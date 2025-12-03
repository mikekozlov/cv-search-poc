from __future__ import annotations

from cv_search.ingestion.cv_parser import CVParser
from cv_search.db.database import CVDatabase
from tests.integration import helpers


def test_ingest_gdrive_single_file(monkeypatch) -> None:
    settings = helpers.test_settings()
    helpers.ensure_postgres_available(settings)
    helpers.cleanup_test_state(settings)

    env = helpers.test_env()

    def fake_extract_text(self, file_path):
        return "\n".join(
            [
                "Name: Stub Backend",
                "Role: Backend Engineer",
                "Domain: HealthTech projects",
                "Tech: dotnet, postgresql, kafka, kubernetes, python",
            ]
        )

    monkeypatch.setattr(CVParser, "extract_text", fake_extract_text, raising=True)

    pptx_path = helpers.make_inbox_pptx_placeholder(settings, role_folder="backend_engineer", filename="test.pptx")
    expected_candidate_id = helpers.pptx_candidate_id(pptx_path.name)

    helpers.run_cli(["init-db"], env)
    helpers.run_cli(["ingest-gdrive", "--file", pptx_path.name], env)

    db = CVDatabase(settings)
    try:
        row = db.conn.execute(
            "SELECT candidate_id, name, location, seniority, source_filename FROM candidate WHERE source_filename = %s",
            (pptx_path.name,),
        ).fetchone()
        assert row, "Candidate row should exist for ingested PPTX."
        candidate_id = row["candidate_id"]
        assert candidate_id == expected_candidate_id
        assert row["name"] == "Stub Backend"
        assert row["location"] == "Testville"
        assert row["seniority"] == "senior"

        tag_rows = db.conn.execute(
            "SELECT tag_type, tag_key FROM candidate_tag WHERE candidate_id = %s",
            (candidate_id,),
        ).fetchall()
        role_tags = {r["tag_key"] for r in tag_rows if r["tag_type"] == "role"}
        tech_tags = {r["tag_key"] for r in tag_rows if r["tag_type"] == "tech"}
        domain_tags = {r["tag_key"] for r in tag_rows if r["tag_type"] == "domain"}
        seniority_tags = {r["tag_key"] for r in tag_rows if r["tag_type"] == "seniority"}

        assert "backend_engineer" in role_tags
        assert {"dotnet", "postgresql", "kafka"} <= tech_tags
        assert "healthtech" in domain_tags
        assert "senior" in seniority_tags

        exp_row = db.conn.execute(
            "SELECT domain_tags_csv, tech_tags_csv FROM experience WHERE candidate_id = %s",
            (candidate_id,),
        ).fetchone()
        assert exp_row, "Experience row should be written."
        assert "healthtech" in (exp_row["domain_tags_csv"] or "")
        assert "kafka" in (exp_row["tech_tags_csv"] or "")

        doc_row = db.conn.execute(
            "SELECT summary_text, experience_text, tags_text, embedding FROM candidate_doc WHERE candidate_id = %s",
            (candidate_id,),
        ).fetchone()
        assert doc_row, "Candidate doc should be persisted with embedding."
        assert doc_row["embedding"] is not None
        emb = doc_row["embedding"]
        if hasattr(emb, "__len__"):
            assert len(emb) == 384

    finally:
        db.close()

    json_payload = helpers.load_ingested_json(settings, candidate_id)
    assert json_payload["source_filename"] == pptx_path.name
    assert json_payload["role_tags"] == ["backend_engineer"]
