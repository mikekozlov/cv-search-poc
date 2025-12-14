from __future__ import annotations
from typing import Any, Dict, List, Tuple

from cv_search.config.settings import Settings
from cv_search.db.database import CVDatabase


class HybridRanker:
    """
    Handles the "late fusion" of lexical and semantic search results
    and assembles the final evidence payload for a candidate.
    """

    def __init__(self, db: CVDatabase, settings: Settings):
        self.db = db
        self.settings = settings
        self.w_lex = settings.search_w_lex
        self.w_sem = settings.search_w_sem

    def _fetch_tag_hits(
        self, candidate_ids: List[str], tags: List[str]
    ) -> Dict[str, Dict[str, bool]]:
        """(Logic moved from search.py)"""
        return self.db.fetch_tag_hits(candidate_ids, tags)

    def _assemble_item(
        self,
        cid: str,
        seat: Dict[str, Any],
        final_score: float,
        order: int,
        lex_map: Dict[str, Dict[str, Any]],
        sem_score: Dict[str, float],
        sem_evidence: Dict[str, Dict[str, Any]],
    ) -> Dict[str, Any]:
        """
        Builds the final JSON object for a single ranked candidate.
        (Logic moved from search.py/_assemble_item)
        """
        tech_evidence_tags = list(dict.fromkeys(seat["must_have"] + seat["nice_to_have"]))
        tech_hits = self._fetch_tag_hits([cid], tech_evidence_tags)
        must_map = {t: bool(tech_hits.get(cid, {}).get(t, False)) for t in seat["must_have"]}
        nice_map = {t: bool(tech_hits.get(cid, {}).get(t, False)) for t in seat["nice_to_have"]}

        lex = lex_map.get(
            cid,
            {
                "score_val": 0.0,
                "coverage": 0.0,
                "must_idf_sum": 0.0,
                "nice_idf_sum": 0.0,
                "domain_bonus": 0.0,
                "last_updated": None,
            },
        )

        return {
            "candidate_id": cid,
            "score": {"value": final_score, "order": order},
            "score_components": {
                "lexical": {
                    "raw": lex["score_val"],
                    "coverage": lex["coverage"],
                    "must_idf_sum": lex["must_idf_sum"],
                    "nice_idf_sum": lex["nice_idf_sum"],
                    "domain_bonus": lex["domain_bonus"],
                },
                "semantic": {"score": float(sem_score.get(cid, 0.0))},
                "weights": {"w_lex": self.w_lex, "w_sem": self.w_sem},
            },
            "semantic_evidence": sem_evidence.get(cid, None),
            "must_have": must_map,
            "nice_to_have": nice_map,
            "recency": {"last_updated": lex.get("last_updated")},
        }

    def rank(
        self,
        seat: Dict[str, Any],
        lexical_results: List[Dict[str, Any]],
        semantic_hits: List[Dict[str, Any]],
        mode: str,
        top_k: int,
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """
        Performs late fusion and ranking based on the specified mode.
        Returns (final_results, fusion_debug_dump)
        (Logic moved from search.py)
        """

        # 1. Build lexical map
        lex_map: Dict[str, Dict[str, Any]] = {}
        for order, row in enumerate(lexical_results, start=1):
            cid = row["candidate_id"]
            M = float(max(1, len(seat.get("must_have", []))))
            coverage = float(row.get("must_hit_count", 0)) / M
            must_idf_sum = float(row.get("must_idf_sum") or 0.0)
            nice_idf_sum = float(row.get("nice_idf_sum") or 0.0)
            must_idf_total = float(row.get("must_idf_total") or 0.0)
            nice_idf_total = float(row.get("nice_idf_total") or 0.0)
            must_idf_cov = must_idf_sum / must_idf_total if must_idf_total > 0 else 0.0
            nice_idf_cov = nice_idf_sum / nice_idf_total if nice_idf_total > 0 else 0.0
            domain_hit = bool(row.get("domain_present"))
            fts_rank = float(row.get("fts_rank") or 0.0)
            lex_score_val = (
                2.0 * coverage
                + 1.0 * must_idf_cov
                + 0.3 * nice_idf_cov
                + 0.5 * (1.0 if domain_hit else 0.0)
                + 0.4 * fts_rank
            )
            lex_map[cid] = {
                "score_val": lex_score_val,
                "coverage": coverage,
                "must_idf_sum": must_idf_sum,
                "nice_idf_sum": nice_idf_sum,
                "domain_bonus": 0.5 if domain_hit else 0.0,
                "fts_rank": fts_rank,
                "last_updated": row.get("last_updated"),
                "rank_order": order,
            }

        # 2. Build semantic map
        sem_score: Dict[str, float] = {}
        sem_evidence: Dict[str, Dict[str, Any]] = {}
        for h in semantic_hits:
            cid = h["candidate_id"]
            raw = h.get("score")
            if raw is None:
                raw = 1.0 - float(h.get("distance", 0.0) or 0.0)
            val = float(raw or 0.0)
            if val < 0.0:
                val = 0.0
            elif val > 1.0:
                val = 1.0
            sem_score[cid] = val
            sem_evidence[cid] = {"file_id": h.get("file_id", ""), "reason": h.get("reason", "")}

        # 3. Assemble results based on mode
        final_results: List[Dict[str, Any]] = []
        fusion_dump: List[Dict[str, Any]] = []

        if mode == "lexical":

            def _last_upd(cid: str):
                v = lex_map.get(cid, {}).get("last_updated")
                return v or ""

            ranked_ids = sorted(
                lex_map.keys(),
                key=lambda c: (-lex_map[c]["score_val"], _last_upd(c), c),
            )
            for i, cid in enumerate(ranked_ids[:top_k], start=1):
                final_results.append(
                    self._assemble_item(
                        cid, seat, lex_map[cid]["score_val"], i, lex_map, sem_score, sem_evidence
                    )
                )

        elif mode == "semantic":
            cut = semantic_hits[:top_k]
            for i, h in enumerate(cut, start=1):
                cid = h["candidate_id"]
                final_results.append(
                    self._assemble_item(
                        cid, seat, sem_score.get(cid, 0.0), i, lex_map, sem_score, sem_evidence
                    )
                )

        else:  # hybrid

            def _last_upd(cid: str):
                v = lex_map.get(cid, {}).get("last_updated")
                return v or ""

            lex_top = sorted(
                lex_map.keys(),
                key=lambda c: (-lex_map[c]["score_val"], _last_upd(c), c),
            )[:top_k]
            pool_ids = list(
                dict.fromkeys(lex_top + [h["candidate_id"] for h in semantic_hits[:top_k]])
            )
            if not pool_ids:
                pool_ids = lex_top

            lex_vals = [lex_map.get(cid, {"score_val": 0.0})["score_val"] for cid in pool_ids]
            lx_min, lx_max = (min(lex_vals), max(lex_vals)) if lex_vals else (0.0, 0.0)

            def _norm_lex(v: float) -> float:
                return 0.0 if lx_max <= lx_min else (v - lx_min) / (lx_max - lx_min)

            fused = []
            for cid in pool_ids:
                lx = _norm_lex(lex_map.get(cid, {"score_val": 0.0})["score_val"])
                sm = sem_score.get(cid, 0.0)
                final = self.w_lex * lx + self.w_sem * sm
                fused.append((cid, final, lx, sm))

            fused.sort(key=lambda t: (-t[1], _last_upd(t[0]), t[0]))

            for order, (cid, final, lx, sm) in enumerate(fused[:top_k], start=1):
                fusion_dump.append({"candidate_id": cid, "lex_norm": lx, "sem": sm, "final": final})
                final_results.append(
                    self._assemble_item(cid, seat, final, order, lex_map, sem_score, sem_evidence)
                )

        return final_results, fusion_dump
