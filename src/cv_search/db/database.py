from __future__ import annotations

import math
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence

try:
    import psycopg
    from psycopg import errors as pg_errors
    from psycopg.rows import dict_row
except (
    ImportError
) as exc:  # pragma: no cover - required dependency should be present in runtime/test envs
    psycopg = None
    pg_errors = None
    dict_row = None
    _psycopg_import_error = exc
else:
    _psycopg_import_error = None

from cv_search.config.settings import Settings


class CVDatabase:
    """Postgres-backed data access layer for candidate storage and retrieval."""

    def __init__(self, settings: Settings, dsn: str | None = None):
        if psycopg is None:
            raise RuntimeError(
                "psycopg is required. Install psycopg[binary]."
            ) from _psycopg_import_error
        self.settings = settings
        self.dsn = dsn or settings.active_db_url
        self.schema_file = str(settings.schema_pg_file)
        self.conn = self._connect_pg()
        self._search_run_columns: set[str] | None = None

    def _connect_pg(self) -> psycopg.Connection:
        try:
            conn = psycopg.connect(self.dsn, autocommit=False, row_factory=dict_row)
        except Exception as exc:
            raise RuntimeError(f"Failed to connect to Postgres at {self.dsn}: {exc}") from exc
        return conn

    def _executemany_pg(self, sql: str, params: Sequence[Sequence[Any]]) -> None:
        with self.conn.cursor() as cur:
            cur.executemany(sql, params)

    def render_sql(self, sql: str, params: Sequence[Any] | Mapping[str, Any] | None = None) -> str:
        try:
            cursor_factory = getattr(psycopg, "ClientCursor", None)
            cursor = cursor_factory(self.conn) if cursor_factory else self.conn.cursor()
            with cursor as cur:
                if not hasattr(cur, "mogrify"):
                    return sql.strip()
                rendered = cur.mogrify(sql) if params is None else cur.mogrify(sql, params)
        except Exception:
            return sql.strip()
        if isinstance(rendered, memoryview):
            rendered = rendered.tobytes()
        if isinstance(rendered, (bytes, bytearray)):
            return rendered.decode("utf-8", errors="replace").strip()
        return str(rendered).strip()

    def close(self) -> None:
        if getattr(self, "conn", None):
            try:
                self.conn.close()
            finally:
                self.conn = None

    def commit(self) -> None:
        self.conn.commit()

    def rollback(self) -> None:
        self.conn.rollback()

    def initialize_schema(self) -> None:
        sql = Path(self.schema_file).read_text(encoding="utf-8")
        with self.conn.cursor() as cur:
            cur.execute(sql)
        self.commit()

    def check_extensions(self) -> Dict[str, str]:
        rows = self.conn.execute(
            "SELECT name, installed_version FROM pg_available_extensions WHERE name IN ('vector', 'pg_trgm');"
        ).fetchall()
        return {row["name"]: row.get("installed_version") or "not installed" for row in rows}

    def check_tables(self) -> List[str]:
        rows = self.conn.execute(
            "SELECT tablename FROM pg_tables WHERE schemaname = 'public' ORDER BY tablename;"
        ).fetchall()
        return [row["tablename"] for row in rows]

    def _get_search_run_columns(self) -> set[str] | None:
        if self._search_run_columns is not None:
            return self._search_run_columns
        try:
            rows = self.conn.execute(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_name = 'search_run'
                  AND table_schema = 'public'
                """
            ).fetchall()
            columns = {row["column_name"] if hasattr(row, "keys") else row[0] for row in rows}
        except Exception:
            return None
        self._search_run_columns = columns
        return columns

    def _is_missing_column(self, exc: Exception) -> bool:
        if pg_errors and isinstance(exc, pg_errors.UndefinedColumn):
            return True
        sqlstate = getattr(exc, "sqlstate", None)
        if sqlstate == "42703":
            return True
        message = str(exc).lower()
        return "column" in message and "does not exist" in message

    def create_search_run(
        self,
        *,
        run_id: str,
        run_kind: str,
        run_dir: str | None,
        user_email: str | None,
        criteria_json: str | None,
        raw_text: str | None,
        top_k: int | None,
        seat_count: int,
        note: str | None,
        status: str = "running",
    ) -> None:
        base_payload = {
            "run_id": run_id,
            "run_kind": run_kind,
            "run_dir": run_dir,
            "user_email": user_email,
            "criteria_json": criteria_json,
            "raw_text": raw_text,
            "top_k": top_k,
            "seat_count": seat_count,
            "note": note,
        }
        payload = {**base_payload, "status": status}

        columns = self._get_search_run_columns()
        if columns is None:
            selected_columns = list(payload.keys())
        else:
            selected_columns = [key for key in payload.keys() if key in columns]
        if not selected_columns:
            selected_columns = list(base_payload.keys())

        def _insert(columns_to_use: list[str]) -> None:
            col_sql = ",\n                    ".join(columns_to_use)
            val_sql = ",".join(["%s"] * len(columns_to_use))
            self.conn.execute(
                f"""
                INSERT INTO search_run(
                    {col_sql}
                )
                VALUES ({val_sql})
                """,
                tuple(payload[col] for col in columns_to_use),
            )

        try:
            _insert(selected_columns)
            self.commit()
        except Exception as exc:
            self.rollback()
            if self._is_missing_column(exc) and selected_columns != list(base_payload.keys()):
                try:
                    _insert(list(base_payload.keys()))
                    self.commit()
                except Exception:
                    self.rollback()
                    raise
            else:
                raise

    def update_search_run_feedback(
        self, *, run_id: str, sentiment: str, comment: str | None
    ) -> None:
        try:
            with self.conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE search_run
                    SET feedback_sentiment = %s,
                        feedback_comment = %s,
                        feedback_submitted_at = NOW()
                    WHERE run_id = %s
                    """,
                    (sentiment, comment, run_id),
                )
            self.commit()
        except Exception:
            self.rollback()
            raise

    def update_search_run_status(
        self,
        *,
        run_id: str,
        status: str,
        completed_at: datetime | None,
        duration_ms: int | None,
        result_count: int | None,
        error_type: str | None,
        error_message: str | None,
        error_stage: str | None,
        error_traceback: str | None,
    ) -> None:
        payload = {
            "status": status,
            "completed_at": completed_at,
            "duration_ms": duration_ms,
            "result_count": result_count,
            "error_type": error_type,
            "error_message": error_message,
            "error_stage": error_stage,
            "error_traceback": error_traceback,
        }
        columns = self._get_search_run_columns()
        if columns is None:
            selected = [
                key for key, value in payload.items() if key == "status" or value is not None
            ]
        else:
            selected = [
                key
                for key, value in payload.items()
                if key in columns and (key == "status" or value is not None)
            ]
        if not selected:
            return

        set_clause = ", ".join([f"{col} = %s" for col in selected])
        params = [payload[col] for col in selected] + [run_id]
        try:
            self.conn.execute(
                f"UPDATE search_run SET {set_clause} WHERE run_id = %s",
                params,
            )
            self.commit()
        except Exception as exc:
            self.rollback()
            if columns is None and self._is_missing_column(exc) and selected != ["status"]:
                try:
                    self.conn.execute(
                        "UPDATE search_run SET status = %s WHERE run_id = %s",
                        (status, run_id),
                    )
                    self.commit()
                except Exception:
                    self.rollback()
                    raise
            else:
                raise

    def list_search_runs(
        self,
        *,
        limit: int = 100,
        status: str | None = None,
        kind: str | None = None,
    ) -> List[Dict[str, Any]]:
        base_columns = [
            "run_id",
            "run_kind",
            "run_dir",
            "user_email",
            "created_at",
            "criteria_json",
            "raw_text",
            "top_k",
            "seat_count",
            "note",
            "feedback_sentiment",
            "feedback_comment",
            "feedback_submitted_at",
        ]
        extra_columns = [
            "status",
            "completed_at",
            "duration_ms",
            "result_count",
            "error_type",
            "error_message",
            "error_stage",
            "error_traceback",
        ]
        columns = self._get_search_run_columns()
        if columns is None:
            select_columns = base_columns + extra_columns
        else:
            select_columns = [col for col in base_columns + extra_columns if col in columns]
        if not select_columns:
            select_columns = base_columns

        conditions: list[str] = []
        params: list[Any] = []
        if kind:
            conditions.append("run_kind = %s")
            params.append(kind)
        if status and columns and "status" in columns:
            conditions.append("status = %s")
            params.append(status)

        where_sql = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        sql = (
            f"SELECT {', '.join(select_columns)} FROM search_run {where_sql} "
            "ORDER BY created_at DESC LIMIT %s"
        )
        params.append(limit)
        select_columns_in_use = select_columns
        try:
            rows = self.conn.execute(sql, params).fetchall()
        except Exception as exc:
            if columns is None and self._is_missing_column(exc):
                select_columns_in_use = base_columns
                fallback_sql = (
                    f"SELECT {', '.join(base_columns)} FROM search_run {where_sql} "
                    "ORDER BY created_at DESC LIMIT %s"
                )
                rows = self.conn.execute(fallback_sql, params).fetchall()
            else:
                raise
        return [
            dict(row) if hasattr(row, "keys") else dict(zip(select_columns_in_use, row))
            for row in rows
        ]

    def get_search_run(self, *, run_id: str) -> Dict[str, Any] | None:
        base_columns = [
            "run_id",
            "run_kind",
            "run_dir",
            "user_email",
            "created_at",
            "criteria_json",
            "raw_text",
            "top_k",
            "seat_count",
            "note",
            "feedback_sentiment",
            "feedback_comment",
            "feedback_submitted_at",
        ]
        extra_columns = [
            "status",
            "completed_at",
            "duration_ms",
            "result_count",
            "error_type",
            "error_message",
            "error_stage",
            "error_traceback",
        ]
        columns = self._get_search_run_columns()
        if columns is None:
            select_columns = base_columns + extra_columns
        else:
            select_columns = [col for col in base_columns + extra_columns if col in columns]
        if not select_columns:
            select_columns = base_columns
        sql = f"SELECT {', '.join(select_columns)} FROM search_run WHERE run_id = %s"
        select_columns_in_use = select_columns
        try:
            row = self.conn.execute(sql, (run_id,)).fetchone()
        except Exception as exc:
            if columns is None and self._is_missing_column(exc):
                select_columns_in_use = base_columns
                fallback_sql = f"SELECT {', '.join(base_columns)} FROM search_run WHERE run_id = %s"
                row = self.conn.execute(fallback_sql, (run_id,)).fetchone()
            else:
                raise
        if not row:
            return None
        return dict(row) if hasattr(row, "keys") else dict(zip(select_columns_in_use, row))

    def remove_candidate_derived(self, candidate_id: str) -> None:
        self.conn.execute("DELETE FROM candidate_doc WHERE candidate_id = %s", (candidate_id,))
        exp_ids = [
            r["id"]
            for r in self.conn.execute(
                "SELECT id FROM experience WHERE candidate_id = %s",
                (candidate_id,),
            ).fetchall()
        ]
        if exp_ids:
            self.conn.execute(
                "DELETE FROM experience_tag WHERE experience_id = ANY(%s)", (exp_ids,)
            )
        self.conn.execute("DELETE FROM experience WHERE candidate_id = %s", (candidate_id,))
        self.conn.execute("DELETE FROM candidate_tag WHERE candidate_id = %s", (candidate_id,))
        self.conn.execute(
            "DELETE FROM candidate_qualification WHERE candidate_id = %s", (candidate_id,)
        )

    def upsert_candidate(self, cv: Dict[str, Any]) -> None:
        self.conn.execute(
            """
            INSERT INTO candidate(
                candidate_id,
                name,
                seniority,
                last_updated,
                source_filename,
                source_gdrive_path,
                source_category,
                source_folder_role_hint
            )
            VALUES(%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT(candidate_id) DO UPDATE SET
                name = EXCLUDED.name,
                seniority = EXCLUDED.seniority,
                last_updated = EXCLUDED.last_updated,
                source_filename = EXCLUDED.source_filename,
                source_gdrive_path = EXCLUDED.source_gdrive_path,
                source_category = EXCLUDED.source_category,
                source_folder_role_hint = EXCLUDED.source_folder_role_hint
            """,
            (
                cv["candidate_id"],
                cv.get("name") or "",
                cv.get("seniority", ""),
                cv.get("last_updated", ""),
                cv.get("source_filename", None),
                cv.get("source_gdrive_path", None),
                cv.get("source_category", None),
                cv.get("source_folder_role_hint", None),
            ),
        )

    def insert_experiences_and_tags(
        self,
        candidate_id: str,
        experiences: List[Dict[str, Any]],
        domain_tags_list: List[List[str]],
        tech_tags_list: List[List[str]],
    ) -> List[int]:
        exp_ids: List[int] = []
        exp_domain_tags_to_insert: List[tuple[int, str, str]] = []
        exp_tech_tags_to_insert: List[tuple[int, str, str]] = []

        for idx, exp in enumerate(experiences or []):
            domain_tags = domain_tags_list[idx]
            tech_tags = tech_tags_list[idx]
            project_description = (
                exp.get("project_description", "") or exp.get("description", "") or ""
            )
            responsibilities = exp.get("responsibilities") or []
            if isinstance(responsibilities, str):
                responsibilities_list = [responsibilities]
            else:
                responsibilities_list = [r for r in responsibilities if r]
            responsibilities_text = "\n".join(responsibilities_list)

            cur = self.conn.execute(
                """
                INSERT INTO experience(
                    candidate_id,
                    title,
                    company,
                    start,
                    "end",
                    project_description,
                    responsibilities_text,
                    domain_tags_csv,
                    tech_tags_csv
                )
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
                RETURNING id
                """,
                (
                    candidate_id,
                    exp.get("title", ""),
                    exp.get("company", ""),
                    exp.get("from", ""),
                    exp.get("to", ""),
                    project_description,
                    responsibilities_text,
                    ",".join(domain_tags),
                    ",".join(tech_tags),
                ),
            )
            exp_id = int(cur.fetchone()["id"])
            exp_ids.append(exp_id)

            for tag in tech_tags:
                exp_tech_tags_to_insert.append((exp_id, "tech", tag))
            for tag in domain_tags:
                exp_domain_tags_to_insert.append((exp_id, "domain", tag))

        if exp_tech_tags_to_insert:
            self._executemany_pg(
                """
                INSERT INTO experience_tag(experience_id, tag_type, tag_key)
                VALUES (%s,%s,%s)
                ON CONFLICT (experience_id, tag_type, tag_key) DO NOTHING
                """,
                exp_tech_tags_to_insert,
            )
        if exp_domain_tags_to_insert:
            self._executemany_pg(
                """
                INSERT INTO experience_tag(experience_id, tag_type, tag_key)
                VALUES (%s,%s,%s)
                ON CONFLICT (experience_id, tag_type, tag_key) DO NOTHING
                """,
                exp_domain_tags_to_insert,
            )

        return exp_ids

    def insert_candidate_qualifications(
        self, candidate_id: str, qualifications: Dict[str, List[str]]
    ) -> None:
        if not qualifications:
            return
        rows: List[tuple[str, str, str, float]] = []
        for category, items in (qualifications or {}).items():
            cat = (category or "").strip().lower()
            if not cat:
                continue
            for item in items or []:
                val = (item or "").strip()
                if not val:
                    continue
                rows.append((candidate_id, cat, val, 1.0))
        if not rows:
            return
        self._executemany_pg(
            """
            INSERT INTO candidate_qualification(candidate_id, category, item, weight)
            VALUES (%s,%s,%s,%s)
            ON CONFLICT(candidate_id, category, item)
            DO UPDATE SET weight = EXCLUDED.weight
            """,
            rows,
        )

    def upsert_candidate_tags(
        self,
        candidate_id: str,
        role_tags: List[str],
        expertise_tags: List[str],
        tech_tags_top: List[str],
        seniority: str,
        domain_rollup: List[str],
    ) -> None:
        tags_to_insert: List[tuple[str, str, str, float]] = []

        for role in role_tags:
            if role:
                tags_to_insert.append((candidate_id, "role", role, 2.0))
        for expertise in expertise_tags:
            if expertise:
                tags_to_insert.append((candidate_id, "expertise", expertise, 1.6))
        for tag in tech_tags_top:
            if tag:
                tags_to_insert.append((candidate_id, "tech", tag, 1.5))
        if seniority:
            tags_to_insert.append((candidate_id, "seniority", seniority, 1.0))
        for domain in domain_rollup:
            if domain:
                tags_to_insert.append((candidate_id, "domain", domain, 1.0))

        if not tags_to_insert:
            return

        self._executemany_pg(
            """
            INSERT INTO candidate_tag(candidate_id, tag_type, tag_key, weight)
            VALUES (%s,%s,%s,%s)
            ON CONFLICT(candidate_id, tag_type, tag_key)
            DO UPDATE SET weight = EXCLUDED.weight
            """,
            tags_to_insert,
        )

    def upsert_candidate_doc(
        self,
        candidate_id: str,
        summary_text: str,
        experience_text: str,
        tags_text: str,
        last_updated: str,
        seniority: str,
    ) -> None:
        self.conn.execute(
            """
            INSERT INTO candidate_doc(
                candidate_id,
                summary_text,
                experience_text,
                tags_text,
                last_updated,
                seniority
            )
            VALUES (%s,%s,%s,%s,%s,%s)
            ON CONFLICT(candidate_id) DO UPDATE SET
                summary_text = EXCLUDED.summary_text,
                experience_text = EXCLUDED.experience_text,
                tags_text = EXCLUDED.tags_text,
                last_updated = EXCLUDED.last_updated,
                seniority = EXCLUDED.seniority
            """,
            (
                candidate_id,
                summary_text,
                experience_text,
                tags_text,
                last_updated,
                seniority,
            ),
        )

    def fetch_tag_hits(
        self, candidate_ids: List[str], tags: List[str]
    ) -> Dict[str, Dict[str, bool]]:
        if not candidate_ids or not tags:
            return {}
        rows = self.conn.execute(
            """
            SELECT candidate_id, tag_key
            FROM candidate_tag
            WHERE candidate_id = ANY(%s)
              AND tag_key = ANY(%s)
            """,
            (candidate_ids, tags),
        ).fetchall()
        result: Dict[str, Dict[str, bool]] = {}
        for row in rows:
            cid = row["candidate_id"]
            tag_key = row["tag_key"]
            result.setdefault(cid, {})[tag_key] = True
        return result

    def compute_idf(self, tokens: List[str], tag_type: str) -> Dict[str, float]:
        unique_tokens = [t for t in dict.fromkeys(tokens) if t]
        if not unique_tokens:
            return {}
        rows = self.conn.execute(
            """
            SELECT tag_key, COUNT(*) AS df
            FROM candidate_tag
            WHERE tag_type = %s
              AND tag_key = ANY(%s)
            GROUP BY tag_key
            """,
            (tag_type, unique_tokens),
        ).fetchall()
        df_map = {row["tag_key"]: int(row["df"]) for row in rows}
        total_candidates = self.conn.execute("SELECT COUNT(*) AS c FROM candidate").fetchone()["c"]
        return {
            token: math.log((total_candidates + 1) / (df_map.get(token, 0) + 1)) + 1
            for token in unique_tokens
        }

    def rank_weighted_set(
        self,
        gated_ids: List[str],
        must_have: List[str],
        nice_to_have: List[str],
        domains: List[str],
        idf_must: Dict[str, float],
        idf_nice: Dict[str, float],
        top_k: int,
        expertise: List[str] | None = None,
        idf_expertise: Dict[str, float] | None = None,
    ) -> tuple[List[Dict[str, Any]], str]:
        if not gated_ids:
            return [], ""

        must_keys = [t for t in dict.fromkeys(must_have) if t]
        nice_keys = [t for t in dict.fromkeys(nice_to_have) if t]
        expertise_keys = [e for e in dict.fromkeys(expertise or []) if e]
        must_weights = [float(idf_must.get(tag, 0.0)) for tag in must_keys]
        nice_weights = [float(idf_nice.get(tag, 0.0)) for tag in nice_keys]
        expertise_weights = [float((idf_expertise or {}).get(tag, 0.0)) for tag in expertise_keys]

        sql = """
        WITH
        must_weights(tag_key, idf) AS (
          SELECT * FROM UNNEST(%s::text[], %s::double precision[])
        ),
        nice_weights(tag_key, idf) AS (
          SELECT * FROM UNNEST(%s::text[], %s::double precision[])
        ),
        expertise_weights(tag_key, idf) AS (
          SELECT * FROM UNNEST(%s::text[], %s::double precision[])
        ),
        candidates AS (
          SELECT c.candidate_id,
                 c.last_updated,
                 COALESCE(SUM(mw.idf), 0.0) AS must_idf_sum,
                 COALESCE(SUM(nw.idf), 0.0) AS nice_idf_sum,
                 COALESCE(SUM(ew.idf), 0.0) AS expertise_idf_sum,
                 SUM(CASE WHEN mw.tag_key IS NOT NULL THEN 1 ELSE 0 END) AS must_hit_count,
                 SUM(CASE WHEN nw.tag_key IS NOT NULL THEN 1 ELSE 0 END) AS nice_hit_count,
                 SUM(CASE WHEN ew.tag_key IS NOT NULL THEN 1 ELSE 0 END) AS expertise_hit_count,
                 MAX(CASE WHEN t.tag_type = 'domain' AND t.tag_key = ANY(%s) THEN 1 ELSE 0 END) AS domain_present
          FROM candidate c
          LEFT JOIN candidate_tag t ON t.candidate_id = c.candidate_id
          LEFT JOIN must_weights mw ON t.tag_type = 'tech' AND mw.tag_key = t.tag_key
          LEFT JOIN nice_weights nw ON t.tag_type = 'tech' AND nw.tag_key = t.tag_key
          LEFT JOIN expertise_weights ew ON t.tag_type = 'expertise' AND ew.tag_key = t.tag_key
          WHERE c.candidate_id = ANY(%s)
          GROUP BY c.candidate_id, c.last_updated
        )
        SELECT * FROM candidates
        ORDER BY must_hit_count DESC, expertise_hit_count DESC, nice_hit_count DESC, candidate_id ASC
        LIMIT %s
        """

        params = (
            must_keys,
            must_weights,
            nice_keys,
            nice_weights,
            expertise_keys,
            expertise_weights,
            domains or [],
            gated_ids,
            top_k,
        )
        rendered_sql = self.render_sql(sql, params)
        rows_raw = self.conn.execute(sql, params).fetchall()
        rows: List[Dict[str, Any]] = [dict(r) for r in rows_raw]
        must_sum = float(sum(must_weights))
        nice_sum = float(sum(nice_weights))
        expertise_sum = float(sum(expertise_weights))
        for r in rows:
            r["must_idf_total"] = must_sum
            r["nice_idf_total"] = nice_sum
            r["expertise_idf_total"] = expertise_sum
        return rows, rendered_sql

    def get_full_candidate_context(self, candidate_id: str) -> Optional[Dict[str, Any]]:
        row = self.conn.execute(
            """
            SELECT summary_text, experience_text, tags_text, last_updated, seniority
            FROM candidate_doc
            WHERE candidate_id = %s
            """,
            (candidate_id,),
        ).fetchone()
        return dict(row) if row else None

    def get_full_candidate_contexts(self, candidate_ids: List[str]) -> Dict[str, Dict[str, Any]]:
        """Bulk fetch full candidate context for multiple candidates in a single query."""
        if not candidate_ids:
            return {}
        rows = self.conn.execute(
            """
            SELECT candidate_id, summary_text, experience_text, tags_text, last_updated, seniority
            FROM candidate_doc
            WHERE candidate_id = ANY(%s)
            """,
            (candidate_ids,),
        ).fetchall()
        return {row["candidate_id"]: dict(row) for row in rows}

    def get_candidate_profile(self, candidate_id: str) -> Optional[Dict[str, Any]]:
        row = self.conn.execute(
            """
            SELECT candidate_id,
                   name,
                   seniority,
                   last_updated,
                   source_filename,
                   source_gdrive_path,
                   source_category,
                   source_folder_role_hint
            FROM candidate
            WHERE candidate_id = %s
            """,
            (candidate_id,),
        ).fetchone()
        return dict(row) if row else None

    def get_candidate_experiences(self, candidate_id: str) -> List[Dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT title,
                   company,
                   start,
                   "end",
                   project_description,
                   responsibilities_text,
                   domain_tags_csv,
                   tech_tags_csv
            FROM experience
            WHERE candidate_id = %s
            ORDER BY id
            """,
            (candidate_id,),
        ).fetchall()
        return [dict(row) for row in rows]

    def get_candidate_qualifications(self, candidate_id: str) -> Dict[str, List[str]]:
        rows = self.conn.execute(
            """
            SELECT category, item
            FROM candidate_qualification
            WHERE candidate_id = %s
            ORDER BY category, item
            """,
            (candidate_id,),
        ).fetchall()
        by_category: Dict[str, List[str]] = {}
        for row in rows:
            category = row.get("category") or ""
            item = row.get("item") or ""
            if not item:
                continue
            by_category.setdefault(category, []).append(item)
        return by_category

    def get_candidate_tags(self, candidate_id: str) -> Dict[str, List[str]]:
        rows = self.conn.execute(
            """
            SELECT tag_type, tag_key
            FROM candidate_tag
            WHERE candidate_id = %s
            ORDER BY tag_type, tag_key
            """,
            (candidate_id,),
        ).fetchall()
        by_type: Dict[str, List[str]] = {}
        for row in rows:
            tag_type = row.get("tag_type") or ""
            tag_key = row.get("tag_key") or ""
            if not tag_key:
                continue
            by_type.setdefault(tag_type, []).append(tag_key)
        return by_type

    def get_candidate_profiles(self, candidate_ids: List[str]) -> Dict[str, Dict[str, Any]]:
        """Bulk fetch candidate profiles for multiple candidates."""
        if not candidate_ids:
            return {}
        rows = self.conn.execute(
            """
            SELECT candidate_id, name, seniority, last_updated,
                   source_filename, source_gdrive_path, source_category,
                   source_folder_role_hint
            FROM candidate
            WHERE candidate_id = ANY(%s)
            """,
            (candidate_ids,),
        ).fetchall()
        return {row["candidate_id"]: dict(row) for row in rows}

    def get_candidate_experiences_bulk(
        self, candidate_ids: List[str]
    ) -> Dict[str, List[Dict[str, Any]]]:
        """Bulk fetch experiences for multiple candidates."""
        if not candidate_ids:
            return {}
        rows = self.conn.execute(
            """
            SELECT candidate_id, title, company, start, "end",
                   project_description, responsibilities_text,
                   domain_tags_csv, tech_tags_csv
            FROM experience
            WHERE candidate_id = ANY(%s)
            ORDER BY candidate_id, id
            """,
            (candidate_ids,),
        ).fetchall()
        by_candidate: Dict[str, List[Dict[str, Any]]] = {}
        for row in rows:
            cid = row["candidate_id"]
            by_candidate.setdefault(cid, []).append(dict(row))
        return by_candidate

    def get_candidate_qualifications_bulk(
        self, candidate_ids: List[str]
    ) -> Dict[str, Dict[str, List[str]]]:
        """Bulk fetch qualifications for multiple candidates."""
        if not candidate_ids:
            return {}
        rows = self.conn.execute(
            """
            SELECT candidate_id, category, item
            FROM candidate_qualification
            WHERE candidate_id = ANY(%s)
            ORDER BY candidate_id, category, item
            """,
            (candidate_ids,),
        ).fetchall()
        by_candidate: Dict[str, Dict[str, List[str]]] = {}
        for row in rows:
            cid = row["candidate_id"]
            category = row.get("category") or ""
            item = row.get("item") or ""
            if not item:
                continue
            by_candidate.setdefault(cid, {}).setdefault(category, []).append(item)
        return by_candidate

    def get_candidate_tags_bulk(self, candidate_ids: List[str]) -> Dict[str, Dict[str, List[str]]]:
        """Bulk fetch tags for multiple candidates."""
        if not candidate_ids:
            return {}
        rows = self.conn.execute(
            """
            SELECT candidate_id, tag_type, tag_key
            FROM candidate_tag
            WHERE candidate_id = ANY(%s)
            ORDER BY candidate_id, tag_type, tag_key
            """,
            (candidate_ids,),
        ).fetchall()
        by_candidate: Dict[str, Dict[str, List[str]]] = {}
        for row in rows:
            cid = row["candidate_id"]
            tag_type = row.get("tag_type") or ""
            tag_key = row.get("tag_key") or ""
            if not tag_key:
                continue
            by_candidate.setdefault(cid, {}).setdefault(tag_type, []).append(tag_key)
        return by_candidate

    def get_candidate_last_updated_by_source_filename(self, source_filename: str) -> Optional[str]:
        row = self.conn.execute(
            "SELECT last_updated FROM candidate WHERE source_filename = %s",
            (source_filename,),
        ).fetchone()
        if not row:
            return None
        return row["last_updated"]

    def get_candidate_last_updated_by_source_gdrive_path(
        self, source_gdrive_path: str
    ) -> Optional[str]:
        row = self.conn.execute(
            "SELECT last_updated FROM candidate WHERE source_gdrive_path = %s",
            (source_gdrive_path,),
        ).fetchone()
        if not row:
            return None
        return row["last_updated"]

    def get_last_updated_for_filenames(self, filenames: Iterable[str]) -> Dict[str, Optional[str]]:
        unique_names = [name for name in dict.fromkeys(filenames) if name]
        if not unique_names:
            return {}
        rows = self.conn.execute(
            "SELECT source_filename, last_updated FROM candidate WHERE source_filename = ANY(%s)",
            (unique_names,),
        ).fetchall()
        existing = {row["source_filename"]: row["last_updated"] for row in rows}
        return {name: existing.get(name) for name in unique_names}

    def get_last_updated_for_gdrive_paths(self, paths: Iterable[str]) -> Dict[str, Optional[str]]:
        unique_paths = [path for path in dict.fromkeys(paths) if path]
        if not unique_paths:
            return {}
        rows = self.conn.execute(
            "SELECT source_gdrive_path, last_updated FROM candidate WHERE source_gdrive_path = ANY(%s)",
            (unique_paths,),
        ).fetchall()
        existing = {row["source_gdrive_path"]: row["last_updated"] for row in rows}
        return {path: existing.get(path) for path in unique_paths}

    def fts_search(
        self,
        query_text: str,
        gated_ids: List[str],
        top_k: int,
    ) -> tuple[List[Dict[str, Any]], str]:
        params: Dict[str, Any] = {"ts_query": query_text, "top_k": top_k}
        sql = """
        SELECT candidate_id,
               ts_rank_cd(tsv_document, plainto_tsquery('english', %(ts_query)s)) AS rank
        FROM candidate_doc
        WHERE tsv_document @@ plainto_tsquery('english', %(ts_query)s)
        """
        if gated_ids:
            sql += " AND candidate_id = ANY(%(gated)s)"
            params["gated"] = gated_ids
        sql += " ORDER BY rank DESC, candidate_id ASC LIMIT %(top_k)s"
        rendered_sql = self.render_sql(sql, params)
        rows = self.conn.execute(sql, params).fetchall()
        return [dict(row) for row in rows], rendered_sql

    def reset_state(self) -> None:
        """Truncate all tables so tests start from a clean Postgres slate."""
        try:
            self.conn.execute(
                "TRUNCATE search_run, experience_tag, experience, candidate_doc, candidate_tag, candidate_qualification, candidate RESTART IDENTITY CASCADE"
            )
            self.commit()
        except (pg_errors.UndefinedTable, AttributeError):
            self.rollback()
