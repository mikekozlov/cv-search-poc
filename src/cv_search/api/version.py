"""Build version detection — shared by main.py and health router."""

from __future__ import annotations

from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[3]


def get_build_version() -> str:
    """Return version string with git commit hash suffix."""
    base = "1.0.0"
    # 1. Try BUILD_COMMIT file (baked into Docker image at build time)
    commit_file = _PROJECT_ROOT / "BUILD_COMMIT"
    if commit_file.is_file():
        commit = commit_file.read_text().strip()
        if commit and commit != "dev":
            return f"{base}-{commit}"
    # 2. Try git (local dev)
    try:
        import subprocess

        commit = (
            subprocess.check_output(
                ["git", "rev-parse", "--short", "HEAD"],
                cwd=str(_PROJECT_ROOT),
                stderr=subprocess.DEVNULL,
            )
            .decode()
            .strip()
        )
        if commit:
            return f"{base}-{commit}"
    except Exception:
        pass
    return f"{base}-dev"


#: Computed once at import time.
BUILD_VERSION = get_build_version()
