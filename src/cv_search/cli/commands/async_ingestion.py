from __future__ import annotations

import os
import subprocess
import sys
import threading

import click

from cv_search.cli.context import CLIContext


def register(cli: click.Group) -> None:
    @cli.command("ingest-async-all")
    @click.pass_obj
    def ingest_async_all_cmd(ctx: CLIContext) -> None:
        """Starts watcher + extractor + enricher in one terminal (local dev)."""

        env = os.environ.copy()
        env["DB_URL"] = ctx.settings.db_url
        env["PYTHONUNBUFFERED"] = "1"

        procs: list[tuple[str, subprocess.Popen[str]]] = []
        print_lock = threading.Lock()

        def start(name: str, args: list[str]) -> None:
            proc = subprocess.Popen(
                args,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            procs.append((name, proc))

        def forward_output(name: str, proc: subprocess.Popen[str]) -> None:
            stream = proc.stdout
            if stream is None:
                return
            for line in iter(stream.readline, ""):
                msg = line.rstrip("\r\n")
                if not msg:
                    continue
                with print_lock:
                    click.echo(f"[{name}] {msg}")

        python = sys.executable
        start("watcher", [python, "-u", "-m", "cv_search.cli", "ingest-watcher"])
        start("extractor", [python, "-u", "-m", "cv_search.cli", "ingest-extractor"])
        start("enricher", [python, "-u", "-m", "cv_search.cli", "ingest-enricher"])

        threads = [
            threading.Thread(target=forward_output, args=(name, proc), daemon=True)
            for name, proc in procs
        ]
        for thread in threads:
            thread.start()

        try:
            while True:
                exit_codes = {name: proc.poll() for name, proc in procs}
                finished = {name: code for name, code in exit_codes.items() if code is not None}
                if finished:
                    with print_lock:
                        for name, code in finished.items():
                            click.echo(f"[{name}] exited with code {code}")
                    raise SystemExit(next(iter(finished.values())))
                threading.Event().wait(0.25)
        except KeyboardInterrupt:
            with print_lock:
                click.echo("Stopping async ingestion (Ctrl+C)...")
        finally:
            for _, proc in procs:
                try:
                    proc.terminate()
                except Exception:
                    pass
            for _, proc in procs:
                try:
                    proc.wait(timeout=5)
                except Exception:
                    pass

    @cli.command("ingest-watcher")
    @click.pass_obj
    def ingest_watcher_cmd(ctx: CLIContext) -> None:
        """Starts the file watcher (Producer)."""
        from cv_search.ingestion.async_pipeline import Watcher
        from cv_search.ingestion.redis_client import RedisClient

        settings = ctx.settings
        redis_client = RedisClient()

        watcher = Watcher(settings, redis_client)
        watcher.run()

    @cli.command("ingest-extractor")
    @click.pass_obj
    def ingest_extractor_cmd(ctx: CLIContext) -> None:
        """Starts the extractor worker (Worker A)."""
        from cv_search.ingestion.async_pipeline import ExtractorWorker
        from cv_search.ingestion.redis_client import RedisClient

        settings = ctx.settings
        redis_client = RedisClient()

        worker = ExtractorWorker(settings, redis_client)
        worker.run()

    @cli.command("ingest-enricher")
    @click.pass_obj
    def ingest_enricher_cmd(ctx: CLIContext) -> None:
        """Starts the enricher worker (Worker B)."""
        from cv_search.ingestion.async_pipeline import EnricherWorker
        from cv_search.ingestion.redis_client import RedisClient

        settings = ctx.settings
        redis_client = RedisClient()

        worker = EnricherWorker(settings, redis_client)
        worker.run()
