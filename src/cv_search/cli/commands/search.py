from __future__ import annotations

import json
import os

import click

from cv_search.cli.context import CLIContext
from cv_search.cli.shared import load_json_file
from cv_search.core.criteria import Criteria, TeamMember, TeamSize
from cv_search.core.parser import parse_request
from cv_search.search import SearchProcessor, default_run_dir
from cv_search.retrieval.embedder_stub import DeterministicEmbedder, EmbedderProtocol


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

    @cli.command("search-seat")
    @click.option(
        "--criteria",
        type=click.Path(exists=True, dir_okay=False),
        default="./data/test/criteria.json",
        required=True,
        help="Path to canonical criteria JSON",
    )
    @click.option("--topk", type=int, default=3, help="Top-K results to return")
    @click.option(
        "--mode",
        type=click.Choice(["lexical", "semantic", "hybrid"]),
        default=None,
        help="Ranking mode",
    )
    @click.option("--vs-topk", type=int, default=None, help="Vector-store fan-in (K)")
    @click.option(
        "--run-dir",
        type=click.Path(file_okay=False),
        default=None,
        help="Output folder for artifacts (default: runs/<timestamp>/)",
    )
    @click.option(
        "--justify/--no-justify",
        default=True,
        help="Enable/disable LLM-based justification (slower).",
    )
    @click.pass_obj
    def search_seat_cmd(
        ctx: CLIContext,
        criteria: str,
        topk: int,
        mode: str | None,
        vs_topk: int | None,
        run_dir: str | None,
        justify: bool,
    ) -> None:
        """
        Seat-aware search with strict gating, then lexical/semantic/hybrid ranking.
        """
        settings = ctx.settings
        client = ctx.client
        db = ctx.db
        embedder = _build_embedder_from_env()

        try:
            crit = load_json_file(criteria)
            out_dir = run_dir or default_run_dir(settings.active_runs_dir)

            processor = SearchProcessor(db, client, settings, embedder=embedder)
            payload = processor.search_for_seat(
                criteria=crit,
                top_k=topk,
                run_dir=out_dir,
                mode_override=mode,
                vs_topk_override=vs_topk,
                with_justification=justify,
            )

            top_ids = [r["candidate_id"] for r in payload["results"]]
            click.echo(
                json.dumps(
                    {
                        "run_dir": out_dir,
                        "mode": mode or settings.search_mode,
                        "topK": top_ids,
                        "payload": payload,
                    },
                    indent=2,
                    ensure_ascii=False,
                )
            )
        finally:
            db.close()

    @cli.command("project-search")
    @click.option(
        "--text",
        type=str,
        required=False,
        help="Free-text brief; used when --criteria is not provided",
    )
    @click.option(
        "--criteria",
        type=click.Path(exists=True, dir_okay=False),
        required=False,
        help="Canonical criteria JSON (optional). If provided, seats are taken from here; otherwise derived from --text.",
    )
    @click.option("--topk", type=int, default=3, help="Top-K per seat")
    @click.option(
        "--run-dir",
        type=click.Path(file_okay=False),
        default=None,
        help="Base output folder for artifacts (default: runs/<timestamp>/)",
    )
    @click.option(
        "--justify/--no-justify",
        default=True,
        help="Enable/disable LLM-based justification (slower).",
    )
    @click.pass_obj
    def project_search_cmd(
        ctx: CLIContext,
        text: str | None,
        criteria: str | None,
        topk: int,
        run_dir: str | None,
        justify: bool,
    ) -> None:
        """
        Multi-seat search:
          - If --criteria is given, run per-seat search as-is.
          - Else, parse --text and derive seats deterministically, then search.
        """
        settings = ctx.settings
        client = ctx.client
        db = ctx.db
        embedder = _build_embedder_from_env()

        if not criteria and not text:
            raise click.ClickException("Provide either --criteria or --text.")

        try:
            out_dir = run_dir or default_run_dir(settings.active_runs_dir)
            processor = SearchProcessor(db, client, settings, embedder=embedder)

            if criteria:
                crit_dict = load_json_file(criteria)
                team_size_dict = crit_dict.get("team_size", {})
                members = [
                    TeamMember(
                        role=member["role"],
                        seniority=member.get("seniority"),
                        domains=member.get("domains", []),
                        tech_tags=member.get("tech_tags", []),
                        nice_to_have=member.get("nice_to_have", []),
                        rationale=member.get("rationale"),
                    )
                    for member in team_size_dict.get("members", [])
                ]
                team_size_obj = TeamSize(total=team_size_dict.get("total"), members=members)

                criteria_obj = Criteria(
                    domain=crit_dict.get("domain", []),
                    tech_stack=crit_dict.get("tech_stack", []),
                    expert_roles=crit_dict.get("expert_roles", []),
                    project_type=crit_dict.get("project_type"),
                    team_size=team_size_obj,
                    minimum_team=crit_dict.get("minimum_team", []),
                    extended_team=crit_dict.get("extended_team", []),
                )
                payload = processor.search_for_project(
                    criteria=criteria_obj,
                    top_k=topk,
                    run_dir=out_dir,
                    raw_text=None,
                    with_justification=justify,
                )
            else:
                criteria_obj = parse_request(
                    text, model=settings.openai_model, settings=settings, client=client
                )
                raw_text_en = getattr(criteria_obj, "_english_brief", None) or text
                payload = processor.search_for_project(
                    criteria=criteria_obj,
                    top_k=topk,
                    run_dir=out_dir,
                    raw_text=raw_text_en,
                    with_justification=justify,
                )

            click.echo(json.dumps(payload, indent=2, ensure_ascii=False))
        finally:
            db.close()

    # Alias expected by integration tests; reuse multiseat implementation.
    cli.add_command(project_search_cmd, name="project-search")
