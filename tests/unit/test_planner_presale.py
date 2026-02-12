import pytest

from cv_search.clients.openai_client import OpenAIClient, StubOpenAIBackend
from cv_search.config.settings import Settings
from cv_search.core.criteria import Criteria
from cv_search.planner.service import Planner


def test_derive_presale_team_sets_rationale_when_missing():
    settings = Settings()
    client = OpenAIClient(settings, backend=StubOpenAIBackend(settings))
    planner = Planner()

    crit = Criteria(
        domain=["manufacturing"],
        tech_stack=["python"],
        expert_roles=["ai_developer"],
        project_type="greenfield",
        team_size=None,
    )

    enriched = planner.derive_presale_team(
        crit,
        raw_text="AI system with Outlook integration plus privacy requirements.",
        client=client,
        settings=settings,
    )

    assert (
        enriched.presale_rationale
        == "Stubbed presale plan: start with AI/BA core, extend with privacy, integration, and delivery oversight."
    )
    assert enriched.minimum_team == ["ai_solution_architect", "business_analyst"]


def test_derive_presale_team_preserves_existing_rationale(monkeypatch):
    settings = Settings()
    client = OpenAIClient(settings, backend=StubOpenAIBackend(settings))
    planner = Planner()

    crit = Criteria(
        domain=[],
        tech_stack=[],
        expert_roles=[],
        project_type=None,
        team_size=None,
        presale_rationale="keep-me",
    )

    monkeypatch.setattr(
        client,
        "get_presale_team_plan",
        lambda **kwargs: {
            "minimum_team": ["ai_solution_architect"],
            "extended_team": [],
            "rationale": "overwrite-me",
        },
    )

    enriched = planner.derive_presale_team(
        crit,
        raw_text="",
        client=client,
        settings=settings,
    )

    assert enriched.minimum_team == ["ai_solution_architect"]
    assert enriched.presale_rationale == "keep-me"


def test_derive_presale_team_raises_when_llm_returns_no_minimum(monkeypatch):
    settings = Settings()
    client = OpenAIClient(settings, backend=StubOpenAIBackend(settings))
    planner = Planner()

    crit = Criteria(
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
            crit,
            raw_text="",
            client=client,
            settings=settings,
        )
