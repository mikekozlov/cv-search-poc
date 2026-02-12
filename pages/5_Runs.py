import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st

APP_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = APP_ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

try:
    from cv_search.app.streamlit_theme import inject_streamlit_theme, render_page_header
    from cv_search.app.streamlit_results import format_timestamp
    from cv_search.auth_guard import require_login
    from cv_search.config.settings import Settings
    from cv_search.db.database import CVDatabase
    from cv_search.utils.archive import zip_directory
except ImportError as e:
    st.error(
        f"""
    **Failed to import project modules.**

    Ensure `app.py` is running from the project root and the `src` directory is correct.
    **Error:** {e}
    """
    )
    st.stop()


st.set_page_config(page_title="Runs", page_icon="CV", layout="wide")
require_login()
inject_streamlit_theme()

render_page_header(
    "Run Inspector",
    "Browse recent runs, inspect artifacts, and download bundles.",
)
st.divider()


def _format_timestamp(value: Any) -> str:
    return format_timestamp(value, empty_label="", utc=True)


def _safe_load_json(path: Path) -> Any | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _safe_read_text(path: Path) -> str | None:
    if not path.exists():
        return None
    try:
        return path.read_text(encoding="utf-8")
    except Exception:
        return None


def _load_runs_from_db(
    settings: Settings, status: str | None, kind: str | None, limit: int
) -> tuple[list[dict[str, Any]], str | None]:
    db = None
    try:
        db = CVDatabase(settings)
        rows = db.list_search_runs(limit=limit, status=status, kind=kind)
        return rows, None
    except Exception as exc:
        return [], str(exc)
    finally:
        if db:
            db.close()


def _scan_runs_on_disk(base_dir: Path, limit: int) -> list[dict[str, Any]]:
    if not base_dir.exists():
        return []

    run_dirs: dict[Path, float] = {}
    for run_json in base_dir.rglob("run.json"):
        run_dirs[run_json.parent] = run_json.stat().st_mtime

    if not run_dirs:
        for criteria_file in base_dir.rglob("criteria.json"):
            run_dirs.setdefault(criteria_file.parent, criteria_file.stat().st_mtime)

    if not run_dirs:
        return []

    ordered_dirs = sorted(run_dirs.items(), key=lambda item: item[1], reverse=True)[:limit]
    entries: list[dict[str, Any]] = []
    for run_dir, mtime in ordered_dirs:
        run_meta = _safe_load_json(run_dir / "run.json") or {}
        created_at = run_meta.get("started_at")
        if not created_at:
            created_at = datetime.fromtimestamp(mtime, tz=timezone.utc).isoformat(
                timespec="seconds"
            )

        error_data = _safe_load_json(run_dir / "errors" / "error.json")
        error_message = None
        status = "unknown"
        if isinstance(error_data, dict):
            error_message = error_data.get("message")
            status = "failed"

        result_count = None
        results_data = _safe_load_json(run_dir / "results.json")
        if isinstance(results_data, list):
            result_count = len(results_data)
            if status == "unknown":
                status = "succeeded"

        entries.append(
            {
                "run_id": run_meta.get("run_id") or run_dir.name,
                "run_kind": run_meta.get("run_kind") or run_dir.parent.name,
                "run_dir": str(run_dir),
                "user_email": run_meta.get("user_email"),
                "created_at": created_at,
                "status": status,
                "result_count": result_count,
                "error_message": error_message,
                "_mtime": mtime,
            }
        )
    return entries


def _apply_filters(
    runs: list[dict[str, Any]], status_filter: str, kind_filter: str
) -> list[dict[str, Any]]:
    filtered = runs
    if status_filter != "all":
        filtered = [run for run in filtered if (run.get("status") or "unknown") == status_filter]
    if kind_filter != "all":
        filtered = [run for run in filtered if (run.get("run_kind") or "") == kind_filter]
    return filtered


def _render_json_section(label: str, path: Path, expanded: bool = False) -> None:
    data = _safe_load_json(path)
    if data is None:
        return
    with st.expander(label, expanded=expanded):
        st.json(data)


def _render_error_section(run_dir: Path) -> None:
    error_data = _safe_load_json(run_dir / "errors" / "error.json")
    if not isinstance(error_data, dict):
        return

    exception_type = error_data.get("exception_type") or "Exception"
    message = error_data.get("message") or "Unknown error"
    stage = error_data.get("stage") or "unknown"
    remediation = error_data.get("remediation_hint") or "Review traceback for details."

    st.subheader("Error summary")
    st.error(f"{exception_type}: {message}")
    st.caption(f"Stage: {stage}")
    st.caption(f"Remediation: {remediation}")

    extra = error_data.get("extra")
    if extra:
        st.json(extra)

    traceback_text = _safe_read_text(run_dir / "errors" / "traceback.txt")
    if traceback_text:
        with st.expander("Traceback"):
            st.code(traceback_text, language="text")


def _render_llm_prompts(run_dir: Path) -> None:
    prompts_text = _safe_read_text(run_dir / "llm.prompts.md")
    if not prompts_text:
        return
    with st.expander("LLM prompts"):
        st.code(prompts_text, language="markdown")


settings = Settings()

st.subheader("Filters")
filter_cols = st.columns([1, 1, 1])
status_filter = filter_cols[0].selectbox(
    "Status",
    options=["all", "running", "succeeded", "failed"],
    index=0,
)
kind_filter = filter_cols[1].selectbox(
    "Kind",
    options=["all", "single_seat_search", "project_search", "presale_search"],
    index=0,
)
limit = filter_cols[2].selectbox(
    "Max runs",
    options=[25, 50, 100, 200],
    index=2,
)

db_status = None
runs, db_error = _load_runs_from_db(
    settings,
    status_filter if status_filter != "all" else None,
    kind_filter if kind_filter != "all" else None,
    limit,
)
source = "database"
if not db_error:
    runs = _apply_filters(runs, status_filter, kind_filter)
if db_error or not runs:
    base_runs_dir = Path(settings.active_runs_dir)
    fallback_runs = _scan_runs_on_disk(base_runs_dir, limit)
    runs = _apply_filters(fallback_runs, status_filter, kind_filter)
    source = "filesystem"
    if db_error:
        db_status = f"Database unavailable, using filesystem fallback: {db_error}"
    else:
        db_status = "Database returned no rows, using filesystem fallback."

display_runs = [
    {
        "created_at": _format_timestamp(run.get("created_at")),
        "kind": run.get("run_kind") or "",
        "status": run.get("status") or "unknown",
        "run_id": run.get("run_id") or "",
        "user_email": run.get("user_email") or "",
        "run_dir": run.get("run_dir") or "",
        "result_count": run.get("result_count"),
        "error_message": run.get("error_message") or "",
    }
    for run in runs
]

st.subheader("Recent runs")
if db_status:
    st.warning(db_status)
st.caption(f"Source: {source}")
if display_runs:
    run_df = pd.DataFrame(display_runs)
    selection = st.dataframe(
        run_df,
        use_container_width=True,
        on_select="rerun",
        selection_mode="single-row",
    )
else:
    st.info("No runs found.")

if not runs:
    st.stop()

selected_rows: list[int] = []
if display_runs:
    if hasattr(selection, "selection"):
        selected_rows = list(getattr(selection.selection, "rows", []) or [])
    elif isinstance(selection, dict):
        selected_rows = list(selection.get("selection", {}).get("rows", []) or [])

selected_idx = selected_rows[0] if selected_rows else 0
selected_run = runs[selected_idx]
selected_run_dir = selected_run.get("run_dir")
selected_run_id = selected_run.get("run_id")

st.subheader("Run details")
st.caption(f"Run ID: {selected_run_id or 'unknown'}")
st.caption(f"Run dir: {selected_run_dir or 'unknown'}")
st.caption(f"User email: {selected_run.get('user_email') or 'unknown'}")

if not selected_run_dir:
    st.warning("Run directory is missing; artifacts cannot be loaded.")
    st.stop()

run_path = Path(selected_run_dir)
if not run_path.exists():
    st.warning("Run directory does not exist on disk.")
    st.stop()

zip_name = f"{run_path.parent.name}_{run_path.name}.zip"
try:
    zip_bytes = zip_directory(run_path)
    st.download_button(
        "Download artifacts (.zip)",
        data=zip_bytes,
        file_name=zip_name,
        mime="application/zip",
    )
except Exception as exc:
    st.error(f"Failed to create zip: {exc}")

_render_json_section("run.json", run_path / "run.json", expanded=True)
_render_json_section("criteria.json", run_path / "criteria.json")
_render_json_section("metrics.json", run_path / "metrics.json")
_render_json_section("results.json", run_path / "results.json")

_render_error_section(run_path)
_render_llm_prompts(run_path)
