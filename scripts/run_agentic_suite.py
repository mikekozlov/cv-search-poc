from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    env = os.environ.copy()
    env.setdefault("AGENTIC_TEST_MODE", "1")
    try:
        import pytest  # type: ignore

        cmd = [sys.executable, "-m", "pytest", "tests/integration", "-q"]
        subprocess.check_call(cmd, cwd=REPO_ROOT, env=env)
    except ModuleNotFoundError:
        os.environ.setdefault("AGENTIC_TEST_MODE", "1")
        print("pytest not installed; running integration tests directly.")
        sys.path.insert(0, str(REPO_ROOT))
        from tests.integration import (
            test_async_agentic,
            test_cli_agentic,
            test_project_search_artifacts,
        )

        test_cli_agentic.test_cli_ingest_and_search_backend()
        test_project_search_artifacts.test_project_search_writes_artifacts_and_respects_expected_order()
        test_async_agentic.test_async_pipeline_agentic_ingests_text_samples()


if __name__ == "__main__":
    main()
