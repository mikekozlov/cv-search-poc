from __future__ import annotations

from typing import Any, Dict, List

from cv_search.config.settings import Settings
from cv_search.db.database import CVDatabase
from cv_search.retrieval.embedder_stub import DeterministicEmbedder, EmbedderProtocol
from cv_search.retrieval.local_embedder import LocalEmbedder


class PgVectorSemanticRetriever:
    """Vector-based retrieval backed by Postgres pgvector."""

    def __init__(self, db: CVDatabase, settings: Settings, embedder: EmbedderProtocol | None = None):
        self.db = db
        self.settings = settings
        if embedder:
            self.embedder = embedder
        elif settings.agentic_test_mode:
            self.embedder = DeterministicEmbedder()
        else:
            self.embedder = LocalEmbedder()

    def _build_vs_query(self, seat: Dict[str, Any]) -> str:
        role = seat["role"].replace("_", " ")
        seniority = seat["seniority"]
        domains = ", ".join(seat.get("domains") or []) if seat.get("domains") else "any domain"
        musts = ", ".join(seat.get("must_have") or []) if seat.get("must_have") else "(no hard musts)"
        nice = ", ".join(seat.get("nice_to_have") or []) if seat.get("nice_to_have") else "(optional)"
        return (
            f"{seniority} {role} in {domains}. "
            f"Must: {musts}. Nice: {nice}. "
            f"Prefer demonstrated outcomes and similar patterns (latency, availability, LCP, etc.)."
        )

    def search(self, gated_ids: List[str], seat: Dict[str, Any], top_k: int) -> Dict[str, Any]:
        vs_query = self._build_vs_query(seat)
        try:
            query_vec = self.embedder.get_embeddings([vs_query])[0]
            rows = self.db.vector_search(query_vec, gated_ids, top_k)
            hits: List[Dict[str, Any]] = []
            for idx, row in enumerate(rows, start=1):
                hits.append(
                    {
                        "rank": idx,
                        "candidate_id": row["candidate_id"],
                        "score": float(row.get("score", 0.0)),
                        "distance": float(row.get("distance", 0.0)),
                        "reason": "pgvector_similarity",
                    }
                )
            return {"query": vs_query, "hits": hits, "source": "pgvector"}
        except Exception as exc:  # pragma: no cover - protective logging
            print(f"Error during pgvector search: {exc}")
            try:
                self.db.rollback()
            except Exception:
                pass
            return {"query": vs_query, "hits": [], "source": "pgvector_error"}
