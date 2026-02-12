from __future__ import annotations
import json
from pathlib import Path
from typing import List, Dict, Any, Tuple


def _load_json(p: Path):
    with open(p, "r", encoding="utf-8") as f:
        return json.load(f)


def load_mock_cvs(test_data_dir: Path) -> List[Dict[str, Any]]:
    """Load mock CVs from the test data directory (data/test/mock_cvs.json)."""
    return _load_json(test_data_dir / "mock_cvs.json")


def load_ingested_cvs_json(
    json_dir: Path,
    *,
    target_filename: str | None = None,
    candidate_id: str | None = None,
) -> Tuple[List[Dict[str, Any]], List[str]]:
    """Load parsed CV JSON payloads from a directory."""
    if not json_dir.exists():
        return [], []

    json_files = sorted(json_dir.glob("*.json"))
    if target_filename:
        json_files = [path for path in json_files if path.name == target_filename]

    cvs: List[Dict[str, Any]] = []
    failed: List[str] = []

    for path in json_files:
        try:
            payload = _load_json(path)
        except Exception:
            failed.append(str(path))
            continue
        if not isinstance(payload, dict):
            failed.append(str(path))
            continue
        if not payload.get("candidate_id"):
            payload["candidate_id"] = path.stem
        if candidate_id and payload.get("candidate_id") != candidate_id:
            continue
        cvs.append(payload)

    return cvs, failed
