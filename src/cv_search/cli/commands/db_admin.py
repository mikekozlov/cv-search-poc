from __future__ import annotations

import click

from cv_search.cli.context import CLIContext
from cv_search.ingestion.pipeline import CVIngestionPipeline


def register(cli: click.Group) -> None:
    @cli.command("init-db")
    @click.pass_obj
    def init_db_cmd(ctx: CLIContext) -> None:
        """Initialize (or re-initialize) the Postgres schema."""
        db = ctx.db
        try:
            db.initialize_schema()
            ext = db.check_extensions()
            click.echo(
                f"Initialized database at {db.dsn if hasattr(db, 'dsn') else '[unknown DSN]'}"
            )
            click.echo(f"Extensions: vector={ext.get('vector')}, pg_trgm={ext.get('pg_trgm')}")
        finally:
            db.close()

    @cli.command("check-db")
    @click.pass_obj
    def check_db_cmd(ctx: CLIContext) -> None:
        """Quick DB sanity: tables + extension availability."""
        db = ctx.db
        try:
            names = ", ".join(db.check_tables())
            ext = db.check_extensions()
            click.echo(f"Tables: {names or '(none)'}")
            click.echo(f"vector: {ext.get('vector')}, pg_trgm: {ext.get('pg_trgm')}")
        finally:
            db.close()

    @cli.command("ingest-mock")
    @click.pass_obj
    def ingest_mock_cmd(ctx: CLIContext) -> None:
        """Rebuild Postgres with mock JSON (pgvector + FTS)."""
        settings = ctx.settings
        db = ctx.db
        pipeline = CVIngestionPipeline(db, settings)
        try:
            n = pipeline.run_mock_ingestion()
            click.echo(f"Ingested {n} mock CVs into {settings.active_db_url}")
        finally:
            pipeline.close()
            db.close()
