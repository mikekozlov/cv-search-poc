import pytest

from cv_search.clients.openai_client import OpenAIClient, StubOpenAIBackend
from cv_search.config.settings import Settings
from cv_search.core.criteria import Criteria
from cv_search.planner.service import Planner


def test_presale_plan_enriches_criteria_with_llm_stub():
    settings = Settings()
    client = OpenAIClient(settings, backend=StubOpenAIBackend(settings))
    planner = Planner()

    criteria = Criteria(
        domain=["manufacturing"],
        tech_stack=["python"],
        expert_roles=["ai_developer"],
        project_type="greenfield",
        team_size=None,
    )

    enriched = planner.derive_presale_team(
        criteria,
        raw_text="AI system with Outlook integration plus privacy requirements.",
        client=client,
        settings=settings,
    )

    assert (
        enriched.presale_rationale
        == "Stubbed presale plan: start with AI/BA core, extend with privacy, integration, and delivery oversight."
    )
    assert enriched.minimum_team == ["ai_solution_architect", "business_analyst"]
    assert enriched.extended_team == [
        "data_privacy_expert",
        "integration_specialist",
        "project_manager",
    ]
    assert enriched.expert_roles == [
        "ai_developer",
        "ai_solution_architect",
        "business_analyst",
        "data_privacy_expert",
        "integration_specialist",
        "project_manager",
    ]


def test_presale_plan_raises_when_llm_returns_no_minimum(monkeypatch):
    settings = Settings()
    client = OpenAIClient(settings, backend=StubOpenAIBackend(settings))
    planner = Planner()

    criteria = Criteria(
        domain=[],
        tech_stack=[],
        expert_roles=[],
        project_type=None,
        team_size=None,
    )

    monkeypatch.setattr(
        client,
        "get_presale_team_plan",
        lambda **kwargs: {"minimum_team": [], "extended_team": []},
    )

    with pytest.raises(ValueError):
        planner.derive_presale_team(
            criteria,
            raw_text="",
            client=client,
            settings=settings,
        )
