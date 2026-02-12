from __future__ import annotations

import json
import random
import re
from typing import Any, Dict, List, Set, Tuple

from cv_search.clients.openai_client import OpenAIClient
from cv_search.config.settings import Settings
from cv_search.db.database import CVDatabase

LEXICAL_WEIGHTS = {
    "coverage": 2.0,
    "must_idf": 1.0,
    "nice_idf": 0.3,
    "domain_bonus": 0.5,
    "expertise_idf": 0.8,
    "fts_rank": 0.4,
}


def _clamp01(x: float) -> float:
    if x < 0.0:
        return 0.0
    if x > 1.0:
        return 1.0
    return x


def _truncate(text: str, max_chars: int) -> str:
    s = (text or "").strip()
    if max_chars <= 0:
        return ""
    if len(s) <= max_chars:
        return s
    head = s[: max(0, max_chars - 14)].rstrip()
    return head + "\n...(truncated)"


class LLMVerdictRanker:
    """
    Lexical retrieval only. LLM provides final ordering (and verdict).
    No semantic retrieval. No hybrid reranking.
    """

    def __init__(self, db: CVDatabase, client: OpenAIClient, settings: Settings):
        self.db = db
        self.client = client
        self.settings = settings

    def _build_lex_map(
        self, seat: Dict[str, Any], lexical_rows: List[Dict[str, Any]]
    ) -> Dict[str, Dict[str, Any]]:
        lex_map: Dict[str, Dict[str, Any]] = {}
        must_count = len(seat.get("must_have", []) or [])
        nice_count = len(seat.get("nice_to_have", []) or [])
        expertise_count = len(seat.get("expertise", []) or [])

        for order, row in enumerate(lexical_rows, start=1):
            cid = row["candidate_id"]
            coverage_denominator = float(max(1, must_count))
            must_hit_count = int(row.get("must_hit_count") or 0)
            nice_hit_count = int(row.get("nice_hit_count") or 0)
            expertise_hit_count = int(row.get("expertise_hit_count") or 0)

            coverage = must_hit_count / coverage_denominator
            must_idf_sum = float(row.get("must_idf_sum") or 0.0)
            nice_idf_sum = float(row.get("nice_idf_sum") or 0.0)
            expertise_idf_sum = float(row.get("expertise_idf_sum") or 0.0)
            must_idf_total = float(row.get("must_idf_total") or 0.0)
            nice_idf_total = float(row.get("nice_idf_total") or 0.0)
            expertise_idf_total = float(row.get("expertise_idf_total") or 0.0)

            must_idf_cov = must_idf_sum / must_idf_total if must_idf_total > 0 else 0.0
            nice_idf_cov = nice_idf_sum / nice_idf_total if nice_idf_total > 0 else 0.0
            expertise_idf_cov = (
                expertise_idf_sum / expertise_idf_total if expertise_idf_total > 0 else 0.0
            )

            domain_hit = bool(row.get("domain_present"))
            fts_rank = float(row.get("fts_rank") or 0.0)

            lex_score_val = (
                LEXICAL_WEIGHTS["coverage"] * coverage
                + LEXICAL_WEIGHTS["must_idf"] * must_idf_cov
                + LEXICAL_WEIGHTS["nice_idf"] * nice_idf_cov
                + LEXICAL_WEIGHTS["domain_bonus"] * (1.0 if domain_hit else 0.0)
                + LEXICAL_WEIGHTS["expertise_idf"] * expertise_idf_cov
                + LEXICAL_WEIGHTS["fts_rank"] * fts_rank
            )
            terms = {
                "coverage": LEXICAL_WEIGHTS["coverage"] * coverage,
                "must_idf": LEXICAL_WEIGHTS["must_idf"] * must_idf_cov,
                "nice_idf": LEXICAL_WEIGHTS["nice_idf"] * nice_idf_cov,
                "domain_bonus": LEXICAL_WEIGHTS["domain_bonus"] * (1.0 if domain_hit else 0.0),
                "expertise_idf": LEXICAL_WEIGHTS["expertise_idf"] * expertise_idf_cov,
                "fts_rank": LEXICAL_WEIGHTS["fts_rank"] * fts_rank,
            }

            lex_map[cid] = {
                "score_val": float(lex_score_val),
                "coverage": float(coverage),
                "coverage_denominator": float(coverage_denominator),
                "must_hit_count": must_hit_count,
                "nice_hit_count": nice_hit_count,
                "expertise_hit_count": expertise_hit_count,
                "must_count": must_count,
                "nice_count": nice_count,
                "expertise_count": expertise_count,
                "must_idf_sum": must_idf_sum,
                "nice_idf_sum": nice_idf_sum,
                "expertise_idf_sum": expertise_idf_sum,
                "must_idf_total": must_idf_total,
                "nice_idf_total": nice_idf_total,
                "expertise_idf_total": expertise_idf_total,
                "must_idf_cov": float(must_idf_cov),
                "nice_idf_cov": float(nice_idf_cov),
                "expertise_idf_cov": float(expertise_idf_cov),
                "domain_hit": bool(domain_hit),
                "domain_bonus": 0.5 if domain_hit else 0.0,
                "fts_rank": fts_rank,
                "weights": dict(LEXICAL_WEIGHTS),
                "terms": terms,
                "last_updated": row.get("last_updated"),
                "rank_order": order,
            }
        return lex_map

    def _extract_evidence_context(
        self,
        ctx: Dict[str, Any],
        must_have_tags: List[str],
        nice_to_have_tags: List[str],
        matched_must_have: List[str],
        max_chars: int,
    ) -> str:
        """Build compact evidence-only context for LLM ranking.

        Returns a structured evidence block instead of full CV text:
        - SUMMARY_SNIPPET: First sentence from summary
        - MISSING_MUST_HAVE: Tags from must_have not matched
        - MATCHED_NICE_HAVE: Tags from nice_to_have that are matched
        - EXPERIENCE_EVIDENCE: 1-2 sentences containing must-have terms
        """
        summary = (ctx.get("summary_text") or "").strip()
        experience = (ctx.get("experience_text") or "").strip()
        tags_text = (ctx.get("tags_text") or "").strip()

        # 1. Summary snippet: first sentence, max 120 chars
        summary_snippet = ""
        if summary:
            # Split on sentence boundaries
            first_sentence_match = re.match(r"^[^.!?\n]+[.!?]?", summary)
            if first_sentence_match:
                summary_snippet = first_sentence_match.group(0).strip()[:120]
            else:
                summary_snippet = summary[:120]

        # 2. Missing must-haves
        matched_set: Set[str] = set(matched_must_have)
        missing_must_have = [t for t in must_have_tags if t not in matched_set]
        missing_str = ",".join(missing_must_have) if missing_must_have else "none"

        # 3. Matched nice-to-haves: check which nice_to_have tags appear in tags_text
        tags_lower = tags_text.lower()
        matched_nice = [t for t in nice_to_have_tags if t.lower() in tags_lower]
        matched_nice_str = ",".join(matched_nice) if matched_nice else "none"

        # 4. Experience evidence: find 1-2 sentences containing must-have terms
        evidence_sentences: List[str] = []
        if experience and must_have_tags:
            # Split experience into sentences
            sentences = re.split(r"(?<=[.!?])\s+", experience)
            # Find sentences containing any must-have tag
            search_terms = set(t.lower() for t in must_have_tags)
            for sentence in sentences:
                sentence_lower = sentence.lower()
                if any(term in sentence_lower for term in search_terms):
                    # Truncate long sentences
                    evidence_sentences.append(sentence[:150].strip())
                    if len(evidence_sentences) >= 2:
                        break

        evidence_str = (
            " | ".join(evidence_sentences) if evidence_sentences else "No direct evidence."
        )

        # Build compact context
        lines = [
            f"SUMMARY_SNIPPET: {summary_snippet}" if summary_snippet else "",
            f"MISSING_MUST_HAVE: {missing_str}",
            f"MATCHED_NICE_HAVE: {matched_nice_str}",
            f"EXPERIENCE_EVIDENCE: {evidence_str}",
        ]
        compact = "\n".join(line for line in lines if line)

        # Truncate if still over budget
        if len(compact) > max_chars:
            compact = compact[: max_chars - 14] + "\n...(truncated)"

        return compact

    def _format_candidates_for_llm(
        self,
        seat: Dict[str, Any],
        pool_rows: List[Dict[str, Any]],
        lex_map: Dict[str, Dict[str, Any]],
        contexts: Dict[str, Dict[str, Any]],
        tag_hits: Dict[str, Dict[str, bool]] | None = None,
    ) -> str:
        use_compact = self.settings.search_llm_compact_context
        max_chars = int(
            self.settings.search_llm_evidence_max_chars
            if use_compact
            else self.settings.search_llm_context_chars
        )
        must_have_tags = seat.get("must_have") or []
        nice_to_have_tags = seat.get("nice_to_have") or []

        lines: List[str] = [f'<candidates count="{len(pool_rows)}">']
        for idx, row in enumerate(pool_rows, start=1):
            cid = row["candidate_id"]
            lex = lex_map.get(cid, {})
            ctx = contexts.get(cid, {}) or {}
            last_updated = ctx.get("last_updated", "") or row.get("last_updated", "") or ""
            seniority = ctx.get("seniority", "") or ""

            # Compute matched must_have tags for this candidate
            matched_must_have: List[str] = []
            if tag_hits and cid in tag_hits:
                candidate_hits = tag_hits[cid]
                matched_must_have = [t for t in must_have_tags if candidate_hits.get(t, False)]
            matched_must_have_str = ",".join(matched_must_have) if matched_must_have else ""

            # Expertise hit indicator
            expertise_hit = 1 if int(row.get("expertise_hit_count") or 0) > 0 else 0

            # Build CV context: compact evidence-only or full text
            if use_compact:
                cv_context = self._extract_evidence_context(
                    ctx=ctx,
                    must_have_tags=must_have_tags,
                    nice_to_have_tags=nice_to_have_tags,
                    matched_must_have=matched_must_have,
                    max_chars=max_chars,
                )
            else:
                summary = ctx.get("summary_text", "") or ""
                experience = ctx.get("experience_text", "") or ""
                tags = ctx.get("tags_text", "") or ""
                cv_context = f"SUMMARY:\n{summary}\n\nEXPERIENCE:\n{experience}\n\nTAGS:\n{tags}"
                cv_context = _truncate(cv_context, max_chars)

            lines.append(
                f'\n<candidate id="{cid}" prompt_position="{idx}" '
                f'lexical_rank="{lex.get("rank_order", 0)}" '
                f'lexical_score="{float(lex.get("score_val", 0.0)):.4f}" '
                f'must_hit_count="{int(row.get("must_hit_count") or 0)}" '
                f'matched_must_have="{matched_must_have_str}" '
                f'nice_hit_count="{int(row.get("nice_hit_count") or 0)}" '
                f'expertise_hit="{expertise_hit}" '
                f'domain_hit="{1 if row.get("domain_present") else 0}" '
                f'last_updated="{last_updated}" seniority="{seniority}">'
            )
            lines.append(cv_context)
            lines.append("</candidate>")

        lines.append("\n</candidates>")
        return "\n".join(lines)

    def rank(
        self,
        seat: Dict[str, Any],
        lexical_rows: List[Dict[str, Any]],
        top_k: int,
        *,
        run_dir: str | None = None,
        pool_size_override: int | None = None,
    ) -> Tuple[List[Dict[str, Any]], Dict[str, Any], int]:
        if not lexical_rows:
            return (
                [],
                {
                    "pool_candidate_ids": [],
                    "llm_response": {"ranked_candidates": []},
                    "usage": None,
                },
                0,
            )

        top_k = max(1, int(top_k))
        pool_mult = max(1, int(self.settings.search_llm_pool_multiplier))
        pool_cap = max(1, int(self.settings.search_llm_pool_max))

        # Use override if provided, otherwise calculate from settings
        if pool_size_override is not None:
            pool_target = min(len(lexical_rows), max(1, pool_size_override))
        else:
            pool_target = min(len(lexical_rows), min(pool_cap, top_k * pool_mult))

        pool_rows = lexical_rows[:pool_target]
        pool_ids = [r["candidate_id"] for r in pool_rows]
        pool_set = set(pool_ids)

        lex_map = self._build_lex_map(seat, pool_rows)
        contexts = self.db.get_full_candidate_contexts(pool_ids)

        # Fetch tag hits for must_have tags to show which ones matched per candidate
        must_have_tags = seat.get("must_have") or []
        pool_tag_hits = self.db.fetch_tag_hits(pool_ids, must_have_tags) if must_have_tags else {}

        # Shuffle candidate order to mitigate LLM positional bias
        # Lexical scores remain visible in attributes; only prompt position changes
        shuffled_pool_rows = pool_rows.copy()
        random.shuffle(shuffled_pool_rows)

        candidates_block = self._format_candidates_for_llm(
            seat, shuffled_pool_rows, lex_map, contexts, pool_tag_hits
        )

        # Use compact JSON (no indent) to reduce tokens
        seat_json = json.dumps(seat, ensure_ascii=False)
        compact_output = self.settings.search_llm_tiered_output
        try:
            # Ask LLM to rank ALL candidates in the pool for consistent results
            llm_resp = self.client.get_candidate_ranking(
                seat_json,
                candidates_block,
                pool_size=len(pool_ids),
                top_k=top_k,
                compact_output=compact_output,
            )
        except Exception as exc:
            llm_resp = {
                "all_scores": [],
                "top_k_verdicts": [],
                "notes": f"llm_error: {type(exc).__name__}: {exc}",
            }

        # Parse response - handle both compact (all_scores + top_k_verdicts) and legacy formats
        all_ranked_ids: List[str] = []
        verdict_map: Dict[str, Dict[str, Any]] = {}
        score_map: Dict[str, float] = {}
        used: Set[str] = set()

        if "all_scores" in llm_resp:
            # Compact format: all_scores + top_k_verdicts
            all_scores = llm_resp.get("all_scores") or []
            top_k_verdicts = llm_resp.get("top_k_verdicts") or []

            # Build score map from all_scores
            for item in all_scores:
                cid = (item or {}).get("candidate_id")
                if not cid or cid not in pool_set or cid in used:
                    continue
                used.add(cid)
                all_ranked_ids.append(cid)
                score_map[cid] = float((item or {}).get("overall_match_score") or 0.0)

            # Build verdict map from top_k_verdicts
            for item in top_k_verdicts:
                cid = (item or {}).get("candidate_id")
                if cid and cid in pool_set:
                    verdict_map[cid] = dict(item)
        else:
            # Legacy format: ranked_candidates with full verdicts
            ranked_candidates = llm_resp.get("ranked_candidates") or []
            for item in ranked_candidates:
                cid = (item or {}).get("candidate_id")
                if not cid or cid not in pool_set or cid in used:
                    continue
                used.add(cid)
                all_ranked_ids.append(cid)
                verdict_map[cid] = dict(item)
                score_map[cid] = float((item or {}).get("overall_match_score") or 0.0)

        # Fill any missing candidates with lexical fallback (in case LLM missed some)
        for cid in pool_ids:
            if cid in used:
                continue
            used.add(cid)
            all_ranked_ids.append(cid)
            score_map[cid] = 0.0

        # Slice to top_k after full ranking for consistent results
        ranked_ids = all_ranked_ids[:top_k]

        # Build tag hit maps once for all ranked ids
        evidence_tags = list(
            dict.fromkeys((seat.get("must_have") or []) + (seat.get("nice_to_have") or []))
        )
        tag_hits = self.db.fetch_tag_hits(ranked_ids, evidence_tags)

        results: List[Dict[str, Any]] = []
        for order, cid in enumerate(ranked_ids, start=1):
            lex = lex_map.get(cid, {})
            verdict = verdict_map.get(cid, {})
            # Use score_map (from all_scores in compact mode, or from verdict in legacy mode)
            llm_score = _clamp01(score_map.get(cid, 0.0))

            must_map = {
                t: bool(tag_hits.get(cid, {}).get(t, False)) for t in (seat.get("must_have") or [])
            }
            nice_map = {
                t: bool(tag_hits.get(cid, {}).get(t, False))
                for t in (seat.get("nice_to_have") or [])
            }

            default_terms = {key: 0.0 for key in LEXICAL_WEIGHTS.keys()}

            results.append(
                {
                    "candidate_id": cid,
                    "score": {"value": llm_score, "order": order},
                    "score_components": {
                        "mode": "llm",
                        "lexical": {
                            "raw": float(lex.get("score_val", 0.0)),
                            "coverage": float(lex.get("coverage", 0.0)),
                            "coverage_denominator": float(lex.get("coverage_denominator", 1.0)),
                            "must_hit_count": int(lex.get("must_hit_count", 0)),
                            "nice_hit_count": int(lex.get("nice_hit_count", 0)),
                            "expertise_hit_count": int(lex.get("expertise_hit_count", 0)),
                            "must_count": int(lex.get("must_count", 0)),
                            "nice_count": int(lex.get("nice_count", 0)),
                            "expertise_count": int(lex.get("expertise_count", 0)),
                            "must_idf_sum": float(lex.get("must_idf_sum", 0.0)),
                            "nice_idf_sum": float(lex.get("nice_idf_sum", 0.0)),
                            "expertise_idf_sum": float(lex.get("expertise_idf_sum", 0.0)),
                            "must_idf_total": float(lex.get("must_idf_total", 0.0)),
                            "nice_idf_total": float(lex.get("nice_idf_total", 0.0)),
                            "expertise_idf_total": float(lex.get("expertise_idf_total", 0.0)),
                            "must_idf_cov": float(lex.get("must_idf_cov", 0.0)),
                            "nice_idf_cov": float(lex.get("nice_idf_cov", 0.0)),
                            "expertise_idf_cov": float(lex.get("expertise_idf_cov", 0.0)),
                            "domain_hit": bool(lex.get("domain_hit", False)),
                            "domain_bonus": float(lex.get("domain_bonus", 0.0)),
                            "fts_rank": float(lex.get("fts_rank", 0.0)),
                            "weights": lex.get("weights", dict(LEXICAL_WEIGHTS)),
                            "terms": lex.get("terms", dict(default_terms)),
                        },
                        "semantic": {
                            "score": 0.0,
                            "raw_score": None,
                            "distance": None,
                            "score_source": None,
                            "clamped_score": 0.0,
                        },
                        "hybrid": {
                            "mode": "llm",
                            "final": llm_score,
                            "lex_raw": float(lex.get("score_val", 0.0)),
                            "sem_score": 0.0,
                            "pool_size": len(pool_ids),
                        },
                        "weights": {
                            "w_lex": 1.0,
                            "w_sem": 0.0,
                        },
                        "llm": {
                            "overall_match_score": llm_score,
                            "lexical_rank": int(lex.get("rank_order", 0)),
                        },
                    },
                    "semantic_evidence": None,
                    "must_have": must_map,
                    "nice_to_have": nice_map,
                    "recency": {"last_updated": lex.get("last_updated")},
                    # Attach verdict in the same shape your UI/CLI already expects
                    # For non-top-k candidates in compact mode, verdict may be empty
                    "llm_justification": {
                        "match_summary": verdict.get("match_summary")
                        or f"Ranked #{order} by LLM with score {llm_score:.0%}.",
                        "strength_analysis": verdict.get("strength_analysis") or [],
                        "gap_analysis": verdict.get("gap_analysis") or [],
                        "overall_match_score": llm_score,
                    },
                }
            )

        # Extract usage from llm_resp and add as top-level key for easier access
        usage = llm_resp.pop("_usage", None)
        debug = {
            "pool_candidate_ids": pool_ids,
            "llm_response": llm_resp,
            "usage": usage,
        }
        return results, debug, len(pool_ids)
