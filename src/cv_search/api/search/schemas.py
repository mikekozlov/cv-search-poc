"""Pydantic schemas for search API requests and responses."""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


# -----------------------------------------------------------------------------
# Enums
# -----------------------------------------------------------------------------


class SeniorityLevel(str, Enum):
    """Seniority levels for candidates."""

    junior = "junior"
    middle = "middle"
    senior = "senior"
    lead = "lead"
    manager = "manager"


class SearchMode(str, Enum):
    """Available search ranking modes."""

    llm = "llm"


# -----------------------------------------------------------------------------
# Criteria Models (mirrors core/criteria.py for API use)
# -----------------------------------------------------------------------------


class TeamMemberSchema(BaseModel):
    """Schema for a team member/seat definition."""

    role: str = Field(..., description="Role name (e.g., 'backend developer', 'data engineer')")
    seniority: Optional[SeniorityLevel] = Field(
        default=None, description="Required seniority level"
    )
    domains: List[str] = Field(default_factory=list, description="Domain expertise areas")
    tech_tags: List[str] = Field(default_factory=list, description="Must-have technology tags")
    nice_to_have: List[str] = Field(
        default_factory=list, description="Nice-to-have technology tags"
    )
    rationale: Optional[str] = Field(default=None, description="Rationale for this team member")

    model_config = {"extra": "ignore"}


class TeamSizeSchema(BaseModel):
    """Schema for team size definition."""

    total: Optional[int] = Field(default=None, description="Total team size")
    members: List[TeamMemberSchema] = Field(
        default_factory=list, description="List of team members/seats"
    )

    model_config = {"extra": "ignore"}


class CriteriaSchema(BaseModel):
    """Schema for search criteria."""

    domain: List[str] = Field(default_factory=list, description="Domain areas")
    tech_stack: List[str] = Field(default_factory=list, description="Technology stack")
    expert_roles: List[str] = Field(default_factory=list, description="Expert roles needed")
    project_type: Optional[str] = Field(default=None, description="Type of project")
    team_size: Optional[TeamSizeSchema] = Field(
        default=None, description="Team size and composition"
    )
    minimum_team: List[str] = Field(
        default_factory=list, description="Minimum team roles (presale)"
    )
    extended_team: List[str] = Field(
        default_factory=list, description="Extended team roles (presale)"
    )
    presale_rationale: Optional[str] = Field(default=None, description="Presale rationale")

    model_config = {"extra": "ignore"}


# -----------------------------------------------------------------------------
# Request Models
# -----------------------------------------------------------------------------


class SeatSearchRequest(BaseModel):
    """Request body for single-seat search."""

    criteria: CriteriaSchema = Field(..., description="Search criteria with team member definition")
    top_k: int = Field(default=3, ge=1, le=50, description="Number of top candidates to return")
    include_cv_markdown: bool = Field(
        default=False,
        description="Include full CV markdown in results (disable to reduce response size)",
    )


class ProjectSearchRequest(BaseModel):
    """Request body for multi-seat project search."""

    text: str = Field(
        ...,
        min_length=3,
        max_length=10000,
        description="Natural language project brief",
    )
    top_k: int = Field(default=3, ge=1, le=50, description="Number of top candidates per seat")
    include_cv_markdown: bool = Field(
        default=False,
        description="Include full CV markdown in results (disable to reduce response size)",
    )

    model_config = {
        "extra": "ignore",
        "json_schema_extra": {
            "examples": [
                {
                    "text": "Need 2 backend devs Python, PostgreSQL and one frontend React + Node.js",
                    "top_k": 3,
                }
            ]
        },
    }


class PresaleSearchRequest(BaseModel):
    """Request body for presale team search."""

    text: str = Field(
        ...,
        min_length=10,
        max_length=10000,
        description="Natural language project brief (required)",
    )
    top_k: int = Field(default=3, ge=1, le=50, description="Number of top candidates per role")
    include_extended: bool = Field(
        default=False, description="Include extended presale roles in search"
    )
    include_cv_markdown: bool = Field(
        default=False,
        description="Include full CV markdown in results (disable to reduce response size)",
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "text": "Mobile app with payments integration and web dashboard, need Flutter mobile, React frontend, Python backend with Stripe",
                    "top_k": 3,
                }
            ]
        },
    }


# -----------------------------------------------------------------------------
# Response Models - Score Components
# -----------------------------------------------------------------------------


class LexicalScoreDetails(BaseModel):
    """Detailed lexical scoring breakdown."""

    raw: float = Field(default=0.0, description="Raw lexical score")
    coverage: float = Field(default=0.0, description="Must-have tag coverage (0-1)")
    coverage_denominator: float = Field(default=1.0, description="Number of must-have tags")
    must_hit_count: int = Field(default=0, description="Number of must-have tags matched")
    nice_hit_count: int = Field(default=0, description="Number of nice-to-have tags matched")
    must_count: int = Field(default=0, description="Total must-have tags requested")
    nice_count: int = Field(default=0, description="Total nice-to-have tags requested")
    must_idf_sum: float = Field(default=0.0, description="Sum of IDF for matched must-have tags")
    nice_idf_sum: float = Field(default=0.0, description="Sum of IDF for matched nice-to-have tags")
    must_idf_total: float = Field(default=0.0, description="Total IDF for all must-have tags")
    nice_idf_total: float = Field(default=0.0, description="Total IDF for all nice-to-have tags")
    must_idf_cov: float = Field(default=0.0, description="IDF coverage for must-have tags")
    nice_idf_cov: float = Field(default=0.0, description="IDF coverage for nice-to-have tags")
    domain_hit: bool = Field(default=False, description="Whether domain tag matched")
    domain_bonus: float = Field(default=0.0, description="Domain bonus score")
    fts_rank: float = Field(default=0.0, description="Full-text search rank")
    weights: Dict[str, float] = Field(default_factory=dict, description="Weight configuration")
    terms: Dict[str, float] = Field(default_factory=dict, description="Individual term scores")

    model_config = {"extra": "allow"}


class SemanticScoreDetails(BaseModel):
    """Detailed semantic scoring breakdown."""

    score: float = Field(default=0.0, description="Final semantic score")
    raw_score: Optional[float] = Field(default=None, description="Raw cosine similarity")
    distance: Optional[float] = Field(default=None, description="Vector distance")
    score_source: Optional[str] = Field(default=None, description="Source of semantic score")
    clamped_score: float = Field(default=0.0, description="Clamped score (0-1)")

    model_config = {"extra": "allow"}


class HybridScoreDetails(BaseModel):
    """Hybrid scoring details."""

    mode: str = Field(default="hybrid", description="Scoring mode used")
    final: float = Field(default=0.0, description="Final fused score")
    lex_raw: float = Field(default=0.0, description="Raw lexical score")
    sem_score: float = Field(default=0.0, description="Semantic score component")
    pool_size: int = Field(default=0, description="Candidate pool size")

    model_config = {"extra": "allow"}


class LLMScoreDetails(BaseModel):
    """LLM ranking details."""

    overall_match_score: float = Field(default=0.0, description="LLM-assigned match score")
    lexical_rank: int = Field(default=0, description="Original lexical rank before LLM")

    model_config = {"extra": "allow"}


class ScoreComponents(BaseModel):
    """Complete score breakdown for a candidate."""

    mode: str = Field(default="hybrid", description="Search mode")
    lexical: LexicalScoreDetails = Field(
        default_factory=LexicalScoreDetails, description="Lexical scoring details"
    )
    semantic: SemanticScoreDetails = Field(
        default_factory=SemanticScoreDetails, description="Semantic scoring details"
    )
    hybrid: HybridScoreDetails = Field(
        default_factory=HybridScoreDetails, description="Hybrid fusion details"
    )
    weights: Dict[str, float] = Field(default_factory=dict, description="Global weights")
    llm: Optional[LLMScoreDetails] = Field(default=None, description="LLM ranking details")

    model_config = {"extra": "allow"}


class LLMJustification(BaseModel):
    """LLM-generated justification for a candidate match."""

    match_summary: str = Field(default="", description="Summary of match quality")
    strength_analysis: List[str] = Field(
        default_factory=list, description="Strengths of the candidate"
    )
    gap_analysis: List[str] = Field(default_factory=list, description="Gaps or concerns")
    overall_match_score: float = Field(default=0.0, description="Overall match score (0-1)")

    model_config = {"extra": "allow"}


class RecencyInfo(BaseModel):
    """Recency information for a candidate."""

    last_updated: Optional[str] = Field(default=None, description="Last CV update timestamp")

    model_config = {"extra": "allow"}


# -----------------------------------------------------------------------------
# Response Models - Candidate Result
# -----------------------------------------------------------------------------


class CandidateResult(BaseModel):
    """Schema for a single candidate result - full data matching Streamlit output."""

    candidate_id: str = Field(..., description="Unique candidate identifier")
    name: Optional[str] = Field(default=None, description="Candidate display name")
    source_file: Optional[str] = Field(
        default=None, description="Path of the source file this CV was parsed from"
    )
    cv_markdown: Optional[str] = Field(
        default=None, description="Full CV content in Markdown format"
    )
    score: Dict[str, Any] = Field(default_factory=dict, description="Score with value and order")
    score_components: Optional[ScoreComponents] = Field(
        default=None, description="Detailed score breakdown"
    )
    must_have: Dict[str, bool] = Field(default_factory=dict, description="Must-have tag matches")
    nice_to_have: Dict[str, bool] = Field(
        default_factory=dict, description="Nice-to-have tag matches"
    )
    recency: Optional[RecencyInfo] = Field(default=None, description="Recency information")
    llm_justification: Optional[LLMJustification] = Field(
        default=None, description="LLM-generated justification"
    )

    model_config = {"extra": "allow"}


class SearchMetrics(BaseModel):
    """Metrics about the search execution."""

    gate_count: int = Field(default=0, description="Candidates passing gating filter")
    lex_fanin: int = Field(default=0, description="Lexical retrieval fan-in")
    pool_size: int = Field(default=0, description="Final candidate pool size")
    mode: str = Field(default="llm", description="Search mode used")
    duration_ms: Optional[int] = Field(default=None, description="Search duration in ms")


class SeatSearchResponse(BaseModel):
    """Response for single-seat search."""

    run_id: str = Field(..., description="Unique run identifier")
    status: str = Field(..., description="Search status (ok, error, skipped)")
    criteria: Dict[str, Any] = Field(..., description="Search criteria used")
    results: List[CandidateResult] = Field(
        default_factory=list, description="Ranked candidate results"
    )
    metrics: SearchMetrics = Field(
        default_factory=SearchMetrics, description="Search execution metrics"
    )
    reason: Optional[str] = Field(
        default=None, description="Reason if no results (e.g., strict_gate_empty)"
    )


class SeatResult(BaseModel):
    """Result for a single seat in project search."""

    seat_index: int = Field(..., description="Seat index in the project")
    role: str = Field(..., description="Role being searched")
    seniority: Optional[str] = Field(default=None, description="Required seniority")
    results: List[CandidateResult] = Field(
        default_factory=list, description="Candidates for this seat"
    )
    metrics: Optional[SearchMetrics] = Field(default=None, description="Seat search metrics")
    gap: bool = Field(default=False, description="True if no candidates found")


class ProjectSearchResponse(BaseModel):
    """Response for multi-seat project search."""

    run_id: str = Field(..., description="Unique run identifier")
    status: str = Field(..., description="Search status (ok, error, skipped)")
    criteria: Dict[str, Any] = Field(..., description="Derived project criteria")
    seats: List[SeatResult] = Field(default_factory=list, description="Results per seat")
    gaps: List[int] = Field(default_factory=list, description="Indices of seats with no candidates")
    note: Optional[str] = Field(default=None, description="Additional notes or warnings")
    reason: Optional[str] = Field(default=None, description="Reason if skipped/failed")


class PresaleSearchResponse(BaseModel):
    """Response for presale team search."""

    run_id: str = Field(..., description="Unique run identifier")
    status: str = Field(..., description="Search status (ok, skipped, failed)")
    criteria: Dict[str, Any] = Field(..., description="Presale criteria with team plan")
    seats: List[SeatResult] = Field(default_factory=list, description="Results per seat")
    gaps: List[int] = Field(default_factory=list, description="Indices of seats with no candidates")
    presale_rationale: Optional[str] = Field(
        default=None, description="LLM rationale for team composition"
    )
    note: Optional[str] = Field(default=None, description="Additional notes or warnings")
    reason: Optional[str] = Field(default=None, description="Reason if skipped/failed")


# -----------------------------------------------------------------------------
# Error Response
# -----------------------------------------------------------------------------


class ErrorResponse(BaseModel):
    """Standard error response."""

    error: str = Field(..., description="Error message")
    code: str = Field(..., description="Error code")
    detail: Optional[str] = Field(default=None, description="Additional error details")
