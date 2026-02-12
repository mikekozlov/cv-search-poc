from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable

from cv_search.ingestion.source_identity import candidate_key_from_source_gdrive_path

_ARCHIVED_TOKENS = {
    "archive",
    "archived",
    "backup",
    "copy",
    "old",
}


def _filename_tokens(name: str) -> list[str]:
    base = Path(name).stem.lower()
    return [token for token in re.split(r"[^a-z0-9]+", base) if token]


def is_archived_filename(name: str) -> bool:
    return any(token in _ARCHIVED_TOKENS for token in _filename_tokens(name))


def _mtime_ns(path: Path) -> int:
    stat = path.stat()
    return getattr(stat, "st_mtime_ns", int(stat.st_mtime * 1e9))


def _candidate_key_for_path(path: Path, inbox_dir: Path) -> str | None:
    try:
        rel = path.relative_to(inbox_dir).as_posix()
    except ValueError:
        return None
    key = candidate_key_from_source_gdrive_path(rel)
    return key or rel


def _pick_best_candidate_file(paths: Iterable[Path]) -> Path | None:
    best: Path | None = None
    best_score: tuple[bool, int] | None = None
    for path in paths:
        try:
            score = (not is_archived_filename(path.name), _mtime_ns(path))
        except OSError:
            continue
        if best_score is None or score > best_score:
            best_score = score
            best = path
    return best


def select_latest_candidate_files(paths: Iterable[Path], inbox_dir: Path) -> dict[str, Path]:
    grouped: dict[str, list[Path]] = {}
    for path in paths:
        key = _candidate_key_for_path(path, inbox_dir)
        if not key:
            continue
        grouped.setdefault(key, []).append(path)
    selected: dict[str, Path] = {}
    for key, files in grouped.items():
        best = _pick_best_candidate_file(files)
        if best is not None:
            selected[key] = best
    return selected
