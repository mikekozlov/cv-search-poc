import json

from cv_search.search.artifacts import SearchRunArtifactWriter


def test_search_run_artifact_writer_persists_criteria_json(tmp_path):
    writer = SearchRunArtifactWriter()
    criteria = {
        "domain": ["fintech"],
        "tech_stack": ["python"],
        "expert_roles": ["backend_engineer"],
        "project_type": "greenfield",
        "team_size": {
            "total": 1,
            "members": [
                {
                    "role": "backend_engineer",
                    "seniority": "senior",
                    "domains": ["fintech"],
                    "tech_tags": ["python"],
                    "nice_to_have": [],
                }
            ],
        },
    }
    payload = {
        "criteria": criteria,
        "gating_sql": "select 1",
        "ranking_sql": "select 2",
        "vs_query": "backend engineer",
        "vs_sql": "select 3",
    }

    writer.write(tmp_path, payload)

    saved = json.loads((tmp_path / "criteria.json").read_text(encoding="utf-8"))
    assert saved == criteria
    assert (tmp_path / "gating.sql.txt").read_text(encoding="utf-8") == "select 1\n"
    assert (tmp_path / "ranking.sql.txt").read_text(encoding="utf-8") == "select 2\n"
    assert (tmp_path / "vs.query.txt").read_text(encoding="utf-8") == "backend engineer\n"
    assert (tmp_path / "vs.sql.txt").read_text(encoding="utf-8") == "select 3\n"
