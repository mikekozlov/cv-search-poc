from __future__ import annotations

# Backward-compatible import shim: semantic retrieval now uses Postgres pgvector.
from cv_search.retrieval.pgvector import PgVectorSemanticRetriever as LocalSemanticRetriever

__all__ = ["LocalSemanticRetriever"]
