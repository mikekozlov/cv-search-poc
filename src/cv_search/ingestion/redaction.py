from __future__ import annotations

import hashlib
import hmac
import re
import unicodedata
from typing import Any, Dict, Iterable

from cv_search.ingestion.seniority import normalize_seniority

DEFAULT_NAME_PREFIX = "Candidate"
_STOPWORDS = {"cv", "resume", "curriculum", "vitae", "profile", "candidate"}

_TOKEN_RE = re.compile(r"[^\W_]+", flags=re.UNICODE)


def anonymized_candidate_name(
    candidate_id: str,
    salt: str | None,
    prefix: str = DEFAULT_NAME_PREFIX,
) -> str:
    prefix_clean = (prefix or DEFAULT_NAME_PREFIX).strip() or DEFAULT_NAME_PREFIX
    seed = (candidate_id or "").strip() or "unknown"
    key = (salt or "").encode("utf-8")
    digest = hmac.new(key, seed.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"{prefix_clean} {digest[:8]}"


def is_anonymized_name(name: str | None, prefix: str = DEFAULT_NAME_PREFIX) -> bool:
    if not name:
        return False
    prefix_clean = (prefix or DEFAULT_NAME_PREFIX).strip() or DEFAULT_NAME_PREFIX
    pattern = rf"^{re.escape(prefix_clean)}\s+[0-9a-f]{{6,}}$"
    return re.match(pattern, name.strip(), flags=re.IGNORECASE) is not None


def redact_name_in_text(
    text: str | None,
    name_hint: str | None,
    filename_hint: str | None,
) -> str:
    if not text:
        return text or ""

    patterns = _build_redaction_patterns(name_hint, filename_hint)
    if not patterns:
        return text

    lines = text.splitlines()
    redacted_lines = []
    for line in lines:
        redacted = line
        for pattern in patterns:
            redacted = pattern.sub(" ", redacted)
        redacted = _clean_line(redacted)
        redacted_lines.append(redacted)
    return "\n".join(redacted_lines)


def sanitize_cv_payload(
    cv: Dict[str, Any],
    *,
    candidate_id: str,
    name_hint: str | None,
    filename_hint: str | None,
    salt: str | None,
    prefix: str = DEFAULT_NAME_PREFIX,
) -> Dict[str, Any]:
    sanitized = dict(cv)
    prefix_clean = (prefix or DEFAULT_NAME_PREFIX).strip() or DEFAULT_NAME_PREFIX
    raw_name = (name_hint or cv.get("name") or "").strip()
    already_anonymized = is_anonymized_name(raw_name, prefix_clean) or raw_name.lower() in {
        "[redacted]",
        "redacted",
    }

    use_name_hint = bool(raw_name) and not already_anonymized
    use_filename_hint = bool(filename_hint) and not use_name_hint and not already_anonymized

    redaction_name = raw_name if use_name_hint else None
    redaction_filename = filename_hint if use_filename_hint else None
    should_redact = bool(redaction_name or redaction_filename)

    if should_redact:
        sanitized["summary"] = redact_name_in_text(
            cv.get("summary"), redaction_name, redaction_filename
        )

    experiences = cv.get("experience") or []
    if isinstance(experiences, list):
        sanitized_exps = []
        for exp in experiences:
            if not isinstance(exp, dict):
                sanitized_exps.append(exp)
                continue
            exp_copy = dict(exp)
            if should_redact:
                exp_copy["project_description"] = redact_name_in_text(
                    exp_copy.get("project_description"),
                    redaction_name,
                    redaction_filename,
                )
                exp_copy["responsibilities"] = _redact_list(
                    exp_copy.get("responsibilities"),
                    redaction_name,
                    redaction_filename,
                )
            exp_copy.pop("highlights", None)
            sanitized_exps.append(exp_copy)
        sanitized["experience"] = sanitized_exps

    sanitized["name"] = raw_name
    sanitized["seniority"] = normalize_seniority(sanitized.get("seniority"))
    sanitized.pop("location", None)
    return sanitized


def _redact_list(
    items: Iterable[str] | None,
    name_hint: str | None,
    filename_hint: str | None,
) -> list[str]:
    if not items:
        return []
    redacted = [
        redact_name_in_text(item, name_hint, filename_hint).strip() for item in items if item
    ]
    return [item for item in redacted if item]


def _build_redaction_patterns(
    name_hint: str | None, filename_hint: str | None
) -> list[re.Pattern[str]]:
    patterns: list[re.Pattern[str]] = []

    if name_hint:
        phrases = _build_name_phrases(name_hint)
        patterns.extend(_compile_phrase_patterns(phrases))
        tokens = _tokenize(name_hint)
        patterns.extend(_compile_token_patterns(tokens, min_len=2))

    if filename_hint:
        filename_tokens = _tokenize_filename(filename_hint)
        patterns.extend(_compile_token_patterns(filename_tokens, min_len=3))

    return patterns


def _build_name_phrases(name_hint: str) -> list[str]:
    normalized = _normalize_whitespace(name_hint)
    if not normalized:
        return []

    phrases = [normalized]
    tokens = _tokenize(normalized)
    if len(tokens) >= 2:
        phrases.append(f"{tokens[0]} {tokens[-1]}")

    if "," in name_hint:
        parts = [p.strip() for p in name_hint.split(",") if p.strip()]
        if len(parts) >= 2:
            phrases.append(f"{parts[1]} {parts[0]}")

    return _dedupe_preserve_order(phrases)


def _compile_phrase_patterns(phrases: Iterable[str]) -> list[re.Pattern[str]]:
    patterns: list[re.Pattern[str]] = []
    for phrase in phrases:
        escaped = re.escape(phrase)
        escaped = re.sub(r"\\\s+", r"\\s+", escaped)
        pattern = rf"(?<!\w){escaped}(?!\w)"
        patterns.append(re.compile(pattern, flags=re.IGNORECASE))
    return patterns


def _compile_token_patterns(tokens: Iterable[str], min_len: int) -> list[re.Pattern[str]]:
    patterns: list[re.Pattern[str]] = []
    for token in _dedupe_preserve_order(tokens):
        token_norm = token.strip()
        if len(token_norm) < min_len:
            continue
        if token_norm.lower() in _STOPWORDS:
            continue
        if token_norm.isdigit():
            continue
        pattern = rf"(?<!\w){re.escape(token_norm)}(?!\w)"
        patterns.append(re.compile(pattern, flags=re.IGNORECASE))
    return patterns


def _tokenize(value: str | None) -> list[str]:
    if not value:
        return []
    normalized = _strip_accents(value)
    return _TOKEN_RE.findall(normalized)


def _tokenize_filename(value: str | None) -> list[str]:
    if not value:
        return []
    cleaned = value.replace("\\", "/")
    filename = cleaned.split("/")[-1]
    filename = re.sub(r"\.[^.]+$", "", filename)
    return _tokenize(filename)


def _strip_accents(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    return "".join(ch for ch in normalized if not unicodedata.combining(ch))


def _normalize_whitespace(value: str) -> str:
    return " ".join((value or "").split())


def _clean_line(value: str) -> str:
    cleaned = re.sub(r"[ \t]{2,}", " ", value).strip()
    cleaned = re.sub(r"\s+([,.;:])", r"\1", cleaned)
    return cleaned


def _dedupe_preserve_order(items: Iterable[str]) -> list[str]:
    seen = set()
    out = []
    for item in items:
        key = item.strip()
        if not key:
            continue
        key_lower = key.lower()
        if key_lower in seen:
            continue
        seen.add(key_lower)
        out.append(key)
    return out
