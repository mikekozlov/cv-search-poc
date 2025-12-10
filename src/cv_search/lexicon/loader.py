from __future__ import annotations
import json
from pathlib import Path
from typing import Dict, List

# Removed PKG_DIR, REPO_ROOT, DEFAULT_LEXICON_DIR, os.getenv

def _load_json(p: Path):
    with open(p, "r", encoding="utf-8") as f:
        return json.load(f)


def load_role_lexicon(lexicon_dir: Path) -> List[str]:
    """Loads the flat list of canonical role keys."""
    return _load_json(lexicon_dir / "role_lexicon.json")


def load_expertise_lexicon(lexicon_dir: Path) -> List[str]:
    """Loads the flat list of canonical expertise keys."""
    data = _load_json(lexicon_dir / "expertise_lexicon.json")
    if not isinstance(data, list):
        raise ValueError("expertise_lexicon.json must be a list")

    normalized: List[str] = []
    seen = set()
    for item in data:
        text = str(item).strip().lower()
        if not text or text in seen:
            continue
        seen.add(text)
        normalized.append(text)

    return normalized


def load_tech_synonym_map(lexicon_dir: Path) -> Dict[str, List[str]]:
    """
    Load canonical->synonyms mapping from tech_synonyms.json.
    Ensures each canonical key is present in its own synonym list and values are normalized/deduped.
    """
    raw = _load_json(lexicon_dir / "tech_synonyms.json")
    if not isinstance(raw, dict):
        raise ValueError("tech_synonyms.json must be an object mapping canonical tech -> list of synonyms")

    normalized: Dict[str, List[str]] = {}
    for canonical, variants in raw.items():
        key = str(canonical).strip().lower()
        if not key:
            continue
        seen = set()
        vals: List[str] = []
        for item in (variants or []):
            val = str(item).strip().lower()
            if not val or val in seen:
                continue
            seen.add(val)
            vals.append(val)
        if key not in seen:
            vals.append(key)
        normalized[key] = vals
    return normalized


def load_tech_lexicon(lexicon_dir: Path) -> List[str]:
    """Returns canonical tech keys (map keys)."""
    return list(load_tech_synonym_map(lexicon_dir).keys())


def build_tech_reverse_index(mapping: Dict[str, List[str]]) -> Dict[str, str]:
    """
    Build synonym->canonical reverse index. Lowercases all synonyms.
    If a synonym appears under multiple canonical keys, the first encountered wins.
    """
    reverse: Dict[str, str] = {}
    for canonical, synonyms in mapping.items():
        for syn in synonyms:
            key = syn.strip().lower()
            if not key or key in reverse:
                continue
            reverse[key] = canonical
    return reverse


def load_domain_lexicon(lexicon_dir: Path) -> List[str]:
    """Loads the flat list of canonical domain keys."""
    return _load_json(lexicon_dir / "domain_lexicon.json")
