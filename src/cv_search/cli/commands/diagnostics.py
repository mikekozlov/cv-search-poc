from __future__ import annotations

import click

from cv_search.cli.context import CLIContext
from cv_search.cli.shared import mask_secret
from cv_search.lexicon.loader import (
    load_domain_lexicon,
    load_expertise_lexicon,
    load_role_lexicon,
    load_tech_synonyms,
)


def register(cli: click.Group) -> None:
    @cli.command("env-info")
    @click.pass_obj
    def env_info_cmd(ctx: CLIContext) -> None:
        """Print env detection (API key masked)."""
        settings = ctx.settings

        click.echo("--- Loaded from Settings ---")
        click.echo(f"OPENAI_API_KEY: {mask_secret(settings.openai_api_key_str)}")
        click.echo(f"OPENAI_MODEL:   {settings.openai_model}")
        click.echo(f"SEARCH_MODE:    {settings.search_mode}")
        click.echo(f"DB_URL:         {settings.db_url}")
        click.echo(f"ACTIVE_DB_URL:  {settings.active_db_url}")
        click.echo(f"LEXICON_DIR:    {settings.lexicon_dir}")
        click.echo(f"RUNS_DIR:       {settings.active_runs_dir}")

    @cli.command("show-lexicons")
    @click.pass_obj
    def show_lexicons_cmd(ctx: CLIContext) -> None:
        """
        Show counts and a short preview of lexicons.
        Works with both list- and dict-based tech lexicons.
        """
        settings = ctx.settings
        roles = load_role_lexicon(settings.lexicon_dir)
        techs = load_tech_synonyms(settings.lexicon_dir)   # returns List[str] in current repo
        doms = load_domain_lexicon(settings.lexicon_dir)
        expertise = load_expertise_lexicon(settings.lexicon_dir)

        click.echo(f"Roles: {len(roles)} | Techs: {len(techs)} | Domains: {len(doms)} | Expertise: {len(expertise)}")

        # Backward-compatible preview: handle list or dict
        if isinstance(techs, dict):
            # Old synonym-map shape: { "react": ["reactjs", ...], ... }
            for k, v in list(techs.items())[:3]:
                more = "..." if len(v) > 3 else ""
                click.echo(f"  {k}: {', '.join(v[:3])}{more}")
        else:
            # Current shape is List[str]
            sample = ", ".join(techs[:10])
            more = "..." if len(techs) > 10 else ""
            click.echo(f"  Sample techs: {sample}{more}")
