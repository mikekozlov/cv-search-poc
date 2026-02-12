import json

from cv_search.core.criteria import Criteria, SeniorityEnum, TeamMember, TeamSize
from cv_search.presale import build_presale_search_criteria


def test_build_presale_search_criteria_builds_seats_from_minimum_and_extended():
    criteria = Criteria(
        domain=["fintech"],
        tech_stack=["python", "react", "flutter", "gdpr", "postgresql"],
        expert_roles=[],
        project_type="greenfield",
        team_size=None,
        minimum_team=["backend_engineer", "data_privacy_expert"],
        extended_team=["project_manager"],
        presale_rationale="why",
    )

    out = build_presale_search_criteria(criteria, include_extended=True)

    assert out.team_size is not None
    assert out.team_size.total == 3
    assert [m.role for m in out.team_size.members] == [
        "backend_engineer",
        "data_privacy_expert",
        "project_manager",
    ]
    assert all(m.seniority == SeniorityEnum.senior for m in out.team_size.members)
    assert all(m.domains == ["fintech"] for m in out.team_size.members)
    backend = out.team_size.members[0]
    privacy = out.team_size.members[1]
    manager = out.team_size.members[2]
    assert "python" in backend.tech_tags
    assert "gdpr" in backend.nice_to_have
    assert "postgresql" in backend.nice_to_have
    assert "gdpr" in privacy.tech_tags
    assert "react" in manager.nice_to_have
    assert "flutter" in manager.nice_to_have
    assert out.presale_rationale == "why"

    payload = json.loads(out.to_json())
    assert payload["team_size"]["total"] == 3
    assert payload["presale_rationale"] == "why"


def test_build_presale_search_criteria_dedupes_roles_and_can_skip_extended():
    criteria = Criteria(
        domain=["healthtech"],
        tech_stack=["dotnet", "kafka", "redis"],
        expert_roles=["backend_engineer"],
        project_type=None,
        team_size=TeamSize(
            total=1,
            members=[
                TeamMember(
                    role="backend_engineer",
                    tech_tags=["kafka"],
                    nice_to_have=["redis"],
                )
            ],
        ),
        minimum_team=["backend_engineer"],
        extended_team=["backend_engineer", "project_manager"],
    )

    out = build_presale_search_criteria(criteria, include_extended=False)

    assert out.team_size is not None
    assert [m.role for m in out.team_size.members] == ["backend_engineer"]
    member = out.team_size.members[0]
    assert "dotnet" in member.tech_tags
    assert "kafka" in member.tech_tags
    assert "redis" in member.nice_to_have
    assert out.expert_roles == ["backend_engineer"]
