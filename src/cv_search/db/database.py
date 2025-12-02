from __future__ import annotations

import json
import math
import sqlite3
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence

try:
    import psycopg
    from psycopg import errors as pg_errors
    from psycopg.rows import dict_row
    from pgvector.psycopg import Vector, register_vector
except ImportError:  # pragma: no cover - optional Postgres driver for offline runs
    psycopg = None
    pg_errors = None
    dict_row = None
    register_vector = None
    Vector = None

from cv_search.config.settings import Settings


class CVDatabase:
    """Postgres-backed data access layer for candidate storage and retrieval."""

    def __init__(self, settings: Settings, dsn: str | None = None):
        self.settings = settings
        self.dsn = dsn or settings.active_db_url
        self.schema_file = str(settings.schema_pg_file)
        self.backend = "postgres"
        self.sqlite_path = self._default_sqlite_path()
        self.conn = None

        if psycopg:
            try:
                self.conn = self._connect_pg()
            except Exception:
                if settings.agentic_test_mode:
                    self.backend = "sqlite"
                    self.conn = self._connect_sqlite()
                else:
                    raise
        else:
            self.backend = "sqlite"
            self.conn = self._connect_sqlite()

    def _default_sqlite_path(self) -> Path:
        if self.settings.agentic_test_mode:
            base = self.settings.test_data_dir / "tmp" / "agentic_db"
        else:
            base = self.settings.data_dir / "db"
        return base / "cvsearch_pg_fallback.db"

    def _connect_pg(self) -> psycopg.Connection:
        conn = psycopg.connect(self.dsn, autocommit=False, row_factory=dict_row)
        try:
            register_vector(conn)
        except Exception as exc:
            if self._is_missing_vector_type(exc):
                try:
                    self._ensure_pg_extensions(conn)
                    register_vector(conn)
                except Exception:
                    conn.close()
                    raise
            else:
                conn.close()
                raise
        return conn

    def _is_missing_vector_type(self, exc: Exception) -> bool:
        return isinstance(exc, psycopg.ProgrammingError) and "vector type not found" in str(exc).lower()

    def _ensure_pg_extensions(self, conn: psycopg.Connection) -> None:
        try:
            with conn.cursor() as cur:
                cur.execute("CREATE EXTENSION IF NOT EXISTS vector;")
                cur.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm;")
            conn.commit()
        except Exception as ext_exc:
            conn.rollback()
            raise RuntimeError(
                "Postgres extension 'vector' is required. Install the pgvector extension and allow CREATE EXTENSION."
            ) from ext_exc

    def _executemany_pg(self, sql: str, params: Sequence[Sequence[Any]]) -> None:
        with self.conn.cursor() as cur:
            cur.executemany(sql, params)

    def _connect_sqlite(self) -> sqlite3.Connection:
        db_file = Path(self.sqlite_path)
        db_file.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(db_file))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON;")
        return conn

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
        if self.backend == "postgres":
            sql = Path(self.schema_file).read_text(encoding="utf-8")
            with self.conn.cursor() as cur:
                cur.execute(sql)
            self.commit()
        else:
            self._initialize_sqlite_schema()

    def _initialize_sqlite_schema(self) -> None:
        schema_sql = """
        CREATE TABLE IF NOT EXISTS app_config (
            key TEXT PRIMARY KEY,
            value TEXT
        );

        CREATE TABLE IF NOT EXISTS candidate (
            candidate_id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            location TEXT,
            seniority TEXT,
            last_updated TEXT,
            source_filename TEXT,
            source_gdrive_path TEXT,
            source_category TEXT,
            source_folder_role_hint TEXT
        );

        CREATE TABLE IF NOT EXISTS candidate_tag (
            candidate_id TEXT NOT NULL,
            tag_type TEXT NOT NULL,
            tag_key TEXT NOT NULL,
            weight REAL DEFAULT 1.0,
            PRIMARY KEY (candidate_id, tag_type, tag_key)
        );

        CREATE INDEX IF NOT EXISTS idx_candidate_tag_type_key ON candidate_tag(tag_type, tag_key);
        CREATE INDEX IF NOT EXISTS idx_candidate_tag_candidate ON candidate_tag(candidate_id);

        CREATE TABLE IF NOT EXISTS experience (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            candidate_id TEXT NOT NULL,
            title TEXT,
            company TEXT,
            start TEXT,
            "end" TEXT,
            domain_tags_csv TEXT,
            tech_tags_csv TEXT,
            highlights TEXT,
            FOREIGN KEY(candidate_id) REFERENCES candidate(candidate_id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS experience_tag (
            experience_id INTEGER NOT NULL,
            tag_type TEXT NOT NULL,
            tag_key TEXT NOT NULL,
            PRIMARY KEY (experience_id, tag_type, tag_key),
            FOREIGN KEY(experience_id) REFERENCES experience(id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_experience_candidate ON experience(candidate_id);

        CREATE TABLE IF NOT EXISTS candidate_doc (
            candidate_id TEXT PRIMARY KEY,
            summary_text TEXT,
            experience_text TEXT,
            tags_text TEXT,
            embedding TEXT,
            last_updated TEXT,
            location TEXT,
            seniority TEXT,
            FOREIGN KEY(candidate_id) REFERENCES candidate(candidate_id) ON DELETE CASCADE
        );
        """
        self.conn.executescript(schema_sql)
        self.commit()

    def check_extensions(self) -> Dict[str, str]:
        if self.backend == "postgres":
            rows = self.conn.execute(
                "SELECT name, installed_version FROM pg_available_extensions WHERE name IN ('vector', 'pg_trgm');"
            ).fetchall()
            return {row["name"]: row.get("installed_version") or "not installed" for row in rows}
        return {"vector": "sqlite-fallback", "pg_trgm": "sqlite-fallback"}

    def check_tables(self) -> List[str]:
        if self.backend == "postgres":
            rows = self.conn.execute(
                "SELECT tablename FROM pg_tables WHERE schemaname = 'public' ORDER BY tablename;"
            ).fetchall()
            return [row["tablename"] for row in rows]
        rows = self.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name;"
        ).fetchall()
        return [row[0] for row in rows]

    def set_app_config(self, key: str, value: str) -> None:
        if self.backend == "postgres":
            self.conn.execute(
                """
                INSERT INTO app_config(key, value)
                VALUES (%s, %s)
                ON CONFLICT(key) DO UPDATE SET value = EXCLUDED.value
                """,
                (key, value),
            )
        else:
            self.conn.execute(
                """
                INSERT INTO app_config(key, value)
                VALUES (?, ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value
                """,
                (key, value),
            )

    def get_app_config(self, key: str) -> Optional[str]:
        if self.backend == "postgres":
            row = self.conn.execute("SELECT value FROM app_config WHERE key = %s", (key,)).fetchone()
            return row["value"] if row else None
        row = self.conn.execute("SELECT value FROM app_config WHERE key = ?", (key,)).fetchone()
        return row[0] if row else None

    def remove_candidate_derived(self, candidate_id: str) -> None:
        if self.backend == "postgres":
            self.conn.execute("DELETE FROM candidate_doc WHERE candidate_id = %s", (candidate_id,))
            exp_ids = [
                r["id"]
                for r in self.conn.execute(
                    "SELECT id FROM experience WHERE candidate_id = %s",
                    (candidate_id,),
                ).fetchall()
            ]
            if exp_ids:
                self.conn.execute("DELETE FROM experience_tag WHERE experience_id = ANY(%s)", (exp_ids,))
            self.conn.execute("DELETE FROM experience WHERE candidate_id = %s", (candidate_id,))
            self.conn.execute("DELETE FROM candidate_tag WHERE candidate_id = %s", (candidate_id,))
        else:
            self.conn.execute("DELETE FROM candidate_doc WHERE candidate_id = ?", (candidate_id,))
            exp_ids = [
                r[0]
                for r in self.conn.execute(
                    "SELECT id FROM experience WHERE candidate_id = ?",
                    (candidate_id,),
                ).fetchall()
            ]
            if exp_ids:
                self.conn.executemany(
                    "DELETE FROM experience_tag WHERE experience_id = ?",
                    [(i,) for i in exp_ids],
                )
            self.conn.execute("DELETE FROM experience WHERE candidate_id = ?", (candidate_id,))
            self.conn.execute("DELETE FROM candidate_tag WHERE candidate_id = ?", (candidate_id,))

    def upsert_candidate(self, cv: Dict[str, Any]) -> None:
        if self.backend == "postgres":
            self.conn.execute(
                """
                INSERT INTO candidate(
                    candidate_id,
                    name,
                    location,
                    seniority,
                    last_updated,
                    source_filename,
                    source_gdrive_path,
                    source_category,
                    source_folder_role_hint
                )
                VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT(candidate_id) DO UPDATE SET
                    name = EXCLUDED.name,
                    location = EXCLUDED.location,
                    seniority = EXCLUDED.seniority,
                    last_updated = EXCLUDED.last_updated,
                    source_filename = EXCLUDED.source_filename,
                    source_gdrive_path = EXCLUDED.source_gdrive_path,
                    source_category = EXCLUDED.source_category,
                    source_folder_role_hint = EXCLUDED.source_folder_role_hint
                """,
                (
                    cv["candidate_id"],
                    cv.get("name", "[redacted]"),
                    cv.get("location", ""),
                    cv.get("seniority", ""),
                    cv.get("last_updated", ""),
                    cv.get("source_filename", None),
                    cv.get("source_gdrive_path", None),
                    cv.get("source_category", None),
                    cv.get("source_folder_role_hint", None),
                ),
            )
        else:
            self.conn.execute(
                """
                INSERT INTO candidate(
                    candidate_id,
                    name,
                    location,
                    seniority,
                    last_updated,
                    source_filename,
                    source_gdrive_path,
                    source_category,
                    source_folder_role_hint
                )
                VALUES(?,?,?,?,?,?,?,?,?)
                ON CONFLICT(candidate_id) DO UPDATE SET
                    name=excluded.name,
                    location=excluded.location,
                    seniority=excluded.seniority,
                    last_updated=excluded.last_updated,
                    source_filename=excluded.source_filename,
                    source_gdrive_path=excluded.source_gdrive_path,
                    source_category=excluded.source_category,
                    source_folder_role_hint=excluded.source_folder_role_hint
                """,
                (
                    cv["candidate_id"],
                    cv.get("name", "[redacted]"),
                    cv.get("location", ""),
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

            if self.backend == "postgres":
                cur = self.conn.execute(
                    """
                    INSERT INTO experience(
                        candidate_id,
                        title,
                        company,
                        start,
                        "end",
                        domain_tags_csv,
                        tech_tags_csv,
                        highlights
                    )
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
                    RETURNING id
                    """,
                    (
                        candidate_id,
                        exp.get("title", ""),
                        exp.get("company", ""),
                        exp.get("from", ""),
                        exp.get("to", ""),
                        ",".join(domain_tags),
                        ",".join(tech_tags),
                        "\n".join(exp.get("highlights", []) or []),
                    ),
                )
                exp_id = int(cur.fetchone()["id"])
            else:
                cur = self.conn.execute(
                    """
                    INSERT INTO experience(
                        candidate_id,
                        title,
                        company,
                        start,
                        "end",
                        domain_tags_csv,
                        tech_tags_csv,
                        highlights
                    )
                    VALUES (?,?,?,?,?,?,?,?)
                    """,
                    (
                        candidate_id,
                        exp.get("title", ""),
                        exp.get("company", ""),
                        exp.get("from", ""),
                        exp.get("to", ""),
                        ",".join(domain_tags),
                        ",".join(tech_tags),
                        "\n".join(exp.get("highlights", []) or []),
                    ),
                )
                exp_id = int(cur.lastrowid)
            exp_ids.append(exp_id)

            for tag in tech_tags:
                exp_tech_tags_to_insert.append((exp_id, "tech", tag))
            for tag in domain_tags:
                exp_domain_tags_to_insert.append((exp_id, "domain", tag))

        if exp_tech_tags_to_insert:
            if self.backend == "postgres":
                self._executemany_pg(
                    """
                    INSERT INTO experience_tag(experience_id, tag_type, tag_key)
                    VALUES (%s,%s,%s)
                    ON CONFLICT (experience_id, tag_type, tag_key) DO NOTHING
                    """,
                    exp_tech_tags_to_insert,
                )
            else:
                self.conn.executemany(
                    """
                    INSERT INTO experience_tag(experience_id, tag_type, tag_key)
                    VALUES (?,?,?)
                    ON CONFLICT (experience_id, tag_type, tag_key) DO NOTHING
                    """,
                    exp_tech_tags_to_insert,
                )
        if exp_domain_tags_to_insert:
            if self.backend == "postgres":
                self._executemany_pg(
                    """
                    INSERT INTO experience_tag(experience_id, tag_type, tag_key)
                    VALUES (%s,%s,%s)
                    ON CONFLICT (experience_id, tag_type, tag_key) DO NOTHING
                    """,
                    exp_domain_tags_to_insert,
                )
            else:
                self.conn.executemany(
                    """
                    INSERT INTO experience_tag(experience_id, tag_type, tag_key)
                    VALUES (?,?,?)
                    ON CONFLICT (experience_id, tag_type, tag_key) DO NOTHING
                    """,
                    exp_domain_tags_to_insert,
                )

        return exp_ids

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

        if self.backend == "postgres":
            self._executemany_pg(
                """
                INSERT INTO candidate_tag(candidate_id, tag_type, tag_key, weight)
                VALUES (%s,%s,%s,%s)
                ON CONFLICT(candidate_id, tag_type, tag_key)
                DO UPDATE SET weight = EXCLUDED.weight
                """,
                tags_to_insert,
            )
        else:
            self.conn.executemany(
                """
                INSERT INTO candidate_tag(candidate_id, tag_type, tag_key, weight)
                VALUES (?,?,?,?)
                ON CONFLICT(candidate_id, tag_type, tag_key)
                DO UPDATE SET weight = excluded.weight
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
        location: str,
        seniority: str,
        embedding: Sequence[float] | None,
    ) -> None:
        if self.backend == "postgres":
            emb_payload = None
            if embedding is not None:
                emb_list = list(embedding)
                emb_payload = Vector(emb_list) if Vector else emb_list
            self.conn.execute(
                """
                INSERT INTO candidate_doc(
                    candidate_id,
                    summary_text,
                    experience_text,
                    tags_text,
                    embedding,
                    last_updated,
                    location,
                    seniority
                )
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT(candidate_id) DO UPDATE SET
                    summary_text = EXCLUDED.summary_text,
                    experience_text = EXCLUDED.experience_text,
                    tags_text = EXCLUDED.tags_text,
                    embedding = EXCLUDED.embedding,
                    last_updated = EXCLUDED.last_updated,
                    location = EXCLUDED.location,
                    seniority = EXCLUDED.seniority
                """,
                (
                    candidate_id,
                    summary_text,
                    experience_text,
                    tags_text,
                    emb_payload,
                    last_updated,
                    location,
                    seniority,
                ),
            )
        else:
            emb_json = json.dumps(list(embedding)) if embedding is not None else None
            self.conn.execute(
                """
                INSERT INTO candidate_doc(
                    candidate_id,
                    summary_text,
                    experience_text,
                    tags_text,
                    embedding,
                    last_updated,
                    location,
                    seniority
                )
                VALUES (?,?,?,?,?,?,?,?)
                ON CONFLICT(candidate_id) DO UPDATE SET
                    summary_text = excluded.summary_text,
                    experience_text = excluded.experience_text,
                    tags_text = excluded.tags_text,
                    embedding = excluded.embedding,
                    last_updated = excluded.last_updated,
                    location = excluded.location,
                    seniority = excluded.seniority
                """,
                (
                    candidate_id,
                    summary_text,
                    experience_text,
                    tags_text,
                    emb_json,
                    last_updated,
                    location,
                    seniority,
                ),
            )

    def fetch_tag_hits(self, candidate_ids: List[str], tags: List[str]) -> Dict[str, Dict[str, bool]]:
        if not candidate_ids or not tags:
            return {}
        if self.backend == "postgres":
            rows = self.conn.execute(
                """
                SELECT candidate_id, tag_key
                FROM candidate_tag
                WHERE candidate_id = ANY(%s)
                  AND tag_key = ANY(%s)
                """,
                (candidate_ids, tags),
            ).fetchall()
        else:
            placeholders_ids = ",".join(["?"] * len(candidate_ids))
            placeholders_tags = ",".join(["?"] * len(tags))
            rows = self.conn.execute(
                f"""
                SELECT candidate_id, tag_key
                FROM candidate_tag
                WHERE candidate_id IN ({placeholders_ids})
                  AND tag_key IN ({placeholders_tags})
                """,
                tuple(candidate_ids) + tuple(tags),
            ).fetchall()
        result: Dict[str, Dict[str, bool]] = {}
        for row in rows:
            cid = row["candidate_id"] if self.backend == "postgres" else row[0]
            tag_key = row["tag_key"] if self.backend == "postgres" else row[1]
            result.setdefault(cid, {})[tag_key] = True
        return result

    def compute_idf(self, tokens: List[str], tag_type: str) -> Dict[str, float]:
        if not tokens:
            return {}
        if self.backend == "postgres":
            rows = self.conn.execute(
                """
                SELECT tag_key, COUNT(*) AS df
                FROM candidate_tag
                WHERE tag_type = %s
                  AND tag_key = ANY(%s)
                GROUP BY tag_key
                """,
                (tag_type, tokens),
            ).fetchall()
            total_candidates = self.conn.execute("SELECT COUNT(*) AS c FROM candidate").fetchone()["c"]
        else:
            placeholders = ",".join(["?"] * len(tokens))
            rows = self.conn.execute(
                f"""
                SELECT tag_key, COUNT(*) AS df
                FROM candidate_tag
                WHERE tag_type = ?
                  AND tag_key IN ({placeholders})
                GROUP BY tag_key
                """,
                (tag_type, *tokens),
            ).fetchall()
            total_candidates = self.conn.execute("SELECT COUNT(*) FROM candidate").fetchone()[0]
        idf: Dict[str, float] = {}
        for row in rows:
            key = row["tag_key"] if self.backend == "postgres" else row[0]
            df = row["df"] if self.backend == "postgres" else row[1]
            idf[key] = math.log((total_candidates + 1) / (df + 1)) + 1
        return idf

    def rank_weighted_set(
        self,
        gated_ids: List[str],
        must_have: List[str],
        nice_to_have: List[str],
        domains: List[str],
        idf_must: Dict[str, float],
        idf_nice: Dict[str, float],
        top_k: int,
    ) -> tuple[List[Dict[str, Any]], str, List[Dict[str, Any]]]:
        if not gated_ids:
            return [], "", []

        if self.backend == "postgres":
            sql = """
            WITH candidates AS (
              SELECT c.candidate_id,
                     c.last_updated,
                     SUM(CASE WHEN t.tag_type = 'tech' AND t.tag_key = ANY(%s) THEN 1 ELSE 0 END) AS must_hit_count,
                     SUM(CASE WHEN t.tag_type = 'tech' AND t.tag_key = ANY(%s) THEN 1 ELSE 0 END) AS nice_hit_count,
                     MAX(CASE WHEN t.tag_type = 'domain' AND t.tag_key = ANY(%s) THEN 1 ELSE 0 END) AS domain_present
              FROM candidate_tag t
              JOIN candidate c ON c.candidate_id = t.candidate_id
              WHERE c.candidate_id = ANY(%s)
              GROUP BY c.candidate_id
            )
            SELECT * FROM candidates
            ORDER BY must_hit_count DESC, nice_hit_count DESC
            LIMIT %s
            """

            params = (
                must_have or [],
                nice_to_have or [],
                domains or [],
                gated_ids,
                top_k,
            )
            plan = self.explain_query_plan(sql, params)
            rows_raw = self.conn.execute(sql, params).fetchall()
            rows: List[Dict[str, Any]] = [dict(r) for r in rows_raw]
        else:
            def ph(n: int) -> str:
                return ",".join(["?"] * n)

            must_expr = "0"
            nice_expr = "0"
            domain_expr = "0"
            params_list: List[Any] = []

            if must_have:
                must_expr = f"SUM(CASE WHEN t.tag_type = 'tech' AND t.tag_key IN ({ph(len(must_have))}) THEN 1 ELSE 0 END)"
                params_list.extend(must_have)
            if nice_to_have:
                nice_expr = f"SUM(CASE WHEN t.tag_type = 'tech' AND t.tag_key IN ({ph(len(nice_to_have))}) THEN 1 ELSE 0 END)"
                params_list.extend(nice_to_have)
            if domains:
                domain_expr = f"MAX(CASE WHEN t.tag_type = 'domain' AND t.tag_key IN ({ph(len(domains))}) THEN 1 ELSE 0 END)"
                params_list.extend(domains)

            sql = f"""
        WITH candidates AS (
          SELECT c.candidate_id,
                 c.last_updated,
                 {must_expr} AS must_hit_count,
                 {nice_expr} AS nice_hit_count,
                 {domain_expr} AS domain_present
          FROM candidate_tag t
          JOIN candidate c ON c.candidate_id = t.candidate_id
          WHERE c.candidate_id IN ({ph(len(gated_ids))})
          GROUP BY c.candidate_id
        )
        SELECT * FROM candidates
        ORDER BY must_hit_count DESC, nice_hit_count DESC
        LIMIT ?
        """

            params_list.extend(gated_ids)
            params_list.append(top_k)
            plan = self.explain_query_plan(sql, params_list)
            rows_raw = self.conn.execute(sql, params_list).fetchall()
            rows = [
                {k: r[idx] for idx, k in enumerate(r.keys())} if isinstance(r, sqlite3.Row) else dict(r)
                for r in rows_raw
            ]
        must_sum = sum(idf_must.get(tag, 0.0) for tag in must_have)
        nice_sum = sum(idf_nice.get(tag, 0.0) for tag in nice_to_have)
        for r in rows:
            r["must_idf_sum"] = must_sum
            r["nice_idf_sum"] = nice_sum
        return rows, sql.strip(), plan

    def explain_query_plan(self, sql: str, params: Iterable[Any]) -> List[Dict[str, Any]]:
        if self.backend == "postgres":
            plan_sql = f"EXPLAIN (FORMAT JSON) {sql}"
            cur = self.conn.execute(plan_sql, params)
            res = cur.fetchone()
            if not res or "QUERY PLAN" not in res:
                return []
            return res["QUERY PLAN"]
        cur = self.conn.execute(f"EXPLAIN QUERY PLAN {sql}", tuple(params))
        columns = [col[0] for col in cur.description]
        return [dict(zip(columns, row)) for row in cur.fetchall()]

    def get_full_candidate_context(self, candidate_id: str) -> Optional[Dict[str, Any]]:
        if self.backend == "postgres":
            row = self.conn.execute(
                """
                SELECT summary_text, experience_text, tags_text, last_updated, location, seniority
                FROM candidate_doc
                WHERE candidate_id = %s
                """,
                (candidate_id,),
            ).fetchone()
            return dict(row) if row else None
        row = self.conn.execute(
            """
            SELECT summary_text, experience_text, tags_text, last_updated, location, seniority
            FROM candidate_doc
            WHERE candidate_id = ?
            """,
            (candidate_id,),
        ).fetchone()
        if not row:
            return None
        return {k: row[idx] for idx, k in enumerate(row.keys())}

    def get_candidate_last_updated_by_source_filename(self, source_filename: str) -> Optional[str]:
        if self.backend == "postgres":
            row = self.conn.execute(
                "SELECT last_updated FROM candidate WHERE source_filename = %s",
                (source_filename,),
            ).fetchone()
            if not row:
                return None
            return row["last_updated"]
        row = self.conn.execute(
            "SELECT last_updated FROM candidate WHERE source_filename = ?",
            (source_filename,),
        ).fetchone()
        return row[0] if row else None

    def get_last_updated_for_filenames(self, filenames: Iterable[str]) -> Dict[str, Optional[str]]:
        unique_names = [name for name in dict.fromkeys(filenames) if name]
        if not unique_names:
            return {}
        if self.backend == "postgres":
            rows = self.conn.execute(
                "SELECT source_filename, last_updated FROM candidate WHERE source_filename = ANY(%s)",
                (unique_names,),
            ).fetchall()
            existing = {row["source_filename"]: row["last_updated"] for row in rows}
        else:
            placeholders = ",".join(["?"] * len(unique_names))
            rows = self.conn.execute(
                f"SELECT source_filename, last_updated FROM candidate WHERE source_filename IN ({placeholders})",
                tuple(unique_names),
            ).fetchall()
            existing = {row[0]: row[1] for row in rows}
        return {name: existing.get(name) for name in unique_names}

    def _cosine_similarity(self, a: Sequence[float], b: Sequence[float]) -> float:
        if not a or not b:
            return 0.0
        dot = sum(x * y for x, y in zip(a, b))
        norm_a = math.sqrt(sum(x * x for x in a)) or 1.0
        norm_b = math.sqrt(sum(y * y for y in b)) or 1.0
        return dot / (norm_a * norm_b)

    def vector_search(
        self,
        query_embedding: Sequence[float],
        gated_ids: List[str],
        top_k: int,
    ) -> List[Dict[str, Any]]:
        if self.backend == "postgres":
            query_param: Any = list(query_embedding)
            if Vector:
                query_param = Vector(query_param)
            params: Dict[str, Any] = {"query": query_param, "top_k": top_k}
            sql = """
            SELECT candidate_id,
                   (1 - (embedding <=> %(query)s)) AS score,
                   (embedding <=> %(query)s) AS distance
            FROM candidate_doc
            WHERE embedding IS NOT NULL
            """
            if gated_ids:
                sql += " AND candidate_id = ANY(%(gated)s)"
                params["gated"] = gated_ids
            sql += " ORDER BY embedding <=> %(query)s LIMIT %(top_k)s"
            rows = self.conn.execute(sql, params).fetchall()
            return [dict(row) for row in rows]

        rows = self.conn.execute(
            "SELECT candidate_id, embedding FROM candidate_doc WHERE embedding IS NOT NULL"
        ).fetchall()
        hits: List[Dict[str, Any]] = []
        for row in rows:
            cid = row[0]
            if gated_ids and cid not in gated_ids:
                continue
            emb = json.loads(row[1]) if row[1] else []
            score = self._cosine_similarity(query_embedding, emb)
            hits.append({"candidate_id": cid, "score": score, "distance": 1.0 - score})
        hits.sort(key=lambda r: (r["distance"], r["candidate_id"]))
        return hits[:top_k]

    def fts_search(
        self,
        query_text: str,
        gated_ids: List[str],
        top_k: int,
    ) -> tuple[List[Dict[str, Any]], str, List[Dict[str, Any]]]:
        if self.backend == "postgres":
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
            sql += " ORDER BY rank DESC LIMIT %(top_k)s"
            plan = self.explain_query_plan(sql, params)
            rows = self.conn.execute(sql, params).fetchall()
            return [dict(row) for row in rows], sql.strip(), plan

        tokens = [t.lower() for t in query_text.split() if t]
        rows = self.conn.execute(
            "SELECT candidate_id, summary_text, experience_text, tags_text FROM candidate_doc"
        ).fetchall()
        scored: List[Dict[str, Any]] = []
        for row in rows:
            cid, summary, experience, tags = row
            if gated_ids and cid not in gated_ids:
                continue
            corpus = " ".join([(summary or ""), (experience or ""), (tags or "")]).lower()
            score = sum(corpus.count(tok) for tok in tokens) if tokens else 0
            if score > 0:
                scored.append({"candidate_id": cid, "rank": float(score)})
        scored.sort(key=lambda r: (-r["rank"], r["candidate_id"]))
        return scored[:top_k], "sqlite_fallback_fts", []

    def reset_agentic_state(self) -> None:
        """
        Truncate all tables when running in agentic mode so tests start clean.
        """
        if not self.settings.agentic_test_mode:
            return
        if self.backend == "postgres":
            try:
                self.conn.execute(
                    "TRUNCATE experience_tag, experience, candidate_doc, candidate_tag, candidate RESTART IDENTITY CASCADE"
                )
                self.commit()
            except (pg_errors.UndefinedTable, AttributeError):
                self.rollback()
        else:
            db_file = Path(self.sqlite_path)
            if db_file.exists():
                try:
                    self.conn.close()
                except Exception:
                    pass
                db_file.unlink()
            self.conn = self._connect_sqlite()
            self._initialize_sqlite_schema()
