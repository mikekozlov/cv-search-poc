from __future__ import annotations

import json
import shutil
from pathlib import Path

from cv_search.clients.openai_client import OpenAIClient, StubOpenAIBackend
from cv_search.core.criteria import Criteria
from cv_search.core.parser import parse_request
from cv_search.db.database import CVDatabase
from cv_search.ingestion.pipeline import CVIngestionPipeline
from cv_search.planner.service import Planner
from cv_search.presale import build_presale_search_criteria
from cv_search.search import SearchProcessor
from tests.integration.helpers import cleanup_test_state, ensure_postgres_available, test_settings


def test_presale_plan_then_search_preserves_rationale_and_writes_artifacts():
    settings = test_settings()
    ensure_postgres_available(settings)
    cleanup_test_state(settings)

    client = OpenAIClient(settings, backend=StubOpenAIBackend(settings))

    pipeline = CVIngestionPipeline(CVDatabase(settings), settings, client=client)
    try:
        pipeline.run_mock_ingestion()
    finally:
        pipeline.close()

    crit = parse_request(
        text="any brief",
        model=settings.openai_model,
        settings=settings,
        client=client,
        include_presale=True,
    )
    raw_text_en = getattr(crit, "_english_brief", None) or "any brief"
    crit_with_plan = Planner().derive_presale_team(
        crit,
        raw_text=raw_text_en,
        client=client,
        settings=settings,
    )

    expected_rationale = "Stubbed presale plan: start with AI/BA core, extend with privacy, integration, and delivery oversight."
    assert crit_with_plan.presale_rationale == expected_rationale

    crit_for_search = Criteria(
        domain=list(crit_with_plan.domain or []),
        tech_stack=list(crit_with_plan.tech_stack or []),
        expert_roles=list(crit_with_plan.expert_roles or []),
        project_type=crit_with_plan.project_type,
        team_size=None,
        minimum_team=["backend_engineer"],
        extended_team=["frontend_engineer"],
        presale_rationale=crit_with_plan.presale_rationale,
    )
    presale_search_criteria = build_presale_search_criteria(crit_for_search)

    run_dir = Path(settings.active_runs_dir) / "test_presale_end_to_end"
    if run_dir.exists():
        shutil.rmtree(run_dir)

    db = CVDatabase(settings)
    processor = SearchProcessor(db, client, settings)
    try:
        payload = processor.search_for_project(
            criteria=presale_search_criteria,
            top_k=3,
            run_dir=str(run_dir),
            raw_text=None,
        )
    finally:
        db.close()

    assert set(payload.keys()) >= {"project_criteria", "seats", "gaps", "run_dir", "note"}
    assert payload["run_dir"] == str(run_dir)

    criteria_path = run_dir / "criteria.json"
    assert criteria_path.exists(), "Project search should write run-level criteria.json."
    saved_criteria = json.loads(criteria_path.read_text(encoding="utf-8"))
    assert saved_criteria.get("presale_rationale") == expected_rationale

    seat_dirs = [
        run_dir / "seat_01_backend_engineer",
        run_dir / "seat_02_frontend_engineer",
    ]
    for seat_dir in seat_dirs:
        assert (seat_dir / "results.json").exists(), f"Missing results.json for {seat_dir.name}"
