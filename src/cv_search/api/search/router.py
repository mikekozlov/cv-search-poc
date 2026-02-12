"""Search API endpoints."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException

from cv_search.api.deps import ClientDep, PlannerDep, ProcessorDep, SettingsDep
from cv_search.api.search.schemas import (
    CandidateResult,
    PresaleSearchRequest,
    PresaleSearchResponse,
    ProjectSearchRequest,
    ProjectSearchResponse,
    SearchMetrics,
    SeatResult,
    SeatSearchRequest,
    SeatSearchResponse,
)
from cv_search.core.cv_markdown import build_cv_markdown
from cv_search.core.parser import parse_request
from cv_search.db.database import CVDatabase
from cv_search.presale import build_presale_search_criteria
from cv_search.search.processor import default_run_dir

logger = logging.getLogger("cv_search.api.search")

router = APIRouter()


def _extract_candidate_results(raw_results: list[dict[str, Any]]) -> list[CandidateResult]:
    """Convert raw search results to CandidateResult schemas.

    Passes through the full data structure from the search processor,
    matching what Streamlit receives in results.json.
    """
    candidates = []
    for r in raw_results:
        # Normalize score to dict format if it's a plain value
        score = r.get("score", {})
        if not isinstance(score, dict):
            score = {"value": float(score) if score else 0.0, "order": 0}

        candidates.append(
            CandidateResult(
                candidate_id=r.get("candidate_id", ""),
                score=score,
                score_components=r.get("score_components"),
                must_have=r.get("must_have", {}),
                nice_to_have=r.get("nice_to_have", {}),
                recency=r.get("recency"),
                llm_justification=r.get("llm_justification"),
            )
        )
    return candidates


def _enrich_candidate_results(
    candidates: list[CandidateResult],
    db: CVDatabase,
    *,
    include_cv_markdown: bool = True,
) -> None:
    """Enrich candidate results in-place with name, source_file, and optionally cv_markdown."""
    if not candidates:
        return

    cids = [c.candidate_id for c in candidates]
    profiles = db.get_candidate_profiles(cids)

    if include_cv_markdown:
        contexts = db.get_full_candidate_contexts(cids)
        experiences = db.get_candidate_experiences_bulk(cids)
        qualifications = db.get_candidate_qualifications_bulk(cids)
        tags = db.get_candidate_tags_bulk(cids)

    for c in candidates:
        cid = c.candidate_id
        profile = profiles.get(cid)

        c.name = profile.get("name") if profile else None
        c.source_file = (
            profile.get("source_gdrive_path") or profile.get("source_filename") if profile else None
        )
        if include_cv_markdown:
            context = contexts.get(cid)
            c.cv_markdown = build_cv_markdown(
                candidate_id=cid,
                profile=profile,
                context=context,
                experiences=experiences.get(cid, []),
                qualifications=qualifications.get(cid, {}),
                tags=tags.get(cid, {}),
            )
        else:
            c.cv_markdown = None


def _extract_metrics(payload: dict[str, Any]) -> SearchMetrics:
    """Extract search metrics from payload."""
    metrics = payload.get("metrics", {})
    return SearchMetrics(
        gate_count=metrics.get("gate_count", 0),
        lex_fanin=metrics.get("lex_fanin", 0),
        pool_size=metrics.get("pool_size", 0),
        mode=metrics.get("mode", "llm"),
        duration_ms=metrics.get("duration_ms"),
    )


@router.post("/seat", response_model=SeatSearchResponse, include_in_schema=False)
def search_seat(
    request: SeatSearchRequest,
    processor: ProcessorDep,
    settings: SettingsDep,
) -> SeatSearchResponse:
    """
    Single-seat candidate search.

    Performs strict gating (role, seniority, must-have tags) followed by
    lexical retrieval and LLM verdict ranking.

    Returns ranked candidates with optional LLM-generated justifications.
    """
    try:
        logger.info("Seat search: top_k=%d", request.top_k)
        run_dir = default_run_dir(settings.active_runs_dir)
        criteria_dict = request.criteria.model_dump(exclude_none=True)

        payload = processor.search_for_seat(
            criteria=criteria_dict,
            top_k=request.top_k,
            run_dir=run_dir,
        )

        status = payload.get("status", "ok")
        if status == "failed":
            logger.warning("Seat search failed: %s", payload.get("error") or payload.get("reason"))

        results = _extract_candidate_results(payload.get("results", []))
        _enrich_candidate_results(
            results, processor.db, include_cv_markdown=request.include_cv_markdown
        )

        return SeatSearchResponse(
            run_id=payload.get("run_id", ""),
            status=status,
            criteria=payload.get("criteria", criteria_dict),
            results=results,
            metrics=_extract_metrics(payload),
            reason=payload.get("reason"),
        )

    except Exception as e:
        logger.error("Seat search exception: %s", e, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Search failed: {str(e)}",
        )


@router.post("/project", response_model=ProjectSearchResponse)
def search_project(
    request: ProjectSearchRequest,
    processor: ProcessorDep,
    client: ClientDep,
    settings: SettingsDep,
) -> ProjectSearchResponse:
    """
    Multi-seat project search.

    Accepts a natural language project brief, derives team seats,
    and performs search for each seat.

    Returns results organized by seat with gap detection for unfilled roles.
    """
    try:
        logger.info("Project search: top_k=%d, text=%r", request.top_k, request.text[:120])
        run_dir = default_run_dir(settings.active_runs_dir)

        # Parse free-text brief into Criteria so derive_project_seats gets a real object
        criteria = parse_request(
            request.text,
            model=settings.openai_model,
            settings=settings,
            client=client,
            run_dir=run_dir,
        )

        payload = processor.search_for_project(
            criteria=criteria,
            top_k=request.top_k,
            run_dir=run_dir,
            raw_text=request.text,
        )

        status = payload.get("status", "ok")
        if status == "failed":
            logger.warning(
                "Project search failed: %s", payload.get("error") or payload.get("reason")
            )

        # Convert seats to SeatResult format
        seat_results = []
        raw_seats = payload.get("seats", [])
        for idx, seat in enumerate(raw_seats):
            results = _extract_candidate_results(seat.get("results", []))
            seat_results.append(
                SeatResult(
                    seat_index=idx,
                    role=seat.get("role", ""),
                    seniority=seat.get("seniority"),
                    results=results,
                    metrics=_extract_metrics(seat) if "metrics" in seat else None,
                    gap=idx in payload.get("gaps", []),
                )
            )

        # Enrich all candidates across all seats in one batch
        all_candidates = [c for s in seat_results for c in s.results]
        _enrich_candidate_results(
            all_candidates, processor.db, include_cv_markdown=request.include_cv_markdown
        )

        return ProjectSearchResponse(
            run_id=payload.get("run_id", ""),
            status=status,
            criteria=payload.get("project_criteria") or {},
            seats=seat_results,
            gaps=payload.get("gaps", []),
            note=payload.get("note"),
            reason=payload.get("reason"),
        )

    except Exception as e:
        logger.error("Project search exception: %s", e, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Project search failed: {str(e)}",
        )


@router.post("/presale", response_model=PresaleSearchResponse)
def search_presale(
    request: PresaleSearchRequest,
    processor: ProcessorDep,
    planner: PlannerDep,
    client: ClientDep,
    settings: SettingsDep,
) -> PresaleSearchResponse:
    """
    Presale team search.

    Generates a presale team plan from the project brief using LLM,
    then searches for candidates for each role in the minimum and
    extended teams.

    Returns candidates organized by team tier with the presale rationale.
    """
    try:
        logger.info("Presale search: top_k=%d, text=%r", request.top_k, request.text[:120])
        run_dir = default_run_dir(settings.active_runs_dir, subdir="presale")

        # Parse brief and generate presale plan
        crit = parse_request(
            request.text,
            model=settings.openai_model,
            settings=settings,
            client=client,
            include_presale=True,
        )

        # Derive presale team via LLM
        raw_text_en = getattr(crit, "_english_brief", None) or request.text
        crit_with_plan = planner.derive_presale_team(
            crit,
            raw_text=raw_text_en,
            client=client,
            settings=settings,
        )

        # Build search criteria from presale plan
        search_criteria = build_presale_search_criteria(
            crit_with_plan,
            include_extended=request.include_extended,
        )

        # Run project search with derived criteria
        payload = processor.search_for_project(
            criteria=search_criteria,
            top_k=request.top_k,
            run_dir=run_dir,
            raw_text=request.text,
            run_kind="presale_search",
        )

        status = payload.get("status", "ok")
        if status == "failed":
            logger.warning(
                "Presale search failed: %s", payload.get("error") or payload.get("reason")
            )

        # Convert seats to SeatResult format
        criteria_dict = planner._criteria_dict(crit_with_plan)

        seat_results = []
        raw_seats = payload.get("seats", [])
        for idx, seat in enumerate(raw_seats):
            results = _extract_candidate_results(seat.get("results", []))
            seat_results.append(
                SeatResult(
                    seat_index=idx,
                    role=seat.get("role", ""),
                    seniority=seat.get("seniority"),
                    results=results,
                    metrics=_extract_metrics(seat) if "metrics" in seat else None,
                    gap=idx in payload.get("gaps", []),
                )
            )

        # Enrich all candidates across all seats in one batch
        all_candidates = [c for s in seat_results for c in s.results]
        _enrich_candidate_results(
            all_candidates, processor.db, include_cv_markdown=request.include_cv_markdown
        )

        return PresaleSearchResponse(
            run_id=payload.get("run_id", ""),
            status=status,
            criteria=criteria_dict,
            seats=seat_results,
            gaps=payload.get("gaps", []),
            presale_rationale=criteria_dict.get("presale_rationale"),
            note=payload.get("note"),
            reason=payload.get("reason"),
        )

    except Exception as e:
        logger.error("Presale search exception: %s", e, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Presale search failed: {str(e)}",
        )
