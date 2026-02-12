import json

from cv_search.clients.openai_client import OpenAIClient, StubOpenAIBackend
from cv_search.config.settings import Settings
from cv_search.core.parser import parse_request


def test_parse_request_include_presale_sets_team_arrays_and_rationale_from_fixture():
    settings = Settings()
    client = OpenAIClient(settings, backend=StubOpenAIBackend(settings))

    crit = parse_request(
        text="any brief",
        model=settings.openai_model,
        settings=settings,
        client=client,
        include_presale=True,
    )

    assert crit.minimum_team == ["ai_solution_architect", "business_analyst"]
    assert crit.extended_team == [
        "data_privacy_expert",
        "integration_specialist",
        "project_manager",
    ]
    expected = "Stubbed presale plan: start with AI/BA core, extend with privacy, integration, and delivery oversight."
    assert crit.presale_rationale == expected
    assert json.loads(crit.to_json())["presale_rationale"] == expected
