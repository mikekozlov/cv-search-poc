from __future__ import annotations

import os
import subprocess
import sys
import threading

import click

from cv_search.cli.context import CLIContext


def _run_processes(
    process_specs: list[tuple[str, list[str]]],
    env: dict[str, str],
    *,
    stop_message: str,
) -> None:
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

    for name, args in process_specs:
        start(name, args)

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
            click.echo(stop_message)
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


def register(cli: click.Group) -> None:
    @cli.command("ingest-async-all")
    @click.option(
        "--enricher-workers",
        type=int,
        default=1,
        show_default=True,
        help="Number of enricher worker processes to run.",
    )
    @click.pass_obj
    def ingest_async_all_cmd(ctx: CLIContext, enricher_workers: int) -> None:
        """Starts watcher + extractor + enricher in one terminal (local dev)."""
        if enricher_workers < 1:
            raise click.BadParameter("enricher-workers must be >= 1")

        env = os.environ.copy()
        env["DB_URL"] = ctx.settings.db_url
        env["PYTHONUNBUFFERED"] = "1"

        python = sys.executable
        process_specs = [
            ("watcher", [python, "-u", "-m", "cv_search.cli", "ingest-watcher"]),
            ("extractor", [python, "-u", "-m", "cv_search.cli", "ingest-extractor"]),
        ]
        process_specs.extend(
            (
                f"enricher-{worker_index}",
                [
                    python,
                    "-u",
                    "-m",
                    "cv_search.cli",
                    "ingest-enricher",
                    "--workers",
                    "1",
                ],
            )
            for worker_index in range(1, enricher_workers + 1)
        )

        _run_processes(
            process_specs,
            env,
            stop_message="Stopping async ingestion (Ctrl+C)...",
        )

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
    @click.option(
        "--workers",
        type=int,
        default=1,
        show_default=True,
        help="Number of enricher worker processes to run.",
    )
    @click.pass_obj
    def ingest_enricher_cmd(ctx: CLIContext, workers: int) -> None:
        """Starts the enricher worker (Worker B)."""
        if workers < 1:
            raise click.BadParameter("workers must be >= 1")
        if workers > 1:
            env = os.environ.copy()
            env["DB_URL"] = ctx.settings.db_url
            env["PYTHONUNBUFFERED"] = "1"
            python = sys.executable
            process_specs = [
                (
                    f"enricher-{worker_index}",
                    [
                        python,
                        "-u",
                        "-m",
                        "cv_search.cli",
                        "ingest-enricher",
                        "--workers",
                        "1",
                    ],
                )
                for worker_index in range(1, workers + 1)
            ]
            _run_processes(
                process_specs,
                env,
                stop_message="Stopping enricher workers (Ctrl+C)...",
            )
            return

        from cv_search.ingestion.async_pipeline import EnricherWorker
        from cv_search.ingestion.redis_client import RedisClient

        settings = ctx.settings
        redis_client = RedisClient()

        worker = EnricherWorker(settings, redis_client)
        worker.run()
