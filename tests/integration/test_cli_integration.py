from __future__ import annotations

import json
from pathlib import Path

from tests.integration.helpers import REPO_ROOT, ingest_mock_state, run_cli


def test_cli_ingest_and_search_backend():
    settings, env = ingest_mock_state()

    expected = json.loads((REPO_ROOT / "data/test/expected_search.json").read_text())
    mock_cvs = json.loads((REPO_ROOT / "data/test/mock_cvs.json").read_text())

    search_output = run_cli(
        [
            "search-seat",
            "--criteria",
            "data/test/criteria.json",
            "--topk",
            "3",
            "--mode",
            "hybrid",
            "--no-justify",
        ],
        env,
    )
    payload = json.loads(search_output)
    backend_expected = expected["backend_engineer"]
    results = payload.get("topK", [])

    assert results, "Search should return at least one candidate."
    assert set(backend_expected).issubset(set(results)), "Expected backend candidates should be present."

    from cv_search.db.database import CVDatabase

    db = CVDatabase(settings)
    try:
        row = db.conn.execute("SELECT COUNT(*) AS c FROM candidate").fetchone()
        assert row["c"] >= len(mock_cvs), "All mock CVs should be ingested into Postgres."
    finally:
        db.close()
