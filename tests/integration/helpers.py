from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from typing import Tuple

import pytest
from click.testing import CliRunner
from dotenv import load_dotenv

from cv_search.config.settings import Settings
from cv_search.db.database import CVDatabase
from main import cli

REPO_ROOT = Path(__file__).resolve().parents[2]
TEST_ENV_FILE = REPO_ROOT / ".env.test"
PATH_ENV_KEYS = ["DATA_DIR", "RUNS_DIR", "GDRIVE_LOCAL_DEST_DIR", "LLM_STUB_DIR"]
REQUIRED_ENV_KEYS = ["DB_URL", "DATA_DIR", "RUNS_DIR", "GDRIVE_LOCAL_DEST_DIR"]


def _load_test_env_vars() -> dict:
    """Load .env.test and normalize path-like entries to absolute paths."""
    load_dotenv(TEST_ENV_FILE, override=True)
    env = os.environ.copy()
    missing = [key for key in REQUIRED_ENV_KEYS if not env.get(key)]
    if missing:
        raise RuntimeError(f"Missing required test env vars in {TEST_ENV_FILE}: {', '.join(missing)}")

    for key in PATH_ENV_KEYS:
        val = env.get(key)
        if not val:
            continue
        p = Path(val)
        if not p.is_absolute():
            norm = str((REPO_ROOT / val).resolve())
            env[key] = norm
            os.environ[key] = norm
    return env


def test_settings() -> Settings:
    """Construct Settings pinned to test infra using .env.test overrides."""
    _load_test_env_vars()
    return Settings()


def test_env() -> dict:
    env = _load_test_env_vars()
    return env


def run_cli(args: list[str], env: dict) -> str:
    runner = CliRunner()
    cwd = os.getcwd()
    os.chdir(REPO_ROOT)
    try:
        result = runner.invoke(cli, args, env=env, catch_exceptions=False)
    finally:
        os.chdir(cwd)
    if result.exit_code != 0:
        raise AssertionError(f"Command failed: {args}\nOUTPUT:\n{result.output}")
    return result.output.strip()


def cleanup_test_state(settings: Settings) -> None:
    try:
        db = CVDatabase(settings)
        db.reset_state()
        db.close()
    except Exception as exc:
        raise RuntimeError(f"Failed to reset Postgres state: {exc}") from exc
    runs_dir = settings.runs_dir
    if runs_dir.exists():
        shutil.rmtree(runs_dir)
    inbox_dir = settings.gdrive_local_dest_dir
    if inbox_dir.exists():
        shutil.rmtree(inbox_dir)
    inbox_dir.mkdir(parents=True, exist_ok=True)
    json_out_dir = settings.data_dir / "ingested_cvs_json"
    if json_out_dir.exists():
        shutil.rmtree(json_out_dir)
    json_out_dir.mkdir(parents=True, exist_ok=True)


def ensure_postgres_available(settings: Settings) -> None:
    try:
        db = CVDatabase(settings)
        db.initialize_schema()
        db.reset_state()
        db.close()
    except Exception as exc:
        pytest.skip(f"Postgres not reachable for tests: {exc}")


def ingest_mock_state() -> Tuple[Settings, dict]:
    settings = test_settings()
    env = test_env()
    ensure_postgres_available(settings)
    cleanup_test_state(settings)
    try:
        run_cli(["init-db"], env)
        run_cli(["ingest-mock"], env)
    except AssertionError as exc:
        pytest.skip(f"CLI failed to prepare Postgres-backed state: {exc}")
    return settings, env


def make_inbox_pptx_placeholder(settings: Settings, role_folder: str = "backend_engineer", filename: str = "test.pptx") -> Path:
    """Create an inbox layout and dummy PPTX file for ingestion tests."""
    role_dir = settings.gdrive_local_dest_dir / "CVs" / role_folder
    role_dir.mkdir(parents=True, exist_ok=True)
    pptx_path = role_dir / filename
    pptx_path.write_bytes(b"placeholder-pptx")
    return pptx_path


def pptx_candidate_id(filename: str) -> str:
    """Mimic pipeline candidate_id derivation from filename only."""
    import hashlib

    file_hash = hashlib.md5(filename.encode()).hexdigest()
    return f"pptx-{file_hash[:10]}"


def load_ingested_json(settings: Settings, candidate_id: str) -> dict:
    """Load debug JSON emitted by pipeline for a given candidate_id."""
    json_path = settings.data_dir / "ingested_cvs_json" / f"{candidate_id}.json"
    if not json_path.exists():
        raise FileNotFoundError(f"Ingestion JSON not found at {json_path}")
    return json.loads(json_path.read_text(encoding="utf-8"))
