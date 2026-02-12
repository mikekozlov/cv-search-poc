from __future__ import annotations

import re
from pathlib import Path
from typing import List, Optional

from cv_search.clients.openai_client import OpenAIClient
from cv_search.config.settings import Settings
from cv_search.core.criteria import (
    Criteria,
    SeniorityEnum,
    TeamMember,
    TeamSize,
    consolidate_members,
)
from cv_search.core.role_classification import classify_role
from cv_search.lexicon.loader import (
    build_tech_reverse_index,
    load_domain_lexicon,
    load_expertise_lexicon,
    load_role_lexicon,
    load_tech_synonym_map,
)
from cv_search.llm.logger import set_run_dir as llm_set_run_dir
from cv_search.llm.logger import reset_run_dir as llm_reset_run_dir


def _canon_tags(seq: List[str] | None, allowed: set[str] | None = None) -> List[str]:
    """Lowercase and deduplicate while preserving input order; optionally filter to allowed set."""
    seen = set()
    out: List[str] = []
    for item in seq or []:
        normalized = (item or "").strip().lower()
        if not normalized or normalized in seen:
            continue
        if allowed is not None and normalized not in allowed:
            continue
        seen.add(normalized)
        out.append(normalized)
    return out


def _map_tech_tags(
    seq: List[str] | None, reverse_index: dict[str, str], tech_lexicon: set[str]
) -> List[str]:
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
    mapping = {
        "mid": "middle",
        "mid-level": "middle",
        "jr": "junior",
        "sr": "senior",
        "sr.": "senior",
    }
    return mapping.get(val, val)


def _as_seniority_enum(value: str | None) -> Optional[SeniorityEnum]:
    norm = _normalize_seniority(value)
    if not norm:
        return None
    try:
        return SeniorityEnum(norm)
    except ValueError:
        return None


def _normalize_member(
    payload: dict,
    tech_reverse: dict[str, str],
    tech_lexicon: set[str],
    role_lexicon: set[str] | None = None,
    domain_lexicon: set[str] | None = None,
    expertise_lexicon: set[str] | None = None,
) -> Optional[TeamMember]:
    role = (payload.get("role") or "").strip().lower()
    if not role or (role_lexicon is not None and role not in role_lexicon):
        return None
    seniority = _as_seniority_enum(payload.get("seniority"))
    # Default to senior if seniority not provided
    if seniority is None:
        seniority = SeniorityEnum.senior
    domains = _canon_tags(payload.get("domains"), allowed=domain_lexicon)
    expertise = _canon_tags(payload.get("expertise"), allowed=expertise_lexicon)
    tech_tags = _map_tech_tags(payload.get("tech_tags"), tech_reverse, tech_lexicon)
    nice_to_have = _map_tech_tags(payload.get("nice_to_have"), tech_reverse, tech_lexicon)
    rationale = payload.get("rationale")
    tier = classify_role(role)
    return TeamMember(
        role=role,
        seniority=seniority,
        domains=domains,
        expertise=expertise,
        tech_tags=tech_tags,
        nice_to_have=nice_to_have,
        rationale=rationale,
        tier=tier,
    )


def _build_team_size(
    payload: dict,
    tech_reverse: dict[str, str],
    tech_lexicon: set[str],
    role_lexicon: set[str] | None = None,
    domain_lexicon: set[str] | None = None,
    expertise_lexicon: set[str] | None = None,
) -> TeamSize | None:
    raw_members: List[dict] = payload.get("members") or []
    members: List[TeamMember] = []
    for raw in raw_members:
        normalized = _normalize_member(
            raw,
            tech_reverse,
            tech_lexicon,
            role_lexicon=role_lexicon,
            domain_lexicon=domain_lexicon,
            expertise_lexicon=expertise_lexicon,
        )
        if normalized:
            members.append(normalized)

    # Consolidate duplicate roles into single entries
    if members:
        members = consolidate_members(members)

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


def parse_request(
    text: str,
    model: str,
    settings: Settings,
    client: OpenAIClient,
    *,
    include_presale: bool = False,
    run_dir: str | Path | None = None,
) -> Criteria:
    """Extract canonical search criteria using the LLM client.

    By default this parses criteria only. Set include_presale=True for presale workflows.
    """

    token = llm_set_run_dir(run_dir) if run_dir else None
    try:
        role_lexicon = set(load_role_lexicon(settings.lexicon_dir))
        domain_lexicon = set(load_domain_lexicon(settings.lexicon_dir))
        expertise_lexicon = set(load_expertise_lexicon(settings.lexicon_dir))
        tech_synonyms = load_tech_synonym_map(settings.lexicon_dir)
        tech_reverse = build_tech_reverse_index(tech_synonyms)
        tech_lexicon = set(tech_synonyms.keys())

        presale_payload: dict = {}
        presale_rationale: str | None = None
        criteria_payload: dict
        english_brief: str | None = None
        if include_presale and hasattr(client, "get_structured_brief"):
            payload = client.get_structured_brief(text, model=model, settings=settings)
            if isinstance(payload, dict):
                english_brief = payload.get("english_brief")
            presale_payload = payload.get("presale_team") or {}
            presale_rationale = presale_payload.get("rationale")
            if presale_rationale is not None and not isinstance(presale_rationale, str):
                presale_rationale = None
            criteria_payload = payload.get("criteria", payload)
        else:
            criteria_payload = client.get_structured_criteria(text, model=model, settings=settings)
            if isinstance(criteria_payload, dict):
                english_brief = criteria_payload.get("english_brief")

        team_payload = criteria_payload.get("team_size") or {}
        team_size = _build_team_size(
            team_payload,
            tech_reverse,
            tech_lexicon,
            role_lexicon=role_lexicon,
            domain_lexicon=domain_lexicon,
            expertise_lexicon=expertise_lexicon,
        )

        domains = _canon_tags(criteria_payload.get("domain"), allowed=domain_lexicon)
        tech_stack = _map_tech_tags(criteria_payload.get("tech_stack"), tech_reverse, tech_lexicon)
        expert_roles = _canon_tags(criteria_payload.get("expert_roles"), allowed=role_lexicon)

        minimum_team = _canon_tags(presale_payload.get("minimum_team"), allowed=role_lexicon)
        extended_team = _canon_tags(presale_payload.get("extended_team"), allowed=role_lexicon)

        if (team_size is None or not team_size.members) and expert_roles:
            fallback_role = expert_roles[0]
            fallback_member = TeamMember(
                role=fallback_role,
                seniority=SeniorityEnum.senior,
                domains=domains,
                tech_tags=tech_stack,
                nice_to_have=[],
                tier=classify_role(fallback_role),
            )
            total = team_size.total if team_size else None
            team_size = TeamSize(total=total or 1, members=[fallback_member])
        elif team_size and not team_size.members and expert_roles:
            fallback_role = expert_roles[0]
            team_size.members.append(
                TeamMember(
                    role=fallback_role,
                    seniority=SeniorityEnum.senior,
                    domains=domains,
                    tech_tags=tech_stack,
                    nice_to_have=[],
                    tier=classify_role(fallback_role),
                )
            )
            team_size.total = team_size.total or len(team_size.members)

        crit_obj = Criteria(
            domain=domains,
            tech_stack=tech_stack,
            expert_roles=expert_roles,
            project_type=criteria_payload.get("project_type"),
            team_size=team_size,
            minimum_team=minimum_team,
            extended_team=extended_team,
            presale_rationale=presale_rationale,
        )
        if english_brief:
            setattr(crit_obj, "_english_brief", english_brief)

        return crit_obj
    finally:
        if token is not None:
            llm_reset_run_dir(token)
