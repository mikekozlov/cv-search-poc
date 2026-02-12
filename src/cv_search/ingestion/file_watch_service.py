from __future__ import annotations

import hashlib
import threading
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Sequence

import click
from watchdog.events import FileMovedEvent, FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

from cv_search.db.database import CVDatabase
from cv_search.ingestion.events import FileDetectedEvent
from cv_search.ingestion.file_selection import select_latest_candidate_files
from cv_search.ingestion.redis_client import RedisClient
from cv_search.ingestion.source_identity import candidate_key_from_source_gdrive_path


@dataclass(frozen=True)
class FileSignature:
    mtime_ns: int
    size_bytes: int


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _signature(path: Path) -> FileSignature:
    stat = path.stat()
    mtime_ns = getattr(stat, "st_mtime_ns", int(stat.st_mtime * 1e9))
    return FileSignature(mtime_ns=mtime_ns, size_bytes=stat.st_size)


def _is_interesting_file(path: Path, exts: Sequence[str]) -> bool:
    # Office creates temporary files like "~$Resume.pptx" while a document is open.
    # These are not real CV payloads and should never be ingested.
    if path.name.startswith("~$"):
        return False
    if path.suffix.lower() not in exts:
        return False
    try:
        return path.is_file()
    except OSError:
        return False


class _CoalescingScheduler:
    def __init__(self, *, debounce_s: float, callback: Callable[[Path], None]) -> None:
        self._debounce_s = debounce_s
        self._callback = callback
        self._condition = threading.Condition()
        self._due_at: dict[Path, float] = {}
        self._stop = False
        self._last_error_at = 0.0
        self._thread = threading.Thread(target=self._run, name="file-coalescer", daemon=True)

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        with self._condition:
            self._stop = True
            self._condition.notify_all()
        self._thread.join(timeout=5)

    def notify(self, path: Path) -> None:
        now = time.monotonic()
        with self._condition:
            self._due_at[path] = now + self._debounce_s
            self._condition.notify_all()

    def _run(self) -> None:
        while True:
            with self._condition:
                if self._stop:
                    return
                if not self._due_at:
                    self._condition.wait(timeout=1.0)
                    continue

                next_path, next_due = min(self._due_at.items(), key=lambda item: item[1])
                now = time.monotonic()
                wait_s = max(0.0, next_due - now)
                if wait_s > 0:
                    self._condition.wait(timeout=wait_s)
                    continue
                self._due_at.pop(next_path, None)

            try:
                self._callback(next_path)
            except Exception as exc:
                now = time.monotonic()
                if now - self._last_error_at >= 5.0:
                    self._last_error_at = now
                    click.secho(
                        f"FileWatchService error while handling {next_path}: {exc}",
                        fg="red",
                    )
                continue


class _WatchdogHandler(FileSystemEventHandler):
    def __init__(self, on_path: Callable[[Path], None]) -> None:
        super().__init__()
        self._on_path = on_path

    def on_created(self, event: FileSystemEvent) -> None:
        if not event.is_directory:
            self._on_path(Path(event.src_path))

    def on_modified(self, event: FileSystemEvent) -> None:
        if not event.is_directory:
            self._on_path(Path(event.src_path))

    def on_moved(self, event: FileMovedEvent) -> None:
        if not event.is_directory:
            self._on_path(Path(event.dest_path))


class FileWatchService:
    def __init__(
        self,
        *,
        inbox_dir: Path,
        redis: RedisClient,
        db: CVDatabase,
        queue_name: str,
        exts: Sequence[str] = (".pptx", ".txt"),
        debounce_ms: int = 750,
        stable_ms: int = 1500,
        dedupe_ttl_s: int = 24 * 60 * 60,
        reconcile: bool = True,
        reconcile_interval_s: int | None = 10 * 60,
    ) -> None:
        self.inbox_dir = inbox_dir
        self.redis = redis
        self.db = db
        self.queue_name = queue_name
        self.exts = tuple(ext.lower() for ext in exts)
        self.debounce_s = debounce_ms / 1000.0
        self.stable_s = stable_ms / 1000.0
        self.dedupe_ttl_s = dedupe_ttl_s
        self.reconcile = reconcile
        self.reconcile_interval_s = reconcile_interval_s

        self._stop_event = threading.Event()
        self._observer = Observer()
        self._handler = _WatchdogHandler(self._on_fs_event)
        self._coalescer = _CoalescingScheduler(
            debounce_s=self.debounce_s, callback=self._process_path
        )
        self._reconcile_thread: threading.Thread | None = None

    def start(self) -> None:
        self.inbox_dir.mkdir(parents=True, exist_ok=True)

        if self.reconcile:
            self.reconcile_once()

        if self.reconcile and self.reconcile_interval_s:
            self._reconcile_thread = threading.Thread(
                target=self._reconcile_loop, name="reconcile-scan", daemon=True
            )
            self._reconcile_thread.start()

        self._coalescer.start()
        self._observer.schedule(self._handler, str(self.inbox_dir), recursive=True)
        self._observer.start()

    def stop(self) -> None:
        self._stop_event.set()
        try:
            self._observer.stop()
            self._observer.join(timeout=5)
        finally:
            self._coalescer.stop()

    def run_forever(self) -> None:
        self.start()
        try:
            while not self._stop_event.is_set():
                time.sleep(0.5)
        finally:
            self.stop()

    def _on_fs_event(self, path: Path) -> None:
        self._coalescer.notify(path.resolve(strict=False))

    def _reconcile_loop(self) -> None:
        interval_s = int(self.reconcile_interval_s or 0)
        while not self._stop_event.is_set():
            time.sleep(interval_s)
            if self._stop_event.is_set():
                return
            self.reconcile_once()

    def reconcile_once(self) -> None:
        candidates = [p for p in self.inbox_dir.rglob("*") if _is_interesting_file(p, self.exts)]
        if not candidates:
            return

        selected = select_latest_candidate_files(candidates, self.inbox_dir)
        if not selected:
            return

        rel_paths: list[str] = []
        files_by_rel: dict[str, Path] = {}
        for file_path in selected.values():
            try:
                rel = file_path.relative_to(self.inbox_dir).as_posix()
            except ValueError:
                continue
            if not rel:
                continue
            if rel in files_by_rel:
                continue
            rel_paths.append(rel)
            files_by_rel[rel] = file_path

        if not rel_paths:
            return

        if hasattr(self.db, "get_last_updated_for_gdrive_paths"):
            last_updated_map = self.db.get_last_updated_for_gdrive_paths(rel_paths)
        else:
            last_updated_map = self.db.get_last_updated_for_filenames([p.name for p in candidates])

        for rel, file_path in files_by_rel.items():
            mtime_iso = datetime.fromtimestamp(file_path.stat().st_mtime).isoformat()
            last_upd = last_updated_map.get(rel) or last_updated_map.get(file_path.name)
            if last_upd and last_upd == mtime_iso:
                continue
            self._enqueue_if_new(file_path, source_gdrive_path=rel)

    def _process_path(self, path: Path) -> None:
        if not _is_interesting_file(path, self.exts):
            return
        try:
            source_gdrive_path = path.relative_to(self.inbox_dir).as_posix()
        except ValueError:
            return

        try:
            sig_before = _signature(path)
        except FileNotFoundError:
            return
        time.sleep(self.stable_s)
        try:
            sig_after = _signature(path)
        except FileNotFoundError:
            return
        if sig_before != sig_after:
            self._coalescer.notify(path)
            return

        if not self._is_latest_candidate_file(path):
            return

        self._enqueue_if_new(path, source_gdrive_path=source_gdrive_path)

    def _candidate_key_for_path(self, path: Path) -> str | None:
        try:
            rel = path.relative_to(self.inbox_dir).as_posix()
        except ValueError:
            return None
        key = candidate_key_from_source_gdrive_path(rel)
        return key or rel

    def _is_latest_candidate_file(self, path: Path) -> bool:
        candidate_key = self._candidate_key_for_path(path)
        if not candidate_key:
            return True

        candidate_dir = self.inbox_dir / Path(candidate_key)
        if not candidate_dir.is_dir():
            return True

        candidate_files = [
            candidate
            for candidate in candidate_dir.iterdir()
            if _is_interesting_file(candidate, self.exts)
        ]
        if not candidate_files:
            return False

        selected = select_latest_candidate_files(candidate_files, self.inbox_dir)
        selected_path = selected.get(candidate_key)
        if not selected_path:
            return False
        return selected_path.resolve(strict=False) == path.resolve(strict=False)

    def _enqueue_if_new(self, path: Path, *, source_gdrive_path: str) -> None:
        signature = _signature(path)
        dedupe_material = (
            f"{source_gdrive_path}|{signature.mtime_ns}|{signature.size_bytes}".encode("utf-8")
        )
        dedupe_hash = hashlib.sha1(dedupe_material).hexdigest()
        dedupe_key = f"ingest:dedupe:{dedupe_hash}"

        if not self.redis.set_if_absent(dedupe_key, "1", ttl_seconds=self.dedupe_ttl_s):
            return

        source_parts = source_gdrive_path.split("/")
        source_category = source_parts[0] if len(source_parts) > 1 else None

        event = FileDetectedEvent(
            event_id=str(uuid.uuid4()),
            detected_at=_utc_now_iso(),
            file_path=str(path),
            source_rel_path=source_gdrive_path,
            source_gdrive_path=source_gdrive_path,
            source_category=source_category,
            mtime_ns=signature.mtime_ns,
            size_bytes=signature.size_bytes,
        )

        self.redis.push_to_queue(self.queue_name, event.to_dict())
        click.echo(f"Queued file: {source_gdrive_path}")
