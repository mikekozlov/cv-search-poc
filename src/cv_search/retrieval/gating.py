from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from cv_search.db.database import CVDatabase


@dataclass
class GatingDiagnostics:
    """Diagnostic information when gating filter returns no results."""

    role_requested: str = ""
    seniority_requested: str = ""
    allowed_seniorities: List[str] = field(default_factory=list)
    candidates_with_role: int = 0
    candidates_with_seniority: int = 0
    available_roles: List[str] = field(default_factory=list)
    suggestion: Optional[str] = None

    def to_reason(self) -> str:
        """Generate a descriptive reason string."""
        parts = [f"No candidates match role='{self.role_requested}'"]
        if self.seniority_requested:
            parts[0] += f" with seniority in {self.allowed_seniorities}"

        if self.candidates_with_role == 0:
            parts.append(f"Role '{self.role_requested}' not found in database.")
            if self.available_roles:
                similar = [
                    r
                    for r in self.available_roles
                    if self.role_requested.replace(" ", "_") in r
                    or r in self.role_requested.replace(" ", "_")
                ]
                if similar:
                    parts.append(f"Did you mean: {', '.join(similar[:3])}?")
                else:
                    parts.append(f"Available roles: {', '.join(self.available_roles[:10])}")
        elif self.candidates_with_seniority == 0:
            parts.append(
                f"Found {self.candidates_with_role} candidates with role '{self.role_requested}' but none match seniority {self.allowed_seniorities}."
            )

        if self.suggestion:
            parts.append(self.suggestion)

        return " ".join(parts)


def _normalize_seniority(s: str) -> str:
    if not s:
        return ""
    s = s.strip().lower()
    mapping = {
        "mid": "middle",
        "jr": "junior",
        "sr": "senior",
        "staff": "lead",
        "principal": "manager",
    }
    return mapping.get(s, s)


def _allowed_seniorities(seat_seniority: str) -> Tuple[str, ...]:
    ladder = ("junior", "middle", "senior", "lead", "manager")
    norm = _normalize_seniority(seat_seniority)
    if norm not in ladder:
        return ("senior",)
    idx = ladder.index(norm)
    return ladder[idx:]


@dataclass
class GatingResult:
    """Result of gating filter operation."""

    candidate_ids: List[str]
    rendered_sql: str
    diagnostics: Optional[GatingDiagnostics] = None


class GatingFilter:
    """Strict candidate filtering based on role and seniority."""

    def __init__(self, db: CVDatabase):
        self.db = db

    def filter_candidates(self, seat: Dict[str, Any]) -> Tuple[List[str], str]:
        """Filter candidates - returns (ids, rendered_sql) for backward compatibility."""
        result = self.filter_candidates_with_diagnostics(seat)
        return result.candidate_ids, result.rendered_sql

    def filter_candidates_with_diagnostics(self, seat: Dict[str, Any]) -> GatingResult:
        """Filter candidates with detailed diagnostics on empty results."""
        role = seat["role"]
        seniority = seat.get("seniority", "")
        allowed_seniorities = tuple(_allowed_seniorities(seniority))
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
        rendered_sql = self.db.render_sql(sql, params)
        rows = self.db.conn.execute(sql, params).fetchall()
        ids = [r["candidate_id"] if hasattr(r, "keys") else r[0] for r in rows]

        diagnostics = None
        if not ids:
            diagnostics = self._build_diagnostics(role, seniority, list(allowed_seniorities))

        return GatingResult(candidate_ids=ids, rendered_sql=rendered_sql, diagnostics=diagnostics)

    def _build_diagnostics(
        self, role: str, seniority: str, allowed_seniorities: List[str]
    ) -> GatingDiagnostics:
        """Build diagnostic info when no candidates match."""
        diag = GatingDiagnostics(
            role_requested=role,
            seniority_requested=seniority,
            allowed_seniorities=allowed_seniorities,
        )

        # Count candidates with the requested role
        role_count_sql = """
            SELECT COUNT(DISTINCT candidate_id) as cnt
            FROM candidate_tag
            WHERE tag_type = 'role' AND tag_key = %s
        """
        row = self.db.conn.execute(role_count_sql, (role,)).fetchone()
        diag.candidates_with_role = row["cnt"] if hasattr(row, "keys") else row[0]

        # If role exists, check seniority mismatch
        if diag.candidates_with_role > 0:
            seniority_count_sql = """
                SELECT COUNT(DISTINCT c.candidate_id) as cnt
                FROM candidate_tag c
                JOIN candidate_tag s ON c.candidate_id = s.candidate_id
                WHERE c.tag_type = 'role' AND c.tag_key = %s
                  AND s.tag_type = 'seniority' AND s.tag_key = ANY(%s)
            """
            row = self.db.conn.execute(seniority_count_sql, (role, allowed_seniorities)).fetchone()
            diag.candidates_with_seniority = row["cnt"] if hasattr(row, "keys") else row[0]
        else:
            # Role not found - get available roles for suggestions
            available_roles_sql = """
                SELECT tag_key, COUNT(*) as cnt
                FROM candidate_tag
                WHERE tag_type = 'role'
                GROUP BY tag_key
                ORDER BY cnt DESC
                LIMIT 20
            """
            rows = self.db.conn.execute(available_roles_sql).fetchall()
            diag.available_roles = [r["tag_key"] if hasattr(r, "keys") else r[0] for r in rows]

        return diag
