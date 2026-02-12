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
    rationale: str = Field(
        description=(
            "Short, user-facing explanation of why the candidate matches or does not match, "
            "citing the strongest evidence. This is not hidden chain-of-thought."
        )
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
    insufficient_info: str | None = None  # User-friendly message when query is too ambiguous
    rationale: str = Field(
        description=(
            "Short, user-facing explanation of how the criteria were derived from the brief. "
            "Mention the key cues (roles/tech/domain) used. This is not hidden chain-of-thought."
        )
    )

    if ConfigDict is not None:
        model_config = ConfigDict(extra="allow")
    else:

        class Config:
            extra = "allow"


class LLMStructuredBrief(BaseModel):
    """Combined criteria + presale team payload produced from a single brief."""

    criteria: LLMCriteria
    presale_team: PresaleTeamPlan
    rationale: str = Field(
        description=(
            "Short, user-facing explanation of the overall interpretation of the client brief "
            "and why the selected criteria and presale roles fit. This is not hidden chain-of-thought."
        )
    )

    if ConfigDict is not None:
        model_config = ConfigDict(extra="allow")
    else:

        class Config:
            extra = "allow"


class RankedCandidateVerdict(BaseModel):
    """Single candidate verdict from LLM batch ranking."""

    candidate_id: str = Field(description="Candidate id from the provided candidates list.")
    match_summary: str = Field(description="Exactly 1 sentence executive summary of fit.")
    strength_analysis: List[str] = Field(
        default_factory=list,
        description="List with exactly 1 item; one sentence citing best-fit evidence.",
    )
    gap_analysis: List[str] = Field(
        default_factory=list,
        description="List with exactly 1 item; one sentence citing biggest gap, or 'No material gaps identified.'",
    )
    overall_match_score: float = Field(description="Overall match score from 0.0 to 1.0.")

    if ConfigDict is not None:
        model_config = ConfigDict(extra="allow")
    else:

        class Config:
            extra = "allow"


class CandidateRankingResponse(BaseModel):
    """Batch ranking response from LLM verdict ranker."""

    ranked_candidates: List[RankedCandidateVerdict] = Field(
        default_factory=list,
        description="Ranked candidates best-to-worst. Must contain only ids from the input.",
    )
    notes: str | None = Field(default=None, description="Optional note about the ranking process.")
    rationale: str = Field(
        description=(
            "Short, user-facing explanation of the main factors used to order the candidates "
            "(for example, must-have coverage and domain alignment). This is not hidden chain-of-thought."
        )
    )

    if ConfigDict is not None:
        model_config = ConfigDict(extra="allow")
    else:

        class Config:
            extra = "allow"


class CandidateScore(BaseModel):
    """Minimal score entry for compact ranking response."""

    candidate_id: str = Field(description="Candidate id from the input.")
    overall_match_score: float = Field(description="Match score from 0.0 to 1.0.")

    if ConfigDict is not None:
        model_config = ConfigDict(extra="allow")
    else:

        class Config:
            extra = "allow"


class CompactRankingResponse(BaseModel):
    """Two-tier ranking response: scores for all, full verdicts for top_k only."""

    all_scores: List[CandidateScore] = Field(
        default_factory=list,
        description="All candidates ranked by score (best-to-worst). Length MUST equal pool_size.",
    )
    top_k_verdicts: List[RankedCandidateVerdict] = Field(
        default_factory=list,
        description="Full verdicts (with narratives) for the top_k candidates only.",
    )
    notes: str | None = Field(default=None, description="Optional note about the ranking process.")
    rationale: str = Field(
        description=(
            "Short, user-facing explanation of the main factors used to order the candidates "
            "(for example, must-have coverage and domain alignment). This is not hidden chain-of-thought."
        )
    )

    if ConfigDict is not None:
        model_config = ConfigDict(extra="allow")
    else:

        class Config:
            extra = "allow"
