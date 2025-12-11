from __future__ import annotations

import json
from pathlib import Path

from tests.integration.helpers import REPO_ROOT, ingest_mock_state, run_cli


def test_project_search_writes_artifacts_and_respects_expected_order():
    settings, env = ingest_mock_state()

    payload = json.loads(
        run_cli(
            [
                "project-search",
                "--criteria",
                "data/test/criteria.json",
                "--topk",
                "3",
                "--no-justify",
            ],
            env,
        )
    )

    expected = json.loads((REPO_ROOT / "data/test/expected_search.json").read_text())

    run_dir = Path(payload["run_dir"])
    assert run_dir.exists(), "Run directory should be created."
    assert str(settings.active_runs_dir) in str(run_dir), (
        "Artifacts should live under the configured runs dir."
    )

    for idx, seat in enumerate(payload["seats"], start=1):
        seat_dir = run_dir / f"seat_{idx:02d}_{seat['role']}"
        assert (seat_dir / "results.json").exists(), f"Results artifact missing for {seat['role']}"

        results = [r["candidate_id"] for r in seat.get("results", [])]
        seat_expected = expected.get(seat["role"], [])
        assert set(seat_expected).issubset(set(results))
