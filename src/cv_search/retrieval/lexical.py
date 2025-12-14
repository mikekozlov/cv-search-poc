from __future__ import annotations

from typing import Any, Dict, List, Tuple

from cv_search.db.database import CVDatabase


class LexicalRetriever:
    """Weighted-set SQL ranking over structured candidate tags."""

    def __init__(self, db: CVDatabase):
        self.db = db

    def _build_fts_query(self, seat: Dict[str, Any]) -> str:
        parts: List[str] = []
        role = seat.get("role")
        if role:
            parts.append(str(role))
        parts.extend(seat.get("domains") or [])
        parts.extend(seat.get("must_have") or [])
        parts.extend(seat.get("nice_to_have") or [])
        return " ".join([p for p in parts if p]).strip()

    def search(
        self,
        gated_ids: List[str],
        seat: Dict[str, Any],
        top_k: int,
    ) -> Tuple[List[Any], str]:
        must_have = [t for t in dict.fromkeys(seat.get("must_have", [])) if t]
        nice_deduped = [t for t in dict.fromkeys(seat.get("nice_to_have", [])) if t]
        must_set = set(must_have)
        nice_to_have = [t for t in nice_deduped if t not in must_set]
        domains = [d for d in dict.fromkeys(seat.get("domains", [])) if d]
        seat = {**seat, "must_have": must_have, "nice_to_have": nice_to_have, "domains": domains}

        idf_must = self.db.compute_idf(must_have, "tech")
        idf_nice = self.db.compute_idf(nice_to_have, "tech")

        ranked_rows, ranking_sql = self.db.rank_weighted_set(
            gated_ids=gated_ids,
            must_have=must_have,
            nice_to_have=nice_to_have,
            domains=domains,
            idf_must=idf_must,
            idf_nice=idf_nice,
            top_k=top_k,
        )

        fts_sql: str | None = None
        fts_map: Dict[str, float] = {}
        fts_query = self._build_fts_query(seat)
        if fts_query:
            fts_rows, fts_sql = self.db.fts_search(fts_query, gated_ids, top_k)
            fts_map = {row["candidate_id"]: float(row.get("rank", 0.0) or 0.0) for row in fts_rows}

        for row in ranked_rows:
            row["fts_rank"] = fts_map.get(row["candidate_id"], 0.0)

        combined_sql = ranking_sql if not fts_sql else f"{ranking_sql}\n---\n{fts_sql}"
        return ranked_rows, combined_sql
