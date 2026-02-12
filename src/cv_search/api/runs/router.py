"""Runs API endpoints for browsing search history and submitting feedback."""

from __future__ import annotations

import json
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from cv_search.api.deps import DBDep
from cv_search.api.runs.schemas import (
    FeedbackResponse,
    ListRunsResponse,
    RunDetail,
    RunListItem,
    RunStatus,
    SubmitFeedbackRequest,
)

router = APIRouter()


def _row_to_list_item(row: dict) -> RunListItem:
    """Convert a database row to RunListItem."""
    raw_text = row.get("raw_text")
    raw_text_preview = raw_text[:200] if raw_text else None

    return RunListItem(
        run_id=row["run_id"],
        run_kind=row.get("run_kind", "unknown"),
        status=row.get("status", "running"),
        created_at=row["created_at"],
        completed_at=row.get("completed_at"),
        duration_ms=row.get("duration_ms"),
        result_count=row.get("result_count"),
        user_email=row.get("user_email"),
        raw_text_preview=raw_text_preview,
        feedback_sentiment=row.get("feedback_sentiment"),
        note=row.get("note"),
    )


def _row_to_detail(row: dict) -> RunDetail:
    """Convert a database row to RunDetail."""
    criteria = None
    criteria_json = row.get("criteria_json")
    if criteria_json:
        try:
            criteria = json.loads(criteria_json)
        except (json.JSONDecodeError, TypeError):
            pass

    return RunDetail(
        run_id=row["run_id"],
        run_kind=row.get("run_kind", "unknown"),
        run_dir=row.get("run_dir"),
        status=row.get("status", "running"),
        created_at=row["created_at"],
        completed_at=row.get("completed_at"),
        duration_ms=row.get("duration_ms"),
        result_count=row.get("result_count"),
        user_email=row.get("user_email"),
        criteria=criteria,
        raw_text=row.get("raw_text"),
        top_k=row.get("top_k"),
        seat_count=row.get("seat_count"),
        note=row.get("note"),
        error_type=row.get("error_type"),
        error_message=row.get("error_message"),
        error_stage=row.get("error_stage"),
        feedback_sentiment=row.get("feedback_sentiment"),
        feedback_comment=row.get("feedback_comment"),
        feedback_submitted_at=row.get("feedback_submitted_at"),
    )


@router.get("/", response_model=ListRunsResponse)
def list_runs(
    db: DBDep,
    limit: int = Query(default=50, ge=1, le=500, description="Maximum runs to return"),
    status: Optional[RunStatus] = Query(default=None, description="Filter by status"),
    kind: Optional[str] = Query(default=None, description="Filter by run kind"),
) -> ListRunsResponse:
    """
    List recent search runs.

    Returns a paginated list of search runs ordered by creation time (newest first).
    Use query parameters to filter by status or run kind.
    """
    try:
        rows = db.list_search_runs(
            limit=limit,
            status=status.value if status else None,
            kind=kind,
        )

        runs = [_row_to_list_item(row) for row in rows]

        return ListRunsResponse(
            runs=runs,
            total=len(runs),
        )

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to list runs: {str(e)}",
        )


@router.get("/{run_id}", response_model=RunDetail)
def get_run(
    run_id: str,
    db: DBDep,
) -> RunDetail:
    """
    Get full details of a specific search run.

    Returns all information about the run including criteria, parameters,
    status, errors (if any), and feedback.
    """
    try:
        row = db.get_search_run(run_id=run_id)

        if not row:
            raise HTTPException(
                status_code=404,
                detail=f"Run '{run_id}' not found",
            )

        return _row_to_detail(row)

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get run: {str(e)}",
        )


@router.post("/{run_id}/feedback", response_model=FeedbackResponse)
def submit_feedback(
    run_id: str,
    request: SubmitFeedbackRequest,
    db: DBDep,
) -> FeedbackResponse:
    """
    Submit feedback for a search run.

    Allows users to provide feedback (like/dislike) on search results
    to help improve the system.
    """
    try:
        # Verify run exists
        row = db.get_search_run(run_id=run_id)
        if not row:
            raise HTTPException(
                status_code=404,
                detail=f"Run '{run_id}' not found",
            )

        # Update feedback
        db.update_search_run_feedback(
            run_id=run_id,
            sentiment=request.sentiment.value,
            comment=request.comment,
        )

        return FeedbackResponse(
            success=True,
            run_id=run_id,
            message=f"Feedback ({request.sentiment.value}) submitted successfully",
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to submit feedback: {str(e)}",
        )
