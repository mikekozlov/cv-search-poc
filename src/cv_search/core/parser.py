from __future__ import annotations

from typing import List, Optional

from cv_search.clients.openai_client import OpenAIClient
from cv_search.config.settings import Settings
from cv_search.core.criteria import Criteria, SeniorityEnum, TeamMember, TeamSize


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


def _normalize_member(payload: dict) -> Optional[TeamMember]:
    role = (payload.get("role") or "").strip().lower()
    if not role:
        return None
    seniority = _as_seniority_enum(payload.get("seniority"))
    domains = _canon_tags(payload.get("domains"))
    tech_tags = _canon_tags(payload.get("tech_tags"))
    nice_to_have = _canon_tags(payload.get("nice_to_have"))
    rationale = payload.get("rationale")
    return TeamMember(
        role=role,
        seniority=seniority,
        domains=domains,
        tech_tags=tech_tags,
        nice_to_have=nice_to_have,
        rationale=rationale,
    )


def _build_team_size(payload: dict) -> TeamSize | None:
    raw_members: List[dict] = payload.get("members") or []
    members: List[TeamMember] = []
    for raw in raw_members:
        normalized = _normalize_member(raw)
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
    team_payload = data.get("team_size") or {}
    team_size = _build_team_size(team_payload)

    domains = _canon_tags(data.get("domain"))
    tech_stack = _canon_tags(data.get("tech_stack"))
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
