from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass
class FileDetectedEvent:
    file_path: str
    source_category: str | None = None
    source_rel_path: str | None = None
    source_gdrive_path: str | None = None
    mtime_ns: int | None = None
    size_bytes: int | None = None
    detected_at: str | None = None
    event_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class TextExtractedEvent:
    file_path: str
    text: str
    candidate_id: str
    source_category: str | None = None
    source_rel_path: str | None = None
    source_gdrive_path: str | None = None
    mtime_ns: int | None = None
    size_bytes: int | None = None
    detected_at: str | None = None
    event_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class EnrichmentCompleteEvent:
    candidate_id: str
    file_path: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
