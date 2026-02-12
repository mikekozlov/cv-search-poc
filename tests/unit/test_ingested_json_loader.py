import json
from pathlib import Path

from cv_search.ingestion.data_loader import load_ingested_cvs_json


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_load_ingested_cvs_json_reads_and_fills_candidate_id(tmp_path: Path) -> None:
    _write_json(tmp_path / "candidate-1.json", {"candidate_id": "candidate-1", "summary": "a"})
    _write_json(tmp_path / "candidate-2.json", {"summary": "b"})

    cvs, failed = load_ingested_cvs_json(tmp_path)

    assert not failed
    ids = {cv["candidate_id"] for cv in cvs}
    assert ids == {"candidate-1", "candidate-2"}


def test_load_ingested_cvs_json_filters_and_reports_failures(tmp_path: Path) -> None:
    (tmp_path / "bad.json").write_text("{not json", encoding="utf-8")
    _write_json(tmp_path / "ok.json", {"candidate_id": "cid", "summary": "x"})

    cvs, failed = load_ingested_cvs_json(tmp_path, candidate_id="cid")

    assert len(cvs) == 1
    assert cvs[0]["candidate_id"] == "cid"
    assert any(path.endswith("bad.json") for path in failed)

    cvs, _ = load_ingested_cvs_json(tmp_path, target_filename="ok.json")
    assert len(cvs) == 1
    assert cvs[0]["candidate_id"] == "cid"
