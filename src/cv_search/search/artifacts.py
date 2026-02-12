from __future__ import annotations

import json
import traceback
from pathlib import Path
from typing import Any, Dict, List


class SearchRunArtifactWriter:
    """Persist search diagnostics and results for later inspection."""

    def write(self, run_dir: str | Path, payload: Dict[str, Any]) -> None:
        target = Path(run_dir)
        target.mkdir(parents=True, exist_ok=True)

        def _write_text(name: str, content: str) -> None:
            (target / name).write_text(content, encoding="utf-8")

        def _write_json(name: str, content: Any) -> None:
            (target / name).write_text(
                json.dumps(content, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )

        criteria = payload.get("criteria")
        if criteria is not None:
            _write_json("criteria.json", criteria)

        gating_sql = (payload.get("gating_sql") or "").strip()
        _write_text("gating.sql.txt", f"{gating_sql}\n")

        ranking_sql = payload.get("ranking_sql")
        if ranking_sql:
            _write_text("ranking.sql.txt", f"{ranking_sql.strip()}\n")

        vs_query = payload.get("vs_query")
        if vs_query:
            _write_text("vs.query.txt", vs_query.strip() + "\n")

        vs_sql = payload.get("vs_sql")
        if vs_sql:
            _write_text("vs.sql.txt", vs_sql.strip() + "\n")

        vs_results = payload.get("vs_results")
        if vs_results:
            _write_json("vs.results.json", vs_results)

        fusion = payload.get("fusion")
        if fusion:
            _write_json("ranking.fusion.json", fusion)

        llm_ranking = payload.get("llm_ranking")
        if llm_ranking:
            _write_json("llm.ranking.json", llm_ranking)

        _write_json("metrics.json", payload.get("metrics", {}))
        _write_json("results.json", payload.get("results", []))

    def write_run_metadata(self, run_dir: str | Path, metadata: Dict[str, Any]) -> None:
        target = Path(run_dir)
        target.mkdir(parents=True, exist_ok=True)
        (target / "run.json").write_text(
            json.dumps(metadata, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def write_warning(self, run_dir: str | Path, warning: Dict[str, Any]) -> None:
        target = Path(run_dir)
        target.mkdir(parents=True, exist_ok=True)
        warnings_path = target / "warnings.json"
        warnings: List[Dict[str, Any]] = []
        if warnings_path.exists():
            try:
                existing = json.loads(warnings_path.read_text(encoding="utf-8"))
                if isinstance(existing, list):
                    warnings = existing
            except Exception:
                warnings = []
        warnings.append(warning)
        warnings_path.write_text(
            json.dumps(warnings, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def write_error(
        self,
        run_dir: str | Path,
        exc: Exception,
        stage: str,
        extra: Dict[str, Any] | None = None,
    ) -> Dict[str, Any]:
        target = Path(run_dir) / "errors"
        target.mkdir(parents=True, exist_ok=True)

        cause_chain: List[Dict[str, Any]] = []
        seen: set[int] = set()
        current = exc.__cause__ or exc.__context__
        while current and id(current) not in seen:
            seen.add(id(current))
            cause_chain.append(
                {
                    "exception_type": type(current).__name__,
                    "message": str(current),
                }
            )
            current = current.__cause__ or current.__context__

        remediation_hint = None
        if extra and isinstance(extra, dict):
            remediation_hint = extra.get("remediation_hint")
        if not remediation_hint:
            remediation_hint = "Check configuration and review errors/traceback.txt for details."

        error_payload = {
            "stage": stage,
            "exception_type": type(exc).__name__,
            "message": str(exc),
            "remediation_hint": remediation_hint,
            "extra": extra or None,
        }
        if cause_chain:
            error_payload["cause_chain"] = cause_chain

        (target / "error.json").write_text(
            json.dumps(error_payload, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        traceback_text = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
        (target / "traceback.txt").write_text(
            traceback_text,
            encoding="utf-8",
        )
        return {"error": error_payload, "traceback": traceback_text}
