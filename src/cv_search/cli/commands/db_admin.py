from __future__ import annotations

import click

from cv_search.cli.context import CLIContext
from cv_search.ingestion.pipeline import CVIngestionPipeline
from cv_search.ingestion.redaction import (
    anonymized_candidate_name,
    is_anonymized_name,
    redact_name_in_text,
)


def register(cli: click.Group) -> None:
    @cli.command("init-db")
    @click.pass_obj
    def init_db_cmd(ctx: CLIContext) -> None:
        """Initialize (or re-initialize) the Postgres schema."""
        db = ctx.db
        try:
            db.initialize_schema()
            ext = db.check_extensions()
            click.echo(
                f"Initialized database at {db.dsn if hasattr(db, 'dsn') else '[unknown DSN]'}"
            )
            click.echo(f"Extensions: pg_trgm={ext.get('pg_trgm')}")
        finally:
            db.close()

    @cli.command("check-db")
    @click.pass_obj
    def check_db_cmd(ctx: CLIContext) -> None:
        """Quick DB sanity: tables + extension availability."""
        db = ctx.db
        try:
            names = ", ".join(db.check_tables())
            ext = db.check_extensions()
            click.echo(f"Tables: {names or '(none)'}")
            click.echo(f"pg_trgm: {ext.get('pg_trgm')}")
        finally:
            db.close()

    @cli.command("ingest-mock")
    @click.pass_obj
    def ingest_mock_cmd(ctx: CLIContext) -> None:
        """Rebuild Postgres with mock JSON (FTS)."""
        settings = ctx.settings
        db = ctx.db
        pipeline = CVIngestionPipeline(db, settings)
        try:
            n = pipeline.run_mock_ingestion()
            click.echo(f"Ingested {n} mock CVs into {settings.active_db_url}")
        finally:
            pipeline.close()
            db.close()

    @cli.command("redact-candidate-names")
    @click.option("--dry-run", is_flag=True, help="Preview changes without writing to Postgres.")
    @click.option("--limit", type=int, default=None, help="Max candidates to process.")
    @click.option(
        "--only-missing",
        is_flag=True,
        help="Skip candidates whose names already match the anonymized format.",
    )
    @click.pass_obj
    def redact_candidate_names_cmd(
        ctx: CLIContext, dry_run: bool, limit: int | None, only_missing: bool
    ) -> None:
        """Backfill anonymized names and redact name tokens from stored CV text."""
        settings = ctx.settings
        db = ctx.db

        prefix = settings.candidate_name_prefix or "Candidate"
        salt = settings.candidate_name_salt

        sql = """
            SELECT c.candidate_id,
                   c.name,
                   c.source_filename,
                   c.source_gdrive_path,
                   d.summary_text,
                   d.experience_text,
                   d.tags_text,
                   d.last_updated,
                   d.seniority
            FROM candidate c
            LEFT JOIN candidate_doc d ON d.candidate_id = c.candidate_id
            ORDER BY c.candidate_id
        """
        params = ()
        if limit:
            sql += " LIMIT %s"
            params = (limit,)

        rows = db.conn.execute(sql, params).fetchall()
        processed = 0
        skipped = 0
        unchanged = 0
        updated_names = 0
        updated_docs = 0
        pending_commits = 0

        try:
            for row in rows:
                processed += 1
                candidate_id = row["candidate_id"]
                existing_name = (row.get("name") or "").strip()
                already_anonymized = is_anonymized_name(existing_name, prefix)

                if only_missing and already_anonymized:
                    skipped += 1
                    continue

                name_hint = existing_name if existing_name and not already_anonymized else None
                filename_hint = row.get("source_gdrive_path") or row.get("source_filename")
                filename_hint = filename_hint if not name_hint else None

                summary_raw = row.get("summary_text")
                experience_raw = row.get("experience_text")
                redacted_summary = redact_name_in_text(summary_raw, name_hint, filename_hint)
                redacted_experience = redact_name_in_text(experience_raw, name_hint, filename_hint)

                new_name = anonymized_candidate_name(candidate_id, salt, prefix)
                name_changed = new_name != existing_name
                summary_changed = (summary_raw or "") != (redacted_summary or "")
                experience_changed = (experience_raw or "") != (redacted_experience or "")

                doc_present = any(
                    row.get(key) is not None
                    for key in ("summary_text", "experience_text", "tags_text")
                )
                doc_changed = doc_present and (summary_changed or experience_changed)

                if not (name_changed or doc_changed):
                    unchanged += 1
                    continue

                if name_changed:
                    updated_names += 1
                if doc_changed:
                    updated_docs += 1

                if dry_run:
                    continue

                if name_changed:
                    db.conn.execute(
                        "UPDATE candidate SET name = %s WHERE candidate_id = %s",
                        (new_name, candidate_id),
                    )

                if doc_changed:
                    summary_to_store = redacted_summary if summary_changed else summary_raw
                    experience_to_store = (
                        redacted_experience if experience_changed else experience_raw
                    )
                    tags_text = row.get("tags_text") or ""

                    db.upsert_candidate_doc(
                        candidate_id=candidate_id,
                        summary_text=summary_to_store,
                        experience_text=experience_to_store,
                        tags_text=tags_text,
                        last_updated=row.get("last_updated") or "",
                        seniority=row.get("seniority") or "",
                    )

                pending_commits += 1
                if pending_commits >= 50:
                    db.commit()
                    pending_commits = 0

            if not dry_run and pending_commits:
                db.commit()

            click.echo(
                "Redaction summary: "
                f"processed={processed}, "
                f"updated_names={updated_names}, "
                f"updated_docs={updated_docs}, "
                f"unchanged={unchanged}, "
                f"skipped={skipped}, "
                f"dry_run={dry_run}"
            )
        except Exception:
            if not dry_run:
                db.rollback()
            raise
        finally:
            db.close()
