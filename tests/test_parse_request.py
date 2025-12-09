from cv_search.core.parser import parse_request
from cv_search.config.settings import Settings
from cv_search.core.criteria import SeniorityEnum


class _StubClient:
    def __init__(self, payload):
        self.payload = payload

    def get_structured_criteria(self, text: str, model: str, settings: Settings):
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
