from cv_search.clients.openai_client import OpenAIClient, StubOpenAIBackend
from cv_search.config.settings import Settings
from cv_search.core.criteria import Criteria
from cv_search.planner.service import Planner
from cv_search.retrieval.embedder_stub import DeterministicEmbedder
from cv_search.search.processor import SearchProcessor


def test_derive_project_seats_returns_zero_for_unknown_brief():
    planner = Planner()
    crit = Criteria(
        domain=[],
        tech_stack=[],
        expert_roles=[],
        project_type=None,
        team_size=None,
    )

    out = planner.derive_project_seats(crit, raw_text="airplane pilot")

    assert out.team_size is not None
    assert out.team_size.total == 0
    assert out.team_size.members == []
    assert out.expert_roles == []


def test_search_for_project_returns_empty_payload_when_no_seats(tmp_path):
    settings = Settings()
    client = OpenAIClient(settings, backend=StubOpenAIBackend(settings))

    class _StubDB:
        pass

    processor = SearchProcessor(
        db=_StubDB(),
        client=client,
        settings=settings,
        embedder=DeterministicEmbedder(),
    )

    crit = Criteria(
        domain=[],
        tech_stack=[],
        expert_roles=[],
        project_type=None,
        team_size=None,
    )

    payload = processor.search_for_project(
        criteria=crit,
        top_k=3,
        run_dir=str(tmp_path),
        raw_text="airplane pilot",
        with_justification=False,
    )

    assert payload["seats"] == []
    assert payload["gaps"] == []
    assert payload["reason"] == "low_signal_brief"
