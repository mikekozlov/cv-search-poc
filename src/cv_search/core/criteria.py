from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import List, Optional


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
    tech_tags: List[str] = field(default_factory=list)
    nice_to_have: List[str] = field(default_factory=list)
    rationale: Optional[str] = None


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

    def to_json(self) -> str:
        def _prune_none(obj):
            if isinstance(obj, dict):
                return {k: _prune_none(v) for k, v in obj.items() if v is not None}
            if isinstance(obj, list):
                return [_prune_none(v) for v in obj if v is not None]
            return obj

        return json.dumps(_prune_none(asdict(self)), ensure_ascii=False, indent=2)
