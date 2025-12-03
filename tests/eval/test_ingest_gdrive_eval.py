from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
import yaml

from cv_search.config.settings import Settings
from cv_search.db.database import CVDatabase
from cv_search.ingestion.cv_parser import CVParser
from tests.integration import helpers

RUN_EVAL = "true" # = os.getenv("RUN_INGEST_EVAL", "").lower() in {"1", "true", "yes"}

pytestmark = [
    pytest.mark.slow,
    pytest.mark.skipif(not RUN_EVAL, reason="Set RUN_INGEST_EVAL=1 to run eval harness"),
]


def _f1(truth: list[str], pred: list[str]) -> float:
    truth_set = set(truth or [])
    pred_set = set(pred or [])
    if not truth_set and not pred_set:
        return 1.0
    if not truth_set or not pred_set:
        return 0.0
    tp = len(truth_set & pred_set)
    precision = tp / len(pred_set)
    recall = tp / len(truth_set)
    if precision + recall == 0:
        return 0.0
    return 2 * precision * recall / (precision + recall)


def _maybe_write_output(settings: Settings, metrics: dict) -> None:
    """Optionally append metrics to runs/evals JSONL when WRITE_EVAL_OUTPUT=1."""
    # if os.getenv("WRITE_EVAL_OUTPUT", "").lower() not in {"1", "true", "yes"}:
    #     return

    out_dir = settings.runs_dir / "evals"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "ingest_gdrive.jsonl"
    with out_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(metrics) + "\n")


def test_ingest_gdrive_eval_backend(monkeypatch) -> None:
    """Evaluate tags produced by ingest-gdrive against golden labels."""
    settings = helpers.test_settings()
    helpers.ensure_postgres_available(settings)
    helpers.cleanup_test_state(settings)

    env = helpers.test_env()
    if os.getenv("EVAL_USE_LIVE", "").lower() in {"1", "true", "yes"}:
        env.pop("USE_OPENAI_STUB", None)
        env.pop("HF_HUB_OFFLINE", None)
        env.pop("USE_DETERMINISTIC_EMBEDDER", None)

    def fake_extract_text(self, file_path):
        return "\n".join(
            [
                "Name: Stub Backend",
                "Role: Backend Engineer",
                "Domain: HealthTech projects",
                "Tech: dotnet, postgresql, kafka, kubernetes, python",
            ]
        )

    monkeypatch.setattr(CVParser, "extract_text", fake_extract_text, raising=True)

    pptx_path = helpers.make_inbox_pptx_placeholder(settings, role_folder="backend_engineer", filename="test.pptx")
    candidate_id = helpers.pptx_candidate_id(pptx_path.name)

    helpers.run_cli(["init-db"], env)
    helpers.run_cli(["ingest-gdrive", "--file", pptx_path.name], env)

    golden_path = Path(__file__).resolve().parents[1] / "fixtures" / "golden" / "ingest_gdrive_backend.yaml"
    golden = yaml.safe_load(golden_path.read_text(encoding="utf-8"))
    cv_json = helpers.load_ingested_json(settings, candidate_id)

    llm_domain = sorted({tag for exp in cv_json.get("experience", []) for tag in exp.get("domain_tags", [])})
    llm_metrics = {
        "role_tags": _f1(golden["role_tags"], cv_json.get("role_tags", [])),
        "tech_tags": _f1(golden["tech_tags"], cv_json.get("tech_tags", [])),
        "domain_tags": _f1(golden["domain_tags"], llm_domain),
    }

    db = CVDatabase(settings)
    try:
        tag_rows = db.conn.execute(
            "SELECT tag_type, tag_key FROM candidate_tag WHERE candidate_id = %s",
            (candidate_id,),
        ).fetchall()
    finally:
        db.close()

    role_db = sorted({r["tag_key"] for r in tag_rows if r["tag_type"] == "role"})
    tech_db = sorted({r["tag_key"] for r in tag_rows if r["tag_type"] == "tech"})
    domain_db = sorted({r["tag_key"] for r in tag_rows if r["tag_type"] == "domain"})

    db_metrics = {
        "role_tags": _f1(golden["role_tags"], role_db),
        "tech_tags": _f1(golden["tech_tags"], tech_db),
        "domain_tags": _f1(golden["domain_tags"], domain_db),
    }

    metrics = {
        "candidate_id": candidate_id,
        "llm": llm_metrics,
        "db": db_metrics,
    }
    _maybe_write_output(settings, metrics)

    assert all(v == 1.0 for v in llm_metrics.values())
    assert all(v == 1.0 for v in db_metrics.values())
