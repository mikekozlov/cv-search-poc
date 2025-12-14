from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from cv_search.clients.openai_client import OpenAIClient
from cv_search.config.settings import Settings
from cv_search.db.database import CVDatabase
from cv_search.planner.service import Planner
from cv_search.ranking.hybrid import HybridRanker
from cv_search.retrieval import GatingFilter, LexicalRetriever, PgVectorSemanticRetriever
from cv_search.retrieval.embedder_stub import EmbedderProtocol
from cv_search.search.artifacts import SearchRunArtifactWriter
from cv_search.search.justification import JustificationService


def default_run_dir(base: str | Path | None = None) -> str:
    base_dir = Path(base) if base else Path("runs")
    return str(base_dir / datetime.now().strftime("%Y%m%d-%H%M%S"))


class SearchProcessor:
    """High-level orchestrator for single-seat and multi-seat searches."""

    _GENERIC_WORDS = {
        "developer",
        "developers",
        "engineer",
        "engineers",
        "dev",
        "coder",
        "programmer",
    }
    _STOPWORDS = {
        "need",
        "needs",
        "want",
        "wants",
        "looking",
        "look",
        "for",
        "to",
        "hire",
        "hiring",
        "a",
        "an",
        "the",
        "some",
        "someone",
        "somebody",
        "please",
        "we",
        "i",
        "our",
        "team",
        "project",
    }

    def __init__(
        self,
        db: CVDatabase,
        client: OpenAIClient,
        settings: Settings,
        embedder: EmbedderProtocol | None = None,
    ):
        self.db = db
        self.client = client
        self.settings = settings

        self.gating_filter = GatingFilter(db)
        self.lexical_retriever = LexicalRetriever(db)
        self.semantic_retriever = PgVectorSemanticRetriever(db, settings, embedder=embedder)
        self.hybrid_ranker = HybridRanker(db, settings)
        self.planner = Planner()
        self.artifact_writer = SearchRunArtifactWriter()
        self.justification_service = JustificationService(client, settings, db=db)

    def _is_generic_low_signal(
        self, raw_text: str, criteria: Dict[str, Any], seats: List[Dict[str, Any]]
    ) -> bool:
        tokens = set(re.findall(r"[a-z0-9_+#\\.]+", raw_text.lower()))
        meaningful = tokens - self._STOPWORDS - self._GENERIC_WORDS
        if meaningful:
            return False

        if criteria.get("domain") or criteria.get("tech_stack"):
            return False

        for seat in seats:
            if seat.get("seniority"):
                return False
            if seat.get("domains") or seat.get("tech_tags") or seat.get("nice_to_have"):
                return False

        return bool(tokens & self._GENERIC_WORDS)

    def _extract_seat(self, criteria: Dict[str, Any]) -> Dict[str, Any]:
        seat = criteria["team_size"]["members"][0]
        return {
            "role": seat["role"],
            "seniority": seat["seniority"],
            "domains": seat.get("domains", []),
            "must_have": seat.get("tech_tags", []),
            "nice_to_have": seat.get("nice_to_have", []),
        }

    def _fingerprint(self, seat: Dict[str, Any], mode: str) -> Dict[str, Any]:
        return {
            "role": seat["role"],
            "seniority": seat["seniority"],
            "domains": sorted(seat["domains"]),
            "must_have": sorted(seat["must_have"]),
            "nice_to_have": sorted(seat["nice_to_have"]),
            "mode": mode,
        }

    def _run_single_seat(
        self,
        criteria: Dict[str, Any],
        top_k: int,
        mode_override: str | None,
        vs_topk_override: int | None,
        with_justification: bool,
        run_dir: Optional[str] = None,
    ) -> Dict[str, Any]:
        mode = (mode_override or self.settings.search_mode).lower()
        vs_topk = vs_topk_override or self.settings.search_vs_topk

        seat = self._extract_seat(criteria)

        gated_ids, gating_sql = self.gating_filter.filter_candidates(seat)

        if not gated_ids:
            return {
                "criteria": criteria,
                "query_fingerprint": self._fingerprint(seat, mode),
                "metrics": {
                    "gate_count": 0,
                },
                "gating_sql": gating_sql,
                "ranking_sql": None,
                "ranking_explain": [],
                "vs_query": None,
                "vs_results": None,
                "fusion": None,
                "results": [],
                "reason": "strict_gate_empty",
            }

        lex_limit = max(top_k, vs_topk, len(gated_ids))
        lex_rows, ranking_sql = self.lexical_retriever.search(gated_ids, seat, lex_limit)

        sem_raw = self.semantic_retriever.search(gated_ids, seat, vs_topk)
        sem_hits = sem_raw.get("hits", [])

        final_results, fusion_dump = self.hybrid_ranker.rank(seat, lex_rows, sem_hits, mode, top_k)

        if with_justification and final_results:
            justifications = self.justification_service.generate(
                final_results, seat, run_dir=run_dir
            )
            for item in final_results:
                item["llm_justification"] = justifications.get(item["candidate_id"])

        return {
            "criteria": criteria,
            "query_fingerprint": self._fingerprint(seat, mode),
            "metrics": {
                "gate_count": len(gated_ids),
            },
            "vs_query": sem_raw.get("query"),
            "vs_results": sem_raw,
            "fusion": fusion_dump or None,
            "results": final_results,
            "gating_sql": gating_sql,
            "ranking_sql": ranking_sql,
            "ranking_explain": [],
        }

    def search_for_seat(
        self,
        criteria: Dict[str, Any],
        top_k: int = 10,
        run_dir: str | None = None,
        mode_override: str | None = None,
        vs_topk_override: int | None = None,
        with_justification: bool = True,
    ) -> Dict[str, Any]:
        payload = self._run_single_seat(
            criteria=criteria,
            top_k=top_k,
            mode_override=mode_override,
            vs_topk_override=vs_topk_override,
            with_justification=with_justification,
            run_dir=run_dir,
        )
        if run_dir:
            self.artifact_writer.write(run_dir, payload)
        return payload

    def search_for_project(
        self,
        criteria: Any,
        top_k: int = 3,
        run_dir: Optional[str] = None,
        raw_text: Optional[str] = None,
        with_justification: bool = True,
    ) -> Dict[str, Any]:
        crit_with_seats = self.planner.derive_project_seats(criteria, raw_text=raw_text)
        base_dict = self.planner._criteria_dict(crit_with_seats)

        seats = (base_dict.get("team_size") or {}).get("members") or []
        if raw_text and self._is_generic_low_signal(raw_text, base_dict, seats):
            note = (
                "This brief is too broad to search reliably. "
                "Please specify the role(s) you need and, if possible, seniority, domain, or tech stack."
            )
            return {
                "project_criteria": base_dict,
                "seats": [],
                "gaps": [],
                "run_dir": None,
                "note": note,
                "reason": "low_signal_brief",
            }

        if not seats:
            if raw_text:
                note = (
                    "Not enough information to derive roles from this brief. "
                    "Please specify the role(s) you need and, if possible, seniority, domain, or tech stack."
                )
                reason = "low_signal_brief"
            else:
                note = "Criteria contains no seats; provide team_size.members or use a free-text brief."
                reason = "no_seats_derived"
            return {
                "project_criteria": base_dict,
                "seats": [],
                "gaps": [],
                "run_dir": None,
                "note": note,
                "reason": reason,
            }

        out_dir = run_dir or default_run_dir(self.settings.active_runs_dir)
        Path(out_dir).mkdir(parents=True, exist_ok=True)
        (Path(out_dir) / "criteria.json").write_text(
            json.dumps(base_dict, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        aggregated: List[Dict[str, Any]] = []
        gaps: List[int] = []

        for idx, seat in enumerate(seats, start=1):
            seat_dir = Path(out_dir) / f"seat_{idx:02d}_{seat['role']}"
            single_criteria = self.planner._pack_single_seat_criteria(base_dict, seat)
            payload = self.search_for_seat(
                criteria=single_criteria,
                top_k=top_k,
                run_dir=str(seat_dir),
                mode_override=None,
                vs_topk_override=None,
                with_justification=with_justification,
            )
            aggregated.append(
                {
                    "index": idx,
                    "role": seat["role"],
                    "criteria": single_criteria,
                    "metrics": payload.get("metrics", {}),
                    "results": payload.get("results", []),
                }
            )
            if not payload.get("results"):
                gaps.append(idx)

        return {
            "project_criteria": base_dict,
            "seats": aggregated,
            "gaps": gaps,
            "run_dir": out_dir,
            "note": "Stateless multi-seat search; per-seat artifacts live under run_dir.",
        }
