import json

from cv_search.clients.openai_client import OpenAIClient, StubOpenAIBackend
from cv_search.core.parser import parse_request
from cv_search.config.settings import Settings
from cv_search.core.criteria import SeniorityEnum


class _StubClient:
    def __init__(self, payload):
        self.payload = payload

    def get_structured_brief(self, text: str, model: str, settings: Settings):
        if "criteria" in self.payload or "presale_team" in self.payload:
            return self.payload
        return {"criteria": self.payload}

    def get_structured_criteria(self, text: str, model: str, settings: Settings):
        if "criteria" in self.payload:
            return self.payload["criteria"]
        return self.payload


def test_parse_request_normalizes_and_fills_team_size_from_roles():
    payload = {
        "domain": ["FinTech", "fintech"],
        "tech_stack": ["Python", "PostgreSQL", "python"],
        "expert_roles": ["Backend_Engineer"],
        "team_size": {},
    }
    crit = parse_request(
        text="need backend",
        model="gpt-4.1-mini",
        settings=Settings(),
        client=_StubClient(payload),
    )

    assert crit.domain == ["fintech"]
    assert crit.tech_stack == ["python", "postgresql"]
    assert crit.expert_roles == ["backend_engineer"]
    assert crit.team_size and crit.team_size.total == 1
    member = crit.team_size.members[0]
    assert member.role == "backend_engineer"
    assert member.seniority == SeniorityEnum.senior
    assert member.domains == ["fintech"]
    assert member.tech_tags == ["python", "postgresql"]


def test_parse_request_normalizes_existing_team_size():
    payload = {
        "domain": ["HealthTech"],
        "tech_stack": ["dotnet", "azure", "dotnet"],
        "expert_roles": ["Backend_Engineer", "backend_engineer"],
        "team_size": {
            "total": 1,
            "members": [
                {
                    "role": "Backend_Engineer",
                    "seniority": "Mid",
                    "domains": ["HealthTech", "healthtech"],
                    "tech_tags": ["Azure", "azure", "DotNet"],
                    "nice_to_have": ["kafka", "Kafka"],
                }
            ],
        },
    }
    crit = parse_request(
        text="need backend mid",
        model="gpt-4.1-mini",
        settings=Settings(),
        client=_StubClient(payload),
    )

    assert crit.domain == ["healthtech"]
    assert crit.tech_stack == ["dotnet", "azure"]
    assert crit.expert_roles == ["backend_engineer"]
    assert crit.team_size and crit.team_size.total == 1
    member = crit.team_size.members[0]
    assert member.role == "backend_engineer"
    assert member.seniority == SeniorityEnum.middle
    assert member.domains == ["healthtech"]
    assert member.tech_tags == ["azure", "dotnet"]
    assert member.nice_to_have == ["kafka"]


def test_parse_request_maps_tech_synonyms_via_reverse_index():
    payload = {
        "domain": ["FinTech"],
        "tech_stack": [
            "Google Analytics/GA4",
            "Custom ETLs",
            "Stripe API",
            "AWS eventbridge",
            "API Design",  # should be dropped (not in lexicon)
        ],
        "expert_roles": ["Backend_Engineer"],
        "team_size": {
            "members": [
                {
                    "role": "Backend_Engineer",
                    "seniority": "Senior",
                    "domains": ["FinTech"],
                    "tech_tags": ["Google Analytics", "GA"],
                    "nice_to_have": ["Stripe API", "Custom ETLs", "Data Vault Modeling"],
                }
            ]
        },
    }
    crit = parse_request(
        text="need fintech backend",
        model="gpt-4.1-mini",
        settings=Settings(),
        client=_StubClient(payload),
    )

    assert crit.tech_stack == ["google_analytics", "etl", "stripe", "aws_eventbridge"]
    assert crit.expert_roles == ["backend_engineer"]
    member = crit.team_size.members[0]
    assert member.tech_tags == ["google_analytics"]
    assert member.nice_to_have == ["stripe", "etl"]
    assert "data vault modeling" not in crit.tech_stack
    assert "api design" not in crit.tech_stack


def test_parse_request_includes_presale_team_from_combined_payload():
    payload = {
        "criteria": {
            "domain": ["HealthTech"],
            "tech_stack": ["python"],
            "expert_roles": ["Backend_Engineer", "non_canonical_role"],
            "team_size": {},
        },
        "presale_team": {
            "minimum_team": ["Backend_Engineer", "unknown_role"],
            "extended_team": ["Data_Privacy_Expert", "random_consultant"],
            "rationale": "Stubbed presale plan...",
        },
    }

    crit = parse_request(
        text="privacy-heavy health project",
        model="gpt-4.1-mini",
        settings=Settings(),
        client=_StubClient(payload),
        include_presale=True,
    )

    assert crit.expert_roles == ["backend_engineer"]
    assert crit.minimum_team == ["backend_engineer"]
    assert crit.extended_team == ["data_privacy_expert"]
    assert crit.presale_rationale == payload["presale_team"]["rationale"]


def test_parse_request_includes_presale_rationale_from_structured_brief_fixture():
    settings = Settings()
    client = OpenAIClient(settings, backend=StubOpenAIBackend(settings))

    crit = parse_request(
        text="any brief",
        model=settings.openai_model,
        settings=settings,
        client=client,
        include_presale=True,
    )

    expected = "Stubbed presale plan: start with AI/BA core, extend with privacy, integration, and delivery oversight."
    assert crit.presale_rationale == expected
    assert json.loads(crit.to_json())["presale_rationale"] == expected


def test_parse_request_attaches_english_brief_when_present():
    payload = {
        "english_brief": "Need a strong Senior .NET developer with AI and Python experience on Azure, 5+ years, for a banking startup.",
        "domain": [],
        "tech_stack": ["dotnet", "python", "azure"],
        "expert_roles": ["Backend_Engineer"],
        "team_size": {},
    }

    crit = parse_request(
        text="Потрібен сильний Senior .NET розробник ...",
        model="gpt-4.1-mini",
        settings=Settings(),
        client=_StubClient(payload),
    )

    assert getattr(crit, "_english_brief", None) == payload["english_brief"]
