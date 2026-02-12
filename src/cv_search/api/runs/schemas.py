"""Pydantic schemas for runs API requests and responses."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


# -----------------------------------------------------------------------------
# Enums
# -----------------------------------------------------------------------------


class RunStatus(str, Enum):
    """Possible run statuses."""

    running = "running"
    succeeded = "succeeded"
    failed = "failed"


class FeedbackSentiment(str, Enum):
    """Feedback sentiment options."""

    like = "like"
    dislike = "dislike"


# -----------------------------------------------------------------------------
# Request Models
# -----------------------------------------------------------------------------


class ListRunsParams(BaseModel):
    """Query parameters for listing runs."""

    limit: int = Field(default=50, ge=1, le=500, description="Maximum runs to return")
    status: Optional[RunStatus] = Field(default=None, description="Filter by status")
    kind: Optional[str] = Field(default=None, description="Filter by run kind")


class SubmitFeedbackRequest(BaseModel):
    """Request body for submitting feedback on a run."""

    sentiment: FeedbackSentiment = Field(..., description="Feedback sentiment (like/dislike)")
    comment: Optional[str] = Field(
        default=None,
        max_length=2000,
        description="Optional feedback comment",
    )


# -----------------------------------------------------------------------------
# Response Models
# -----------------------------------------------------------------------------


class RunListItem(BaseModel):
    """Summary of a search run for listing."""

    run_id: str = Field(..., description="Unique run identifier")
    run_kind: str = Field(..., description="Type of run (single_seat_search, project_search, etc.)")
    status: str = Field(default="running", description="Run status")
    created_at: datetime = Field(..., description="When the run was created")
    completed_at: Optional[datetime] = Field(default=None, description="When the run completed")
    duration_ms: Optional[int] = Field(default=None, description="Run duration in milliseconds")
    result_count: Optional[int] = Field(default=None, description="Number of results returned")
    user_email: Optional[str] = Field(default=None, description="User who initiated the run")
    raw_text_preview: Optional[str] = Field(default=None, description="First 200 chars of raw text")
    feedback_sentiment: Optional[str] = Field(default=None, description="User feedback sentiment")
    note: Optional[str] = Field(default=None, description="Run notes or warnings")


class RunDetail(BaseModel):
    """Full details of a search run."""

    run_id: str = Field(..., description="Unique run identifier")
    run_kind: str = Field(..., description="Type of run")
    run_dir: Optional[str] = Field(default=None, description="Artifact storage directory")
    status: str = Field(default="running", description="Run status")
    created_at: datetime = Field(..., description="When the run was created")
    completed_at: Optional[datetime] = Field(default=None, description="When the run completed")
    duration_ms: Optional[int] = Field(default=None, description="Run duration in milliseconds")
    result_count: Optional[int] = Field(default=None, description="Number of results returned")
    user_email: Optional[str] = Field(default=None, description="User who initiated the run")

    # Search parameters
    criteria: Optional[Dict[str, Any]] = Field(default=None, description="Search criteria used")
    raw_text: Optional[str] = Field(default=None, description="Original brief text")
    top_k: Optional[int] = Field(default=None, description="Top-K parameter used")
    seat_count: Optional[int] = Field(default=None, description="Number of seats searched")
    note: Optional[str] = Field(default=None, description="Run notes or warnings")

    # Error information
    error_type: Optional[str] = Field(default=None, description="Error type if failed")
    error_message: Optional[str] = Field(default=None, description="Error message if failed")
    error_stage: Optional[str] = Field(default=None, description="Stage where error occurred")

    # Feedback
    feedback_sentiment: Optional[str] = Field(default=None, description="User feedback sentiment")
    feedback_comment: Optional[str] = Field(default=None, description="User feedback comment")
    feedback_submitted_at: Optional[datetime] = Field(
        default=None, description="When feedback was submitted"
    )


class ListRunsResponse(BaseModel):
    """Response for listing runs."""

    runs: List[RunListItem] = Field(default_factory=list, description="List of runs")
    total: int = Field(default=0, description="Total number of runs returned")


class FeedbackResponse(BaseModel):
    """Response for feedback submission."""

    success: bool = Field(..., description="Whether feedback was submitted successfully")
    run_id: str = Field(..., description="Run that received feedback")
    message: str = Field(default="Feedback submitted", description="Status message")
