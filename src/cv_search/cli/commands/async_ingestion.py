from __future__ import annotations

import click

from cv_search.cli.context import CLIContext


def register(cli: click.Group) -> None:
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
