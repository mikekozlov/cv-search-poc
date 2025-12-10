from __future__ import annotations

import re
from typing import List, Optional

from cv_search.clients.openai_client import OpenAIClient
from cv_search.config.settings import Settings
from cv_search.core.criteria import Criteria, SeniorityEnum, TeamMember, TeamSize
from cv_search.lexicon.loader import build_tech_reverse_index, load_tech_synonym_map


def _canon_tags(seq: List[str] | None) -> List[str]:
    """Lowercase and deduplicate while preserving input order."""
    seen = set()
    out: List[str] = []
    for item in seq or []:
        normalized = (item or "").strip().lower()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        out.append(normalized)
    return out


def _map_tech_tags(seq: List[str] | None, reverse_index: dict[str, str], tech_lexicon: set[str]) -> List[str]:
    """Normalize tech strings, split simple combos, map via reverse index, and keep only canonical techs."""
    seen = set()
    out: List[str] = []
    for item in seq or []:
        if not item:
            continue
        # split on slashes to handle combos like ".net 6/8" or "google analytics/ga4"
        parts = [p.strip().lower() for p in re.split(r"[\\/]+", str(item)) if p.strip()]
        if not parts:
            continue
        for part in parts:
            mapped = reverse_index.get(part, part)
            if mapped not in tech_lexicon or mapped in seen:
                continue
            seen.add(mapped)
            out.append(mapped)
    return out


def _normalize_seniority(value: str | None) -> str:
    if not value:
        return ""
    val = (value or "").strip().lower()
    mapping = {"mid": "middle", "mid-level": "middle", "jr": "junior", "sr": "senior", "sr.": "senior"}
    return mapping.get(val, val)


def _as_seniority_enum(value: str | None) -> Optional[SeniorityEnum]:
    norm = _normalize_seniority(value)
    if not norm:
        return None
    try:
        return SeniorityEnum(norm)
    except ValueError:
        return None


def _normalize_member(payload: dict, tech_reverse: dict[str, str], tech_lexicon: set[str]) -> Optional[TeamMember]:
    role = (payload.get("role") or "").strip().lower()
    if not role:
        return None
    seniority = _as_seniority_enum(payload.get("seniority"))
    domains = _canon_tags(payload.get("domains"))
    tech_tags = _map_tech_tags(payload.get("tech_tags"), tech_reverse, tech_lexicon)
    nice_to_have = _map_tech_tags(payload.get("nice_to_have"), tech_reverse, tech_lexicon)
    rationale = payload.get("rationale")
    return TeamMember(
        role=role,
        seniority=seniority,
        domains=domains,
        tech_tags=tech_tags,
        nice_to_have=nice_to_have,
        rationale=rationale,
    )


def _build_team_size(payload: dict, tech_reverse: dict[str, str], tech_lexicon: set[str]) -> TeamSize | None:
    raw_members: List[dict] = payload.get("members") or []
    members: List[TeamMember] = []
    for raw in raw_members:
        normalized = _normalize_member(raw, tech_reverse, tech_lexicon)
        if normalized:
            members.append(normalized)

    raw_total = payload.get("total")
    total: int | None = None
    try:
        total = int(raw_total) if raw_total is not None else None
    except (TypeError, ValueError):
        total = None

    if not members and total is None:
        return None

    if members:
        total = max(total or len(members), len(members))

    return TeamSize(total=total, members=members)


def parse_request(text: str, model: str, settings: Settings, client: OpenAIClient) -> Criteria:
    """Extract canonical search criteria using the LLM client."""

    data = client.get_structured_criteria(text, model=model, settings=settings)
    tech_synonyms = load_tech_synonym_map(settings.lexicon_dir)
    tech_reverse = build_tech_reverse_index(tech_synonyms)
    tech_lexicon = set(tech_synonyms.keys())

    team_payload = data.get("team_size") or {}
    team_size = _build_team_size(team_payload, tech_reverse, tech_lexicon)

    domains = _canon_tags(data.get("domain"))
    tech_stack = _map_tech_tags(data.get("tech_stack"), tech_reverse, tech_lexicon)
    expert_roles = _canon_tags(data.get("expert_roles"))

    if (team_size is None or not team_size.members) and expert_roles:
        fallback_member = TeamMember(
            role=expert_roles[0],
            seniority=SeniorityEnum.senior,
            domains=domains,
            tech_tags=tech_stack,
            nice_to_have=[],
        )
        total = team_size.total if team_size else None
        team_size = TeamSize(total=total or 1, members=[fallback_member])
    elif team_size and not team_size.members and expert_roles:
        team_size.members.append(
            TeamMember(
                role=expert_roles[0],
                seniority=SeniorityEnum.senior,
                domains=domains,
                tech_tags=tech_stack,
                nice_to_have=[],
            )
        )
        team_size.total = team_size.total or len(team_size.members)

    return Criteria(
        domain=domains,
        tech_stack=tech_stack,
        expert_roles=expert_roles,
        project_type=data.get("project_type"),
        team_size=team_size,
    )
