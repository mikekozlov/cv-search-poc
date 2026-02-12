from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Dict, List, Optional


class SeniorityEnum(str, Enum):
    junior = "junior"
    middle = "middle"
    senior = "senior"
    lead = "lead"
    manager = "manager"


@dataclass
class TeamMember:
    role: str
    seniority: Optional[SeniorityEnum] = None
    domains: List[str] = field(default_factory=list)
    expertise: List[str] = field(default_factory=list)  # Specialization from expertise_lexicon
    tech_tags: List[str] = field(default_factory=list)  # Must-have tech from tech_synonyms
    nice_to_have: List[str] = field(default_factory=list)  # Optional tech from tech_synonyms
    rationale: Optional[str] = None
    tier: Optional[str] = None  # "core" or "sme" - set by role classification


@dataclass
class TeamSize:
    total: Optional[int] = None
    members: List[TeamMember] = field(default_factory=list)


@dataclass
class Criteria:
    domain: List[str]
    tech_stack: List[str]
    expert_roles: List[str]
    project_type: Optional[str] = None
    team_size: Optional[TeamSize] = None
    minimum_team: List[str] = field(default_factory=list)
    extended_team: List[str] = field(default_factory=list)
    presale_rationale: Optional[str] = None

    def to_json(self) -> str:
        def _prune_none(obj):
            if isinstance(obj, dict):
                return {k: _prune_none(v) for k, v in obj.items() if v is not None}
            if isinstance(obj, list):
                return [_prune_none(v) for v in obj if v is not None]
            return obj

        return json.dumps(_prune_none(asdict(self)), ensure_ascii=False, indent=2)


def _normalize_role_key(role: str) -> str:
    """Normalize role string to a canonical key for deduplication."""
    return (role or "").strip().lower().replace(" ", "_").replace("-", "_")


def consolidate_seat_dicts(seats: List[Dict]) -> List[Dict]:
    """Remove duplicate roles from a list of seat dictionaries.

    Keeps first occurrence of each role, merging nice_to_have and domains
    from subsequent duplicates.
    """
    seen_roles: Dict[str, Dict] = {}

    for seat in seats:
        role = seat.get("role", "")
        role_key = _normalize_role_key(role)
        if not role_key:
            continue

        if role_key not in seen_roles:
            seen_roles[role_key] = dict(seat)  # Copy to avoid mutation
        else:
            # Merge nice_to_have and domains into existing
            existing = seen_roles[role_key]
            existing_nice = existing.get("nice_to_have") or []
            new_nice = seat.get("nice_to_have") or []
            existing["nice_to_have"] = list(dict.fromkeys(existing_nice + new_nice))

            existing_domains = existing.get("domains") or []
            new_domains = seat.get("domains") or []
            existing["domains"] = list(dict.fromkeys(existing_domains + new_domains))

    return list(seen_roles.values())


def consolidate_members(members: List[TeamMember]) -> List[TeamMember]:
    """Remove duplicate roles, keeping first occurrence with merged attributes.

    Members with the same normalized role are consolidated into a single entry.
    The first occurrence's core attributes (role, seniority, tech_tags) are kept,
    while nice_to_have and domains are merged from all duplicates.
    """
    seen_roles: Dict[str, TeamMember] = {}

    for member in members:
        role_key = _normalize_role_key(member.role)
        if not role_key:
            continue

        if role_key not in seen_roles:
            seen_roles[role_key] = member
        else:
            # Merge nice_to_have and domains into existing member
            existing = seen_roles[role_key]
            merged_nice = list(dict.fromkeys(existing.nice_to_have + member.nice_to_have))
            merged_domains = list(dict.fromkeys(existing.domains + member.domains))
            # Create new member with merged attributes (dataclass is immutable-ish)
            seen_roles[role_key] = TeamMember(
                role=existing.role,
                seniority=existing.seniority,
                domains=merged_domains,
                expertise=existing.expertise,
                tech_tags=existing.tech_tags,
                nice_to_have=merged_nice,
                rationale=existing.rationale,
                tier=existing.tier,
            )

    return list(seen_roles.values())
