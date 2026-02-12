"""Planner API endpoints for brief parsing and team derivation."""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict

from fastapi import APIRouter, HTTPException

from cv_search.api.deps import ClientDep, PlannerDep, SettingsDep
from cv_search.api.planner.schemas import (
    DeriveSeatsRequest,
    DeriveSeatsResponse,
    ParseBriefRequest,
    ParseBriefResponse,
    PresalePlanRequest,
    PresalePlanResponse,
)
from cv_search.api.search.schemas import CriteriaSchema, TeamMemberSchema
from cv_search.core.parser import parse_request
from cv_search.search.processor import default_run_dir

router = APIRouter()


def _criteria_to_schema(crit) -> CriteriaSchema:
    """Convert a Criteria dataclass to CriteriaSchema."""
    from cv_search.core.criteria import Criteria

    if isinstance(crit, Criteria):
        crit_dict = asdict(crit)
    elif isinstance(crit, dict):
        crit_dict = crit
    else:
        crit_dict = {}

    # Handle enum conversion for seniority
    team_size = crit_dict.get("team_size")
    if team_size and isinstance(team_size, dict):
        members = team_size.get("members", [])
        for member in members:
            if member.get("seniority") and hasattr(member["seniority"], "value"):
                member["seniority"] = member["seniority"].value

    return CriteriaSchema.model_validate(crit_dict)


def _criteria_to_dict(crit) -> Dict[str, Any]:
    """Convert a Criteria dataclass to dict, handling enums."""
    from cv_search.core.criteria import Criteria

    if isinstance(crit, Criteria):
        crit_dict = asdict(crit)
    elif isinstance(crit, dict):
        crit_dict = crit
    else:
        crit_dict = {}

    # Convert enum values to strings
    team_size = crit_dict.get("team_size")
    if team_size and isinstance(team_size, dict):
        members = team_size.get("members", [])
        for member in members:
            if member.get("seniority") and hasattr(member["seniority"], "value"):
                member["seniority"] = member["seniority"].value

    return crit_dict


@router.post("/parse-brief", response_model=ParseBriefResponse)
def parse_brief(
    request: ParseBriefRequest,
    client: ClientDep,
    settings: SettingsDep,
) -> ParseBriefResponse:
    """
    Parse a natural language project brief into structured criteria.

    Extracts domain, tech stack, expert roles, and team composition from
    free-form text using LLM-powered parsing.

    Set `include_presale=true` to also extract presale team planning
    (minimum_team, extended_team).
    """
    try:
        crit = parse_request(
            text=request.text,
            model=settings.openai_model,
            settings=settings,
            client=client,
            include_presale=request.include_presale,
        )

        english_brief = getattr(crit, "_english_brief", None)

        return ParseBriefResponse(
            criteria=_criteria_to_schema(crit),
            english_brief=english_brief,
        )

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to parse brief: {str(e)}",
        )


@router.post("/derive-seats", response_model=DeriveSeatsResponse)
def derive_seats(
    request: DeriveSeatsRequest,
    planner: PlannerDep,
) -> DeriveSeatsResponse:
    """
    Derive project seats from criteria.

    Uses deterministic rules to infer team composition based on tech stack,
    domain, and other signals in the criteria.

    Returns the criteria enriched with team_size.members if seats were derived.
    """
    try:
        from cv_search.core.criteria import Criteria, SeniorityEnum, TeamMember, TeamSize

        # Convert request criteria to Criteria dataclass
        crit_dict = request.criteria.model_dump(exclude_none=True)

        # Build TeamSize if present
        team_size = None
        if crit_dict.get("team_size"):
            ts = crit_dict["team_size"]
            members = []
            for m in ts.get("members", []):
                seniority = None
                if m.get("seniority"):
                    try:
                        seniority = SeniorityEnum(m["seniority"])
                    except ValueError:
                        pass
                members.append(
                    TeamMember(
                        role=m.get("role", ""),
                        seniority=seniority,
                        domains=m.get("domains", []),
                        tech_tags=m.get("tech_tags", []),
                        nice_to_have=m.get("nice_to_have", []),
                        rationale=m.get("rationale"),
                    )
                )
            team_size = TeamSize(total=ts.get("total"), members=members)

        crit = Criteria(
            domain=crit_dict.get("domain", []),
            tech_stack=crit_dict.get("tech_stack", []),
            expert_roles=crit_dict.get("expert_roles", []),
            project_type=crit_dict.get("project_type"),
            team_size=team_size,
            minimum_team=crit_dict.get("minimum_team", []),
            extended_team=crit_dict.get("extended_team", []),
            presale_rationale=crit_dict.get("presale_rationale"),
        )

        # Derive seats
        result = planner.derive_project_seats(crit, raw_text=request.raw_text)

        # Extract seats
        seats = []
        if result.team_size and result.team_size.members:
            for m in result.team_size.members:
                seats.append(
                    TeamMemberSchema(
                        role=m.role,
                        seniority=m.seniority.value if m.seniority else None,
                        domains=m.domains,
                        tech_tags=m.tech_tags,
                        nice_to_have=m.nice_to_have,
                        rationale=m.rationale,
                    )
                )

        return DeriveSeatsResponse(
            criteria=_criteria_to_schema(result),
            seats=seats,
            seat_count=len(seats),
        )

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to derive seats: {str(e)}",
        )


@router.post("/presale-plan", response_model=PresalePlanResponse)
def presale_plan(
    request: PresalePlanRequest,
    planner: PlannerDep,
    client: ClientDep,
    settings: SettingsDep,
) -> PresalePlanResponse:
    """
    Generate a presale team plan from a project brief.

    Uses LLM to analyze the brief and derive:
    - minimum_team: Essential roles required for project delivery
    - extended_team: Additional roles for full scope coverage
    - presale_rationale: Explanation of team composition

    This endpoint does NOT perform candidate search - use `/search/presale`
    for that.
    """
    try:
        run_dir = default_run_dir(settings.active_runs_dir, subdir=None)

        # Parse brief with presale flag
        crit = parse_request(
            text=request.text,
            model=request.model or settings.openai_model,
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
            model=request.model,
        )

        # Write criteria to run directory
        Path(run_dir).mkdir(parents=True, exist_ok=True)
        criteria_path = Path(run_dir) / "criteria.json"
        criteria_path.write_text(crit_with_plan.to_json(), encoding="utf-8")

        criteria_dict = _criteria_to_dict(crit_with_plan)

        return PresalePlanResponse(
            criteria=criteria_dict,
            minimum_team=crit_with_plan.minimum_team,
            extended_team=crit_with_plan.extended_team,
            presale_rationale=crit_with_plan.presale_rationale,
            run_dir=run_dir,
        )

    except ValueError as e:
        raise HTTPException(
            status_code=400,
            detail=str(e),
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to generate presale plan: {str(e)}",
        )
