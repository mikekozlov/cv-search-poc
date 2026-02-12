from __future__ import annotations

import json
import shutil
from pathlib import Path

from tests.integration.helpers import (
    cleanup_test_state,
    ensure_postgres_available,
    run_cli,
    test_env,
    test_settings,
)


def test_cli_presale_plan_writes_criteria_artifact_with_rationale():
    settings = test_settings()
    env = test_env()

    ensure_postgres_available(settings)
    cleanup_test_state(settings)

    run_dir = Path(settings.active_runs_dir) / "test_cli_presale_plan"
    if run_dir.exists():
        shutil.rmtree(run_dir)

    output = json.loads(
        run_cli(
            [
                "presale-plan",
                "--text",
                "any brief",
                "--run-dir",
                str(run_dir),
            ],
            env,
        )
    )

    criteria_path = run_dir / "criteria.json"
    assert criteria_path.exists(), "presale-plan should write criteria.json into run dir."

    saved = json.loads(criteria_path.read_text(encoding="utf-8"))
    assert saved.get("presale_rationale"), "criteria.json should contain presale_rationale."
    assert saved["presale_rationale"] == output["presale_rationale"]
