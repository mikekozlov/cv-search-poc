from __future__ import annotations

import re

_CANONICAL = ("junior", "middle", "senior", "lead", "manager")
_TOKEN_RE = re.compile(r"[a-z0-9]+", flags=re.IGNORECASE)


def normalize_seniority(value: str | None, *, default: str = "senior") -> str:
    if default not in _CANONICAL:
        raise ValueError(f"default must be one of: {', '.join(_CANONICAL)}")
    if value is None:
        return default
    raw = str(value).strip().lower()
    if not raw:
        return default
    if raw in _CANONICAL:
        return raw

    tokens = set(_TOKEN_RE.findall(raw))

    if _has_any(tokens, {"manager", "mgr", "director", "head", "vp", "vice", "principal"}):
        return "manager"
    if _has_any(tokens, {"lead", "staff"}):
        return "lead"
    if _has_any(tokens, {"senior", "sr"}):
        return "senior"
    if _has_any(tokens, {"middle", "mid", "midlevel"}):
        return "middle"
    if _has_any(tokens, {"junior", "jr", "entry", "intern"}):
        return "junior"

    return default


def _has_any(tokens: set[str], candidates: set[str]) -> bool:
    return bool(tokens.intersection(candidates))
