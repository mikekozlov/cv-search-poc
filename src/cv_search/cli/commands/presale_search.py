from __future__ import annotations

import os
from pathlib import Path

import click

from cv_search.cli.context import CLIContext
from cv_search.core.parser import parse_request
from cv_search.planner.service import Planner
from cv_search.retrieval.embedder_stub import DeterministicEmbedder, EmbedderProtocol
from cv_search.search import default_run_dir


def _build_embedder_from_env() -> EmbedderProtocol | None:
    """
    Allow offline/test runs to avoid downloading models by using a deterministic stub embedder.
    Opt in via USE_DETERMINISTIC_EMBEDDER or HF_HUB_OFFLINE environment variables.
    """
    flag = os.environ.get("USE_DETERMINISTIC_EMBEDDER") or os.environ.get("HF_HUB_OFFLINE")
    if flag and str(flag).lower() in {"1", "true", "yes", "on"}:
        return DeterministicEmbedder()
    return None


def register(cli: click.Group) -> None:
    @cli.command("parse-request")
    @click.option("--text", type=str, required=True, help="Free-text client brief")
    @click.option("--model", type=str, default=None, help="Override model, e.g. gpt-4.1-mini")
    @click.pass_obj
    def parse_request_cmd(ctx: CLIContext, text: str, model: str | None) -> None:
        """Parse a project brief to canonical Criteria JSON."""
        settings = ctx.settings
        client = ctx.client
        model_name = model or settings.openai_model
        criteria = parse_request(text, model=model_name, settings=settings, client=client)
        click.echo(criteria.to_json())

    @cli.command("presale-plan")
    @click.option("--text", type=str, required=True, help="Free-text client brief")
    @click.option(
        "--run-dir",
        type=click.Path(file_okay=False),
        default=None,
        help="Output folder for artifacts (default: runs/<timestamp>/)",
    )
    @click.pass_obj
    def presale_plan_cmd(ctx: CLIContext, text: str, run_dir: str | None) -> None:
        """
        LLM-derived presale team arrays returned as Criteria JSON (no search).
        """
        settings = ctx.settings
        client = ctx.client

        planner = Planner()
        crit = parse_request(
            text,
            model=settings.openai_model,
            settings=settings,
            client=client,
            include_presale=True,
        )
        raw_text_en = getattr(crit, "_english_brief", None) or text
        crit_with_plan = planner.derive_presale_team(
            crit,
            raw_text=raw_text_en,
            client=client,
            settings=settings,
        )

        out_dir = run_dir or default_run_dir(settings.active_runs_dir)
        Path(out_dir).mkdir(parents=True, exist_ok=True)
        (Path(out_dir) / "criteria.json").write_text(crit_with_plan.to_json(), encoding="utf-8")

        click.echo(crit_with_plan.to_json())
