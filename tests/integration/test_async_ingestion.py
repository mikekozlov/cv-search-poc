from __future__ import annotations

import shutil

from cv_search.clients.openai_client import OpenAIClient, StubOpenAIBackend
from cv_search.db.database import CVDatabase
from cv_search.ingestion.async_pipeline import (
    QUEUE_DLQ,
    QUEUE_ENRICH_TASK,
    QUEUE_EXTRACT_TASK,
    EnricherWorker,
    ExtractorWorker,
    Watcher,
)
from cv_search.ingestion.parser_stub import StubCVParser
from cv_search.retrieval.embedder_stub import DeterministicEmbedder
from tests.integration.helpers import REPO_ROOT, cleanup_test_state, ensure_postgres_available, test_settings


def test_async_pipeline_ingests_text_samples(redis_client):
    """Run the async ingestion flow against a real Redis-backed queue."""
    settings = test_settings()
    ensure_postgres_available(settings)
    cleanup_test_state(settings)

    db = CVDatabase(settings)
    db.initialize_schema()
    db.close()

    inbox_dir = settings.gdrive_local_dest_dir / "Engineering" / "backend_engineer"
    inbox_dir.mkdir(parents=True, exist_ok=True)
    sample_src = REPO_ROOT / "data/test/pptx_samples/backend_sample.txt"
    sample_dest = inbox_dir / sample_src.name
    shutil.copy(sample_src, sample_dest)

    watcher = Watcher(settings, redis_client)
    try:
        watcher._scan_and_publish()
    finally:
        watcher.close()

    extractor = ExtractorWorker(settings, redis_client, parser=StubCVParser())
    extract_task = redis_client.pop_from_queue(QUEUE_EXTRACT_TASK, timeout=1)
    assert extract_task, "Watcher should enqueue an extract task."
    extractor._process_task(extract_task)

    enricher = EnricherWorker(
        settings,
        redis_client,
        embedder=DeterministicEmbedder(),
        parser=StubCVParser(),
        client=OpenAIClient(settings, backend=StubOpenAIBackend(settings)),
    )
    enrich_task = redis_client.pop_from_queue(QUEUE_ENRICH_TASK, timeout=1)
    assert enrich_task, "Extractor should enqueue an enrich task."
    try:
        enricher._process_task(enrich_task)
    finally:
        enricher.close()

    assert redis_client.client.llen(QUEUE_DLQ) == 0, "DLQ should stay empty for a happy path flow."

    db_check = CVDatabase(settings)
    rows = db_check.conn.execute("SELECT candidate_id FROM candidate").fetchall()
    assert rows, "Candidate should be ingested into Postgres."
    docs = db_check.conn.execute(
        "SELECT COUNT(*) AS c, COUNT(embedding) AS with_emb FROM candidate_doc"
    ).fetchone()
    assert docs["with_emb"] >= 1, "Embedding should be stored in Postgres."

    cand_row = db_check.conn.execute("SELECT candidate_id FROM candidate").fetchone()
    assert cand_row, "Candidate row should exist."
    candidate_id = cand_row["candidate_id"]

    exp_row = db_check.conn.execute(
        "SELECT project_description, responsibilities_text, tech_tags_csv, domain_tags_csv FROM experience WHERE candidate_id = %s",
        (candidate_id,),
    ).fetchone()
    assert exp_row, "Experience row should exist for candidate."
    assert "deterministic" in (exp_row["project_description"] or "")
    assert "Built deterministic APIs" in (exp_row["responsibilities_text"] or "")
    assert "kafka" in (exp_row["tech_tags_csv"] or "")
    assert "healthtech" in (exp_row["domain_tags_csv"] or "")

    quals = db_check.conn.execute(
        "SELECT category, item FROM candidate_qualification WHERE candidate_id = %s",
        (candidate_id,),
    ).fetchall()
    assert quals, "Qualifications should be persisted."

    doc_row = db_check.conn.execute(
        "SELECT experience_text FROM candidate_doc WHERE candidate_id = %s",
        (candidate_id,),
    ).fetchone()
    assert doc_row and "Responsibilities" in (doc_row["experience_text"] or "")
    db_check.close()
