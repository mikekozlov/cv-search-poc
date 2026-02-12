from __future__ import annotations

import sys

import click

from cv_search.cli.context import CLIContext, build_context


def _register_commands(cli_group: click.Group) -> None:
    from cv_search.cli.commands import (
        async_ingestion,
        db_admin,
        diagnostics,
        ingestion,
        presale_search,
        search,
        transcription,
    )

    for module in (
        diagnostics,
        db_admin,
        search,
        ingestion,
        async_ingestion,
        presale_search,
        transcription,
    ):
        module.register(cli_group)


def _configure_unicode_output() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            continue


@click.group()
@click.option("--db-url", type=str, default=None, help="Override Postgres DSN for this session.")
@click.pass_context
def cli(ctx: click.Context, db_url: str | None) -> None:
    """cv-search CLI."""
    _configure_unicode_output()
    ctx.obj = build_context(db_url)


_register_commands(cli)


def main() -> None:
    cli()


__all__ = ["CLIContext", "cli", "main"]
