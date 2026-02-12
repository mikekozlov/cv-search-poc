from __future__ import annotations

import hashlib
import re


def normalize_source_gdrive_path(source_gdrive_path: str) -> str:
    normalized = (source_gdrive_path or "").replace("\\", "/").lstrip("/")
    return "/".join(part for part in normalized.split("/") if part)


def candidate_key_from_source_gdrive_path(source_gdrive_path: str) -> str:
    normalized = normalize_source_gdrive_path(source_gdrive_path)
    if not normalized:
        return ""
    parts = normalized.split("/")
    if len(parts) <= 1:
        return normalized
    return "/".join(parts[:-1])


def candidate_id_from_source_gdrive_path(source_gdrive_path: str) -> str:
    candidate_key = candidate_key_from_source_gdrive_path(source_gdrive_path)
    if not candidate_key:
        candidate_key = normalize_source_gdrive_path(source_gdrive_path)
    digest = hashlib.md5(candidate_key.encode("utf-8")).hexdigest()
    return f"pptx-{digest[:10]}"


def _normalize_candidate_folder(folder: str) -> str:
    cleaned = (folder or "").replace("_", " ").strip()
    return re.sub(r"\s+", " ", cleaned)


def _name_tokens(name: str | None) -> list[str]:
    if not name:
        return []
    tokens = []
    for part in name.split():
        if any(ch.isalpha() for ch in part):
            tokens.append(part)
    return tokens


def is_probably_full_name(name: str | None) -> bool:
    return len(_name_tokens(name)) >= 2


def candidate_name_from_source_gdrive_path(source_gdrive_path: str) -> str | None:
    normalized = normalize_source_gdrive_path(source_gdrive_path)
    if not normalized:
        return None
    parts = normalized.split("/")
    if len(parts) < 2:
        return None
    candidate_folder = _normalize_candidate_folder(parts[-2])
    if not is_probably_full_name(candidate_folder):
        return None
    return candidate_folder
