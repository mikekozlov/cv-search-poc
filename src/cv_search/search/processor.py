from __future__ import annotations

import json
import re
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from cv_search.clients.openai_client import OpenAIClient
from cv_search.config.settings import Settings
from cv_search.core.criteria import consolidate_seat_dicts
from cv_search.core.role_classification import is_core_role
from cv_search.db.database import CVDatabase
from cv_search.planner.service import Planner
from cv_search.ranking.llm_verdict import LLMVerdictRanker
from cv_search.retrieval import GatingFilter, LexicalRetriever
from cv_search.search.artifacts import SearchRunArtifactWriter
from cv_search.llm.logger import set_run_dir as llm_set_run_dir
from cv_search.llm.logger import reset_run_dir as llm_reset_run_dir


def default_run_dir(base: str | Path | None = None, *, subdir: str | None = "search") -> str:
    base_dir = Path(base) if base else Path("runs")
    if subdir:
        base_dir = base_dir / subdir
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    run_dir = base_dir / f"{timestamp}__{uuid.uuid4()}"
    run_dir.mkdir(parents=True, exist_ok=True)
    return str(run_dir)


@dataclass(frozen=True)
class RunContext:
    run_id: str
    run_kind: str
    run_dir: str
    started_at: datetime
    user_email: str | None

    def as_dict(self) -> Dict[str, Any]:
        return {
            "run_id": self.run_id,
            "run_kind": self.run_kind,
            "run_dir": self.run_dir,
            "started_at": self.started_at.isoformat(),
            "user_email": self.user_email,
        }


@contextmanager
def _llm_run_dir(run_dir: str | None):
    token = llm_set_run_dir(run_dir) if run_dir else None
    try:
        yield
    finally:
        if token is not None:
            llm_reset_run_dir(token)


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
    ):
        self.db = db
        self.client = client
        self.settings = settings

        self.gating_filter = GatingFilter(db)
        self.lexical_retriever = LexicalRetriever(db)
        self.llm_ranker = LLMVerdictRanker(db, client, settings)
        self.planner = Planner()
        self.artifact_writer = SearchRunArtifactWriter()

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
            "expertise": seat.get("expertise", []),
            "must_have": seat.get("tech_tags", []),
            "nice_to_have": seat.get("nice_to_have", []),
        }

    def _fingerprint(self, seat: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "role": seat["role"],
            "seniority": seat["seniority"],
            "domains": sorted(seat["domains"]),
            "expertise": sorted(seat.get("expertise", [])),
            "must_have": sorted(seat["must_have"]),
            "nice_to_have": sorted(seat["nice_to_have"]),
            "mode": "llm",
        }

    @staticmethod
    def _compute_lex_fanin(
        *,
        top_k: int,
        gate_count: int,
        multiplier: int,
        max_cap: int,
    ) -> int:
        top_k = max(1, int(top_k))
        gate_count = max(0, int(gate_count))
        multiplier = max(1, int(multiplier))
        max_cap = max(1, int(max_cap))

        desired = top_k * multiplier
        cap = max(max_cap, top_k)
        return min(gate_count or top_k, min(cap, desired))

    @staticmethod
    def _extract_uuid_from_run_dir(run_dir: str) -> str | None:
        """Extract UUID from run_dir path if it matches format: timestamp__uuid."""
        folder_name = Path(run_dir).name
        if "__" in folder_name:
            parts = folder_name.split("__")
            if len(parts) >= 2:
                candidate = parts[-1]
                # Validate it looks like a UUID (36 chars with hyphens)
                if len(candidate) == 36 and candidate.count("-") == 4:
                    return candidate
        return None

    def _start_run(
        self, *, run_kind: str, run_dir: str | None, user_email: str | None
    ) -> RunContext:
        started_at = datetime.now(timezone.utc)
        resolved_dir = run_dir or default_run_dir(self.settings.active_runs_dir)
        Path(resolved_dir).mkdir(parents=True, exist_ok=True)

        # Extract UUID from folder name if possible, otherwise generate new one
        run_id = self._extract_uuid_from_run_dir(resolved_dir) or str(uuid.uuid4())

        run_context = RunContext(
            run_id=run_id,
            run_kind=run_kind,
            run_dir=str(resolved_dir),
            started_at=started_at,
            user_email=user_email,
        )
        self.artifact_writer.write_run_metadata(run_context.run_dir, run_context.as_dict())
        return run_context

    def _summarize_seat_criteria(self, criteria: Dict[str, Any]) -> Dict[str, Any]:
        team_size = criteria.get("team_size") or {}
        seat = (team_size.get("members") or [{}])[0] if isinstance(team_size, dict) else {}
        return {
            "role": seat.get("role"),
            "seniority": seat.get("seniority"),
            "domains": seat.get("domains", []),
            "must_have": seat.get("tech_tags", []),
            "nice_to_have": seat.get("nice_to_have", []),
            "project_type": criteria.get("project_type"),
        }

    def _summarize_project_criteria(
        self, base_dict: Dict[str, Any] | None, raw_text: str | None
    ) -> Dict[str, Any]:
        summary: Dict[str, Any] = {"seat_count": 0, "roles": [], "has_raw_text": bool(raw_text)}
        if base_dict:
            team_size = base_dict.get("team_size") or {}
            seats = team_size.get("members") or [] if isinstance(team_size, dict) else []
            summary["seat_count"] = len(seats)
            summary["roles"] = [seat.get("role") for seat in seats if seat.get("role")]
        if raw_text:
            summary["raw_text_preview"] = raw_text[:200]
        return summary

    def _write_db_warning(self, run_dir: str | None, action: str, exc: Exception) -> None:
        if not run_dir:
            return
        warning = {
            "stage": "db",
            "action": action,
            "exception_type": type(exc).__name__,
            "exception_message": str(exc),
            "ts": datetime.now(timezone.utc).isoformat(),
        }
        self.artifact_writer.write_warning(run_dir, warning)

    def _update_run_status(
        self,
        *,
        run_id: str,
        run_dir: str,
        status: str,
        completed_at: datetime | None,
        duration_ms: int | None,
        result_count: int | None,
        error_type: str | None,
        error_message: str | None,
        error_stage: str | None,
        error_traceback: str | None,
    ) -> bool:
        updater = getattr(self.db, "update_search_run_status", None)
        if not callable(updater):
            return False
        try:
            updater(
                run_id=run_id,
                status=status,
                completed_at=completed_at,
                duration_ms=duration_ms,
                result_count=result_count,
                error_type=error_type,
                error_message=error_message,
                error_stage=error_stage,
                error_traceback=error_traceback,
            )
            return True
        except Exception as exc:
            self._write_db_warning(run_dir, "update_search_run_status", exc)
            return False

    def _run_single_seat(
        self,
        criteria: Dict[str, Any],
        top_k: int,
        run_dir: Optional[str] = None,
        llm_pool_size: int | None = None,
    ) -> Dict[str, Any]:
        seat = self._extract_seat(criteria)

        gating_result = self.gating_filter.filter_candidates_with_diagnostics(seat)
        gated_ids = gating_result.candidate_ids
        gating_sql = gating_result.rendered_sql

        if not gated_ids:
            reason = "strict_gate_empty"
            if gating_result.diagnostics:
                reason = gating_result.diagnostics.to_reason()
            return {
                "criteria": criteria,
                "query_fingerprint": self._fingerprint(seat),
                "metrics": {
                    "gate_count": 0,
                    "lex_fanin": 0,
                    "pool_size": 0,
                    "mode": "llm",
                },
                "gating_sql": gating_sql,
                "ranking_sql": None,
                "ranking_explain": [],
                "llm_ranking": None,
                "results": [],
                "reason": reason,
            }

        gate_count = len(gated_ids)
        top_k = min(int(top_k), gate_count)

        # Base lex_fanin on the LLM pool size, not top_k
        pool_mult = max(1, int(self.settings.search_llm_pool_multiplier))
        pool_cap = max(1, int(self.settings.search_llm_pool_max))
        if llm_pool_size is not None:
            effective_pool = max(1, llm_pool_size)
        else:
            effective_pool = min(pool_cap, top_k * pool_mult)
        lex_fanin = self._compute_lex_fanin(
            top_k=effective_pool,
            gate_count=gate_count,
            multiplier=self.settings.search_fanin_multiplier,
            max_cap=self.settings.search_lex_fanin_max,
        )

        lex_rows, ranking_sql = self.lexical_retriever.search(gated_ids, seat, lex_fanin)

        final_results, llm_ranking, pool_size = self.llm_ranker.rank(
            seat=seat,
            lexical_rows=lex_rows,
            top_k=top_k,
            run_dir=run_dir,
            pool_size_override=llm_pool_size,
        )

        metrics = {
            "gate_count": gate_count,
            "lex_fanin": lex_fanin,
            "pool_size": pool_size,
            "mode": "llm",
            "llm_pool_cap": int(self.settings.search_llm_pool_max),
            "llm_pool_multiplier": int(self.settings.search_llm_pool_multiplier),
        }

        return {
            "criteria": criteria,
            "query_fingerprint": self._fingerprint(seat),
            "metrics": metrics,
            "llm_ranking": llm_ranking,
            "results": final_results,
            "gating_sql": gating_sql,
            "ranking_sql": ranking_sql,
            "ranking_explain": [],
        }

    def _record_run(
        self,
        *,
        run_id: str,
        run_kind: str,
        run_dir: str | None,
        user_email: str | None,
        criteria: Dict[str, Any],
        raw_text: str | None,
        top_k: int,
        seat_count: int,
        note: str | None,
    ) -> bool:
        recorder = getattr(self.db, "create_search_run", None)
        if not callable(recorder):
            return False
        try:
            criteria_json = json.dumps(criteria, ensure_ascii=False)
            recorder(
                run_id=run_id,
                run_kind=run_kind,
                run_dir=run_dir,
                user_email=user_email,
                criteria_json=criteria_json,
                raw_text=raw_text,
                top_k=top_k,
                seat_count=seat_count,
                note=note,
                status="running",
            )
        except Exception as exc:
            self._write_db_warning(run_dir, "create_search_run", exc)
            return False
        return True

    def search_for_seat(
        self,
        criteria: Dict[str, Any],
        top_k: int = 10,
        run_dir: str | None = None,
        run_kind: str = "single_seat_search",
        record_run: bool = True,
        raise_on_error: bool = False,
        user_email: str | None = None,
        llm_pool_size: int | None = None,
        # Deprecated params kept for API compat - ignored
        mode_override: str | None = None,
        vs_topk_override: int | None = None,
    ) -> Dict[str, Any]:
        run_context = self._start_run(run_kind=run_kind, run_dir=run_dir, user_email=user_email)
        run_dir = run_context.run_dir
        db_recorded = False
        with _llm_run_dir(run_dir):
            try:
                if record_run:
                    db_recorded = self._record_run(
                        run_id=run_context.run_id,
                        run_kind=run_kind,
                        run_dir=run_dir,
                        user_email=user_email,
                        criteria=criteria,
                        raw_text=None,
                        top_k=top_k,
                        seat_count=1,
                        note=None,
                    )
                payload = self._run_single_seat(
                    criteria=criteria,
                    top_k=top_k,
                    run_dir=run_dir,
                    llm_pool_size=llm_pool_size,
                )
                payload["run_id"] = run_context.run_id
                payload["run_dir"] = run_dir
                payload["status"] = "ok"

                # Add duration_ms to metrics
                completed_at = datetime.now(timezone.utc)
                duration_ms = int((completed_at - run_context.started_at).total_seconds() * 1000)
                if "metrics" in payload:
                    payload["metrics"]["duration_ms"] = duration_ms

                self.artifact_writer.write(run_dir, payload)
                if db_recorded:
                    result_count = len(payload.get("results", []))
                    self._update_run_status(
                        run_id=run_context.run_id,
                        run_dir=run_dir,
                        status="succeeded",
                        completed_at=completed_at,
                        duration_ms=duration_ms,
                        result_count=result_count,
                        error_type=None,
                        error_message=None,
                        error_stage=None,
                        error_traceback=None,
                    )
                return payload
            except Exception as exc:
                error_extra = {
                    "criteria_summary": self._summarize_seat_criteria(criteria),
                    "top_k": top_k,
                    "mode": "llm",
                }
                error_info = self.artifact_writer.write_error(
                    run_dir, exc, stage="search", extra=error_extra
                )
                error_payload = error_info["error"]
                error_traceback = error_info["traceback"]
                if db_recorded:
                    completed_at = datetime.now(timezone.utc)
                    duration_ms = int(
                        (completed_at - run_context.started_at).total_seconds() * 1000
                    )
                    self._update_run_status(
                        run_id=run_context.run_id,
                        run_dir=run_dir,
                        status="failed",
                        completed_at=completed_at,
                        duration_ms=duration_ms,
                        result_count=0,
                        error_type=error_payload.get("exception_type"),
                        error_message=error_payload.get("message"),
                        error_stage=error_payload.get("stage"),
                        error_traceback=error_traceback[:4000],
                    )
                failure_payload = {
                    "status": "failed",
                    "error": error_payload,
                    "run_id": run_context.run_id,
                    "run_dir": run_dir,
                    "criteria": criteria,
                    "results": [],
                    "metrics": {},
                }
                if raise_on_error:
                    raise
                return failure_payload

    def search_for_project(
        self,
        criteria: Any,
        top_k: int = 3,
        run_dir: Optional[str] = None,
        raw_text: Optional[str] = None,
        run_kind: str = "project_search",
        raise_on_error: bool = False,
        user_email: str | None = None,
        llm_pool_size: int | None = None,
        # Deprecated params kept for API compat - ignored
        mode_override: Optional[str] = None,
    ) -> Dict[str, Any]:
        run_context = self._start_run(run_kind=run_kind, run_dir=run_dir, user_email=user_email)
        run_dir = run_context.run_dir
        base_dict: Dict[str, Any] | None = None
        aggregated: List[Dict[str, Any]] = []
        gaps: List[int] = []
        db_recorded = False
        with _llm_run_dir(run_dir):
            try:
                crit_with_seats = self.planner.derive_project_seats(criteria, raw_text=raw_text)
                base_dict = self.planner._criteria_dict(crit_with_seats)

                all_seats = (base_dict.get("team_size") or {}).get("members") or []
                # Consolidate duplicate roles into single entries
                all_seats = consolidate_seat_dicts(all_seats)
                # Separate core roles (to be searched) from SME roles (recommendations only)
                core_seats = [s for s in all_seats if is_core_role(s.get("role", ""))]
                sme_seats = [s for s in all_seats if not is_core_role(s.get("role", ""))]
                sme_roles = [
                    {"role": s.get("role"), "seniority": s.get("seniority")} for s in sme_seats
                ]
                seats = core_seats  # Only search core seats
                if raw_text and self._is_generic_low_signal(raw_text, base_dict, all_seats):
                    note = (
                        "This brief is too broad to search reliably. "
                        "Please specify the role(s) you need and, if possible, seniority, domain, or tech stack."
                    )
                    db_recorded = self._record_run(
                        run_id=run_context.run_id,
                        run_kind=run_kind,
                        run_dir=run_dir,
                        user_email=user_email,
                        criteria=base_dict,
                        raw_text=raw_text,
                        top_k=top_k,
                        seat_count=len(seats),
                        note=note,
                    )
                    if db_recorded:
                        completed_at = datetime.now(timezone.utc)
                        duration_ms = int(
                            (completed_at - run_context.started_at).total_seconds() * 1000
                        )
                        self._update_run_status(
                            run_id=run_context.run_id,
                            run_dir=run_dir,
                            status="succeeded",
                            completed_at=completed_at,
                            duration_ms=duration_ms,
                            result_count=0,
                            error_type=None,
                            error_message=None,
                            error_stage=None,
                            error_traceback=None,
                        )
                    return {
                        "project_criteria": base_dict,
                        "seats": [],
                        "gaps": [],
                        "sme_roles": sme_roles,
                        "run_dir": run_dir,
                        "run_id": run_context.run_id,
                        "note": note,
                        "reason": "low_signal_brief",
                        "status": "skipped",
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
                    db_recorded = self._record_run(
                        run_id=run_context.run_id,
                        run_kind=run_kind,
                        run_dir=run_dir,
                        user_email=user_email,
                        criteria=base_dict,
                        raw_text=raw_text,
                        top_k=top_k,
                        seat_count=0,
                        note=note,
                    )
                    if db_recorded:
                        completed_at = datetime.now(timezone.utc)
                        duration_ms = int(
                            (completed_at - run_context.started_at).total_seconds() * 1000
                        )
                        self._update_run_status(
                            run_id=run_context.run_id,
                            run_dir=run_dir,
                            status="succeeded",
                            completed_at=completed_at,
                            duration_ms=duration_ms,
                            result_count=0,
                            error_type=None,
                            error_message=None,
                            error_stage=None,
                            error_traceback=None,
                        )
                    return {
                        "project_criteria": base_dict,
                        "seats": [],
                        "gaps": [],
                        "sme_roles": sme_roles,
                        "run_dir": run_dir,
                        "run_id": run_context.run_id,
                        "note": note,
                        "reason": reason,
                        "status": "skipped",
                    }

                out_dir = run_dir
                Path(out_dir).mkdir(parents=True, exist_ok=True)
                (Path(out_dir) / "criteria.json").write_text(
                    json.dumps(base_dict, indent=2, ensure_ascii=False),
                    encoding="utf-8",
                )
                db_note = "Stateless multi-seat search; per-seat artifacts live under run_dir."
                db_recorded = self._record_run(
                    run_id=run_context.run_id,
                    run_kind=run_kind,
                    run_dir=out_dir,
                    user_email=user_email,
                    criteria=base_dict,
                    raw_text=raw_text,
                    top_k=top_k,
                    seat_count=len(seats),
                    note=db_note,
                )

                def _search_single_seat(idx_seat_tuple):
                    idx, seat = idx_seat_tuple
                    seat_dir = Path(out_dir) / f"seat_{idx:02d}_{seat['role']}"
                    single_criteria = self.planner._pack_single_seat_criteria(base_dict, seat)
                    payload = self.search_for_seat(
                        criteria=single_criteria,
                        top_k=top_k,
                        run_dir=str(seat_dir),
                        record_run=False,
                        raise_on_error=raise_on_error,
                        user_email=user_email,
                        llm_pool_size=llm_pool_size,
                    )
                    seat_entry = {
                        "index": idx,
                        "role": seat["role"],
                        "seniority": seat.get("seniority"),
                        "criteria": single_criteria,
                        "metrics": payload.get("metrics", {}),
                        "results": payload.get("results", []),
                    }
                    if payload.get("status") == "failed":
                        seat_entry["error"] = payload.get("error")
                    return idx, seat_entry, bool(payload.get("results"))

                # Execute seat searches in parallel
                max_workers = min(len(seats), 5)  # Cap at 5 concurrent searches
                with ThreadPoolExecutor(max_workers=max_workers) as executor:
                    futures = {
                        executor.submit(_search_single_seat, (idx, seat)): idx
                        for idx, seat in enumerate(seats, start=1)
                    }
                    results_map = {}
                    for future in as_completed(futures):
                        idx, seat_entry, has_results = future.result()
                        results_map[idx] = seat_entry
                        if not has_results:
                            gaps.append(idx)

                # Reassemble in original order
                for idx in sorted(results_map.keys()):
                    aggregated.append(results_map[idx])

                if db_recorded:
                    completed_at = datetime.now(timezone.utc)
                    duration_ms = int(
                        (completed_at - run_context.started_at).total_seconds() * 1000
                    )
                    result_count = sum(
                        len(seat_entry.get("results", [])) for seat_entry in aggregated
                    )
                    self._update_run_status(
                        run_id=run_context.run_id,
                        run_dir=out_dir,
                        status="succeeded",
                        completed_at=completed_at,
                        duration_ms=duration_ms,
                        result_count=result_count,
                        error_type=None,
                        error_message=None,
                        error_stage=None,
                        error_traceback=None,
                    )
                return {
                    "project_criteria": base_dict,
                    "seats": aggregated,
                    "gaps": gaps,
                    "sme_roles": sme_roles,
                    "run_dir": out_dir,
                    "run_id": run_context.run_id,
                    "note": None,
                    "status": "ok",
                }
            except Exception as exc:
                error_extra = {
                    "criteria_summary": self._summarize_project_criteria(base_dict, raw_text),
                    "top_k": top_k,
                }
                error_info = self.artifact_writer.write_error(
                    run_dir, exc, stage="search", extra=error_extra
                )
                error_payload = error_info["error"]
                error_traceback = error_info["traceback"]
                if not db_recorded:
                    seat_count = 0
                    if base_dict:
                        team_size = base_dict.get("team_size") or {}
                        if isinstance(team_size, dict):
                            seat_count = len(team_size.get("members") or [])
                    db_recorded = self._record_run(
                        run_id=run_context.run_id,
                        run_kind=run_kind,
                        run_dir=run_dir,
                        user_email=user_email,
                        criteria=base_dict or {},
                        raw_text=raw_text,
                        top_k=top_k,
                        seat_count=seat_count,
                        note=None,
                    )
                if db_recorded:
                    completed_at = datetime.now(timezone.utc)
                    duration_ms = int(
                        (completed_at - run_context.started_at).total_seconds() * 1000
                    )
                    self._update_run_status(
                        run_id=run_context.run_id,
                        run_dir=run_dir,
                        status="failed",
                        completed_at=completed_at,
                        duration_ms=duration_ms,
                        result_count=0,
                        error_type=error_payload.get("exception_type"),
                        error_message=error_payload.get("message"),
                        error_stage=error_payload.get("stage"),
                        error_traceback=error_traceback[:4000],
                    )
                failure_payload = {
                    "status": "failed",
                    "error": error_payload,
                    "run_id": run_context.run_id,
                    "run_dir": run_dir,
                    "project_criteria": base_dict,
                    "seats": aggregated,
                    "gaps": gaps,
                }
                if raise_on_error:
                    raise
                return failure_payload
