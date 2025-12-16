from __future__ import annotations

import hashlib


def normalize_source_gdrive_path(source_gdrive_path: str) -> str:
    normalized = (source_gdrive_path or "").replace("\\", "/").lstrip("/")
    return "/".join(part for part in normalized.split("/") if part)


def candidate_id_from_source_gdrive_path(source_gdrive_path: str) -> str:
    normalized = normalize_source_gdrive_path(source_gdrive_path)
    digest = hashlib.md5(normalized.encode("utf-8")).hexdigest()
    return f"pptx-{digest[:10]}"
