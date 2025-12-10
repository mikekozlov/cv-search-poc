from __future__ import annotations

from typing import Any, Dict, List, Tuple

from cv_search.db.database import CVDatabase


def _normalize_seniority(s: str) -> str:
    if not s:
        return ""
    s = s.strip().lower()
    mapping = {"mid": "middle", "jr": "junior", "sr": "senior", "staff": "lead", "principal": "manager"}
    return mapping.get(s, s)


def _allowed_seniorities(seat_seniority: str) -> Tuple[str, ...]:
    ladder = ("junior", "middle", "senior", "lead", "manager")
    norm = _normalize_seniority(seat_seniority)
    if norm not in ladder:
        return ("senior",)
    idx = ladder.index(norm)
    return ladder[idx:]


class GatingFilter:
    """Strict candidate filtering based on role and seniority."""

    def __init__(self, db: CVDatabase):
        self.db = db
    def filter_candidates(self, seat: Dict[str, Any]) -> Tuple[List[str], str]:
        role = seat["role"]
        allowed_seniorities = tuple(_allowed_seniorities(seat["seniority"]))
        if getattr(self.db, "backend", "postgres") == "postgres":
            sql = """
    WITH gated AS (
      SELECT c.candidate_id
      FROM candidate c
      WHERE EXISTS (
        SELECT 1
        FROM candidate_tag t
        WHERE t.candidate_id = c.candidate_id
          AND t.tag_type = 'role'
          AND t.tag_key  = %s
      )
      AND EXISTS (
        SELECT 1
        FROM candidate_tag t
        WHERE t.candidate_id = c.candidate_id
          AND t.tag_type = 'seniority'
          AND t.tag_key  = ANY(%s)
      )
    )
    SELECT candidate_id FROM gated
    """
            params: Tuple[Any, ...] = (role, list(allowed_seniorities))
        else:
            placeholders = ",".join(["?"] * len(allowed_seniorities))
            sql = f"""
    WITH gated AS (
      SELECT c.candidate_id
      FROM candidate c
      WHERE EXISTS (
        SELECT 1
        FROM candidate_tag t
        WHERE t.candidate_id = c.candidate_id
          AND t.tag_type = 'role'
          AND t.tag_key  = ?
      )
      AND EXISTS (
        SELECT 1
        FROM candidate_tag t
        WHERE t.candidate_id = c.candidate_id
          AND t.tag_type = 'seniority'
          AND t.tag_key  IN ({placeholders})
      )
    )
    SELECT candidate_id FROM gated
    """
            params = (role, *allowed_seniorities)
        rows = self.db.conn.execute(sql, params).fetchall()
        ids = [r["candidate_id"] if hasattr(r, "keys") else r[0] for r in rows]
        return ids, sql.strip()
