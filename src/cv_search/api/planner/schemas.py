"""Pydantic schemas for planner API requests and responses."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from cv_search.api.search.schemas import CriteriaSchema, TeamMemberSchema


# -----------------------------------------------------------------------------
# Request Models
# -----------------------------------------------------------------------------


class ParseBriefRequest(BaseModel):
    """Request body for parsing a natural language brief into criteria."""

    text: str = Field(
        ...,
        min_length=10,
        max_length=10000,
        description="Natural language project brief",
    )
    include_presale: bool = Field(
        default=False,
        description="Include presale team planning (minimum_team, extended_team)",
    )


class DeriveSeatsRequest(BaseModel):
    """Request body for deriving project seats from criteria."""

    criteria: CriteriaSchema = Field(..., description="Input criteria")
    raw_text: Optional[str] = Field(
        default=None,
        max_length=10000,
        description="Optional raw text to help with seat derivation",
    )


class PresalePlanRequest(BaseModel):
    """Request body for generating a presale team plan."""

    text: str = Field(
        ...,
        min_length=10,
        max_length=10000,
        description="Natural language project brief",
    )
    model: Optional[str] = Field(
        default=None,
        description="LLM model to use (defaults to settings.openai_model)",
    )


# -----------------------------------------------------------------------------
# Response Models
# -----------------------------------------------------------------------------


class ParseBriefResponse(BaseModel):
    """Response for brief parsing."""

    criteria: CriteriaSchema = Field(..., description="Parsed criteria")
    english_brief: Optional[str] = Field(
        default=None,
        description="English translation of the brief (if input was non-English)",
    )


class DeriveSeatsResponse(BaseModel):
    """Response for seat derivation."""

    criteria: CriteriaSchema = Field(..., description="Criteria with derived seats")
    seats: List[TeamMemberSchema] = Field(
        default_factory=list,
        description="List of derived team seats",
    )
    seat_count: int = Field(default=0, description="Number of seats derived")


class PresalePlanResponse(BaseModel):
    """Response for presale team planning."""

    criteria: Dict[str, Any] = Field(..., description="Full criteria with presale plan")
    minimum_team: List[str] = Field(
        default_factory=list,
        description="Minimum required team roles",
    )
    extended_team: List[str] = Field(
        default_factory=list,
        description="Extended team roles for full scope",
    )
    presale_rationale: Optional[str] = Field(
        default=None,
        description="LLM-generated rationale for team composition",
    )
    run_dir: Optional[str] = Field(
        default=None,
        description="Directory where artifacts are stored",
    )
