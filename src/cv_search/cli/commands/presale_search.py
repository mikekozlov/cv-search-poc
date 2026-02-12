from __future__ import annotations

import json
from pathlib import Path

import click

from cv_search.cli.context import CLIContext
from cv_search.cli.shared import load_json_file
from cv_search.core.criteria import Criteria, SeniorityEnum
from cv_search.core.parser import parse_request
from cv_search.planner.service import Planner
from cv_search.presale import build_presale_search_criteria
from cv_search.search import SearchProcessor, default_run_dir


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
        help="Output folder for artifacts (default: runs/<timestamp>__<uuid>/)",
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

        out_dir = run_dir or default_run_dir(settings.active_runs_dir, subdir=None)
        Path(out_dir).mkdir(parents=True, exist_ok=True)
        (Path(out_dir) / "criteria.json").write_text(crit_with_plan.to_json(), encoding="utf-8")

        click.echo(crit_with_plan.to_json())

    @cli.command("presale-search")
    @click.option(
        "--text",
        type=str,
        required=False,
        help="Free-text client brief (will generate a presale plan first).",
    )
    @click.option(
        "--criteria",
        "criteria_path",
        type=click.Path(exists=True, dir_okay=False),
        required=False,
        help="Path to criteria.json containing minimum_team/extended_team (e.g., from presale-plan).",
    )
    @click.option(
        "--include-extended/--no-include-extended",
        default=True,
        show_default=True,
        help="Include extended presale roles in the search seats.",
    )
    @click.option(
        "--seniority",
        type=click.Choice([e.value for e in SeniorityEnum]),
        default=SeniorityEnum.senior.value,
        show_default=True,
        help="Default seniority applied to each presale role seat.",
    )
    @click.option("--topk", type=int, default=3, show_default=True, help="Top-K per role seat.")
    @click.option(
        "--run-dir",
        type=click.Path(file_okay=False),
        default=None,
        help="Output folder for artifacts (default: runs/presale_search/<timestamp>__<uuid>/)",
    )
    @click.pass_obj
    def presale_search_cmd(
        ctx: CLIContext,
        text: str | None,
        criteria_path: str | None,
        include_extended: bool,
        seniority: str,
        topk: int,
        run_dir: str | None,
    ) -> None:
        """
        End-to-end presale flow: derive presale roles, then search candidates per presale role.

        This converts Criteria.minimum_team / Criteria.extended_team into a multi-seat Criteria
        (one seat per role) and runs SearchProcessor.search_for_project(..., raw_text=None)
        so the "generic brief" guard does not block role-driven searches.
        """
        settings = ctx.settings
        client = ctx.client
        db = ctx.db

        if bool(text) == bool(criteria_path):
            raise click.ClickException("Provide exactly one of --text or --criteria.")

        planner = Planner()
        if criteria_path:
            payload = load_json_file(criteria_path)
            if not isinstance(payload, dict):
                raise click.ClickException("--criteria must be a JSON object.")
            base_criteria = Criteria(
                domain=payload.get("domain", []),
                tech_stack=payload.get("tech_stack", []),
                expert_roles=payload.get("expert_roles", []),
                project_type=payload.get("project_type"),
                team_size=None,
                minimum_team=payload.get("minimum_team", []) or [],
                extended_team=payload.get("extended_team", []) or [],
                presale_rationale=payload.get("presale_rationale"),
            )
        else:
            crit = parse_request(
                text or "",
                model=settings.openai_model,
                settings=settings,
                client=client,
                include_presale=True,
            )
            raw_text_en = getattr(crit, "_english_brief", None) or (text or "")
            base_criteria = planner.derive_presale_team(
                crit,
                raw_text=raw_text_en,
                client=client,
                settings=settings,
            )

        if not (base_criteria.minimum_team or []):
            raise click.ClickException(
                "Presale plan contains no minimum_team roles. "
                "Run presale-plan first or provide a brief via --text."
            )

        search_criteria = build_presale_search_criteria(
            base_criteria,
            include_extended=include_extended,
            seniority=seniority,
        )
        if not search_criteria.team_size or not search_criteria.team_size.members:
            raise click.ClickException("No presale roles selected for search.")

        try:
            out_dir = run_dir or default_run_dir(
                Path(settings.active_runs_dir) / "presale_search",
                subdir=None,
            )
            processor = SearchProcessor(db, client, settings)
            payload = processor.search_for_project(
                criteria=search_criteria,
                top_k=topk,
                run_dir=out_dir,
                raw_text=None,
                run_kind="presale_search",
            )
            click.echo(json.dumps(payload, indent=2, ensure_ascii=False))
        finally:
            db.close()
