from __future__ import annotations

from typing import Any, Dict, List

try:
    from pydantic.v1 import BaseModel, Field
except ImportError:
    from pydantic import BaseModel, Field

try:
    from pydantic import ConfigDict
except ImportError:
    ConfigDict = None


class CandidateJustification(BaseModel):
    """Structured justification output returned by the LLM."""

    match_summary: str = Field(
        description="One to two sentence executive summary of the candidate fit."
    )
    strength_analysis: List[str] = Field(
        default_factory=list, description="Bulleted list of candidate strengths."
    )
    gap_analysis: List[str] = Field(
        default_factory=list, description="Bulleted list of gaps or missing skills."
    )
    overall_match_score: float = Field(description="Overall match score from 0.0 to 1.0.")

    if ConfigDict is not None:
        model_config = ConfigDict(extra="allow")
    else:

        class Config:
            extra = "allow"


class PresaleTeamPlan(BaseModel):
    """Structured presale team composition returned by the LLM."""

    minimum_team: List[str] = Field(
        default_factory=list, description="Canonical role keys required for kickoff."
    )
    extended_team: List[str] = Field(
        default_factory=list, description="Optional/supporting canonical roles."
    )
    rationale: str | None = Field(default=None, description="Short rationale for the selections.")

    if ConfigDict is not None:
        model_config = ConfigDict(extra="allow")
    else:

        class Config:
            extra = "allow"


class LLMCriteria(BaseModel):
    """Structured criteria block produced by the LLM."""

    domain: List[str]
    tech_stack: List[str]
    expert_roles: List[str]
    project_type: str | None = None
    team_size: Dict[str, Any] | None = None

    if ConfigDict is not None:
        model_config = ConfigDict(extra="allow")
    else:

        class Config:
            extra = "allow"


class LLMStructuredBrief(BaseModel):
    """Combined criteria + presale team payload produced from a single brief."""

    criteria: LLMCriteria
    presale_team: PresaleTeamPlan

    if ConfigDict is not None:
        model_config = ConfigDict(extra="allow")
    else:

        class Config:
            extra = "allow"
