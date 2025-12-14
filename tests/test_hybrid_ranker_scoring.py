from __future__ import annotations

from dataclasses import dataclass

from cv_search.ranking.hybrid import HybridRanker


class _StubDB:
    def fetch_tag_hits(self, candidate_ids, tags):
        return {}


@dataclass(frozen=True)
class _StubSettings:
    search_w_lex: float = 1.0
    search_w_sem: float = 1.0


def test_hybrid_prefers_higher_semantic_score_over_rank_position():
    ranker = HybridRanker(db=_StubDB(), settings=_StubSettings(search_w_lex=0.0, search_w_sem=1.0))
    seat = {"role": "backend_engineer", "seniority": "senior", "must_have": [], "nice_to_have": []}

    results, _ = ranker.rank(
        seat=seat,
        lexical_results=[],
        semantic_hits=[
            {"rank": 1, "candidate_id": "cand_low", "score": 0.1, "distance": 0.9},
            {"rank": 2, "candidate_id": "cand_high", "score": 0.9, "distance": 0.1},
        ],
        mode="hybrid",
        top_k=2,
    )

    assert [r["candidate_id"] for r in results] == ["cand_high", "cand_low"]
    assert results[0]["score_components"]["semantic"]["score"] == 0.9


def test_lexical_mode_is_sorted_by_lexical_scoring_formula():
    ranker = HybridRanker(db=_StubDB(), settings=_StubSettings())
    seat = {
        "role": "backend_engineer",
        "seniority": "senior",
        "must_have": ["python", "postgresql"],
        "nice_to_have": [],
    }

    lexical_results = [
        {
            "candidate_id": "cand_low",
            "must_hit_count": 1,
            "nice_hit_count": 0,
            "must_idf_sum": 1.0,
            "nice_idf_sum": 0.0,
            "must_idf_total": 4.0,
            "nice_idf_total": 0.0,
            "domain_present": False,
            "fts_rank": 0.0,
            "last_updated": "2024-01-01",
        },
        {
            "candidate_id": "cand_high",
            "must_hit_count": 1,
            "nice_hit_count": 0,
            "must_idf_sum": 4.0,
            "nice_idf_sum": 0.0,
            "must_idf_total": 4.0,
            "nice_idf_total": 0.0,
            "domain_present": False,
            "fts_rank": 0.0,
            "last_updated": "2024-01-01",
        },
    ]

    results, _ = ranker.rank(
        seat=seat,
        lexical_results=lexical_results,
        semantic_hits=[],
        mode="lexical",
        top_k=2,
    )

    assert [r["candidate_id"] for r in results] == ["cand_high", "cand_low"]
