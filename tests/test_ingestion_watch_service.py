from __future__ import annotations

import time
from datetime import datetime

from cv_search.ingestion.file_watch_service import FileWatchService
from cv_search.ingestion.redis_client import InMemoryRedisClient
from cv_search.ingestion.source_identity import candidate_id_from_source_gdrive_path


class _StubDB:
    def __init__(self, last_updated_by_path: dict[str, str | None]) -> None:
        self._last_updated_by_path = last_updated_by_path

    def get_last_updated_for_gdrive_paths(self, paths: list[str]) -> dict[str, str | None]:
        return {path: self._last_updated_by_path.get(path) for path in paths}


def test_candidate_id_includes_relative_path() -> None:
    cid1 = candidate_id_from_source_gdrive_path("Engineering/backend/CV.pptx")
    cid2 = candidate_id_from_source_gdrive_path("Sales/backend/CV.pptx")
    assert cid1 != cid2
    assert cid1 == candidate_id_from_source_gdrive_path(r"Engineering\backend\CV.pptx")


def test_in_memory_set_if_absent_dedupes_and_expires() -> None:
    redis_client = InMemoryRedisClient()
    assert redis_client.set_if_absent("k", "1", ttl_seconds=1)
    assert not redis_client.set_if_absent("k", "1", ttl_seconds=1)
    time.sleep(1.1)
    assert redis_client.set_if_absent("k", "1", ttl_seconds=1)


def test_reconcile_once_enqueues_new_file(tmp_path) -> None:
    inbox_dir = tmp_path / "inbox"
    file_path = inbox_dir / "Engineering" / "backend_engineer" / "backend_sample.txt"
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text("hello", encoding="utf-8")

    rel = file_path.relative_to(inbox_dir).as_posix()
    redis_client = InMemoryRedisClient()
    db = _StubDB(last_updated_by_path={rel: None})
    svc = FileWatchService(
        inbox_dir=inbox_dir,
        redis=redis_client,
        db=db,
        queue_name="ingest:queue:extract:test",
        reconcile=False,
        reconcile_interval_s=None,
        dedupe_ttl_s=60,
    )

    svc.reconcile_once()

    payload = redis_client.pop_from_queue("ingest:queue:extract:test", timeout=1)
    assert payload
    assert payload["source_gdrive_path"] == rel


def test_reconcile_once_skips_unchanged_file(tmp_path) -> None:
    inbox_dir = tmp_path / "inbox"
    file_path = inbox_dir / "Engineering" / "backend_engineer" / "backend_sample.txt"
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text("hello", encoding="utf-8")

    rel = file_path.relative_to(inbox_dir).as_posix()
    mtime_iso = datetime.fromtimestamp(file_path.stat().st_mtime).isoformat()

    redis_client = InMemoryRedisClient()
    db = _StubDB(last_updated_by_path={rel: mtime_iso})
    svc = FileWatchService(
        inbox_dir=inbox_dir,
        redis=redis_client,
        db=db,
        queue_name="ingest:queue:extract:test",
        reconcile=False,
        reconcile_interval_s=None,
        dedupe_ttl_s=60,
    )

    svc.reconcile_once()

    assert redis_client.client.llen("ingest:queue:extract:test") == 0


def test_reconcile_once_ignores_office_temp_files(tmp_path) -> None:
    inbox_dir = tmp_path / "inbox"
    file_path = inbox_dir / "Engineering" / "backend_engineer" / "~$resume.pptx"
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text("not a real pptx", encoding="utf-8")

    rel = file_path.relative_to(inbox_dir).as_posix()
    redis_client = InMemoryRedisClient()
    db = _StubDB(last_updated_by_path={rel: None})
    svc = FileWatchService(
        inbox_dir=inbox_dir,
        redis=redis_client,
        db=db,
        queue_name="ingest:queue:extract:test",
        reconcile=False,
        reconcile_interval_s=None,
        dedupe_ttl_s=60,
        exts=(".pptx",),
    )

    svc.reconcile_once()

    assert redis_client.client.llen("ingest:queue:extract:test") == 0
