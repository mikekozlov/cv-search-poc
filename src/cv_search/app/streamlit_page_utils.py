"""
Shared utilities for Streamlit search pages.
Consolidated from duplicated code in Project Search and Single Seat Search pages.
"""

from __future__ import annotations

from pathlib import Path

import streamlit as st

from cv_search.app.bootstrap import load_stateless_services as bootstrap_stateless_services
from cv_search.app.streamlit_results import (
    format_timestamp,
    render_experience_cards,
    render_justification_block,
    render_score_breakdown,
    render_summary_card,
    render_tag_chips,
)
from cv_search.config.settings import Settings
from cv_search.core.cv_markdown import build_cv_markdown  # noqa: F811
from cv_search.db.database import CVDatabase
from cv_search.ingestion.cv_parser import CVParser


# ============================================================================
# Service Loading
# ============================================================================


@st.cache_resource
def load_stateless_services() -> dict[str, object]:
    """Load stateless services (cached at Streamlit resource level)."""
    return bootstrap_stateless_services()


def ensure_services_loaded() -> None:
    """Ensure services are loaded into session state. Call early in each page."""
    if "services_loaded" not in st.session_state:
        services = load_stateless_services()
        st.session_state.update(services)
        st.session_state["services_loaded"] = True


# ============================================================================
# Feedback UI Components
# ============================================================================


def set_feedback_sentiment(sentiment: str, key: str) -> None:
    """Callback for feedback sentiment buttons."""
    st.session_state[key] = sentiment


def render_run_feedback(run_id: str, settings: Settings, scope: str) -> None:
    """Render thumbs up/down feedback UI for a search run."""
    st.subheader("Run feedback")
    st.caption(f"Run ID: {run_id}")
    sentiment_key = f"{scope}_feedback_sentiment_{run_id}"
    comment_key = f"{scope}_feedback_comment_{run_id}"
    status_key = f"{scope}_feedback_status_{run_id}"

    cols = st.columns([1, 1, 6])
    cols[0].button(
        "👍",
        key=f"{sentiment_key}_like",
        on_click=set_feedback_sentiment,
        args=("like", sentiment_key),
    )
    cols[1].button(
        "👎",
        key=f"{sentiment_key}_dislike",
        on_click=set_feedback_sentiment,
        args=("dislike", sentiment_key),
    )

    sentiment = st.session_state.get(sentiment_key)
    if sentiment:
        label = "Like" if sentiment == "like" else "Dislike"
        st.caption(f"Selected: {label}")

    comment = st.text_area(
        "Comments",
        key=comment_key,
        height=120,
        placeholder="Share what worked well or what should improve.",
    )

    if st.button("Submit feedback", key=f"{scope}_feedback_submit_{run_id}"):
        if not sentiment:
            st.warning("Select Like or Dislike before submitting feedback.")
        else:
            db = None
            try:
                db = CVDatabase(settings)
                db.update_search_run_feedback(
                    run_id=run_id,
                    sentiment=sentiment,
                    comment=(comment or "").strip() or None,
                )
                st.session_state[status_key] = "saved"
            except Exception as e:
                st.error(f"Failed to save feedback: {e}")
            finally:
                if db:
                    db.close()

    if st.session_state.get(status_key) == "saved":
        st.success("Feedback saved.")


# ============================================================================
# Text Utilities
# ============================================================================


def format_tag_chips(tags: list[str]) -> str:
    """Format tags as inline code chips."""
    if not tags:
        return "-"
    return " ".join(f"`{tag}`" for tag in tags)


def split_csv(value: str | None) -> list[str]:
    """Split comma-separated string into list."""
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


def split_lines(value: str | None) -> list[str]:
    """Split newline-separated string into list."""
    if not value:
        return []
    return [line.strip() for line in value.splitlines() if line.strip()]


# build_cv_markdown is now imported from cv_search.core.cv_markdown


# ============================================================================
# Source File Handling
# ============================================================================


@st.cache_data(show_spinner=False)
def extract_source_text(path_str: str, mtime: float | None) -> str:
    """Extract text from source file (PPTX or text)."""
    path = Path(path_str)
    if path.suffix.lower() == ".pptx":
        return CVParser().extract_text(path)
    return path.read_text(encoding="utf-8", errors="replace")


def load_source_text(path: Path | None) -> tuple[str | None, str | None]:
    """Load source text with error handling. Returns (text, error_message)."""
    if path is None:
        return None, "Source path is not available."
    if not path.exists():
        return None, f"Source file not found: {path}"
    try:
        mtime = path.stat().st_mtime
    except OSError as exc:
        return None, f"Unable to read file metadata: {exc}"
    try:
        text = extract_source_text(str(path), mtime)
    except Exception as exc:
        return None, f"Failed to extract text: {exc}"
    return text, None


def resolve_source_info(
    settings: Settings, profile: dict[str, object] | None
) -> tuple[str | None, str | None, Path | None]:
    """Resolve source file info from candidate profile."""
    source_filename = profile.get("source_filename") if profile else None
    source_gdrive_path = profile.get("source_gdrive_path") if profile else None
    local_path = None
    if source_gdrive_path:
        local_path = settings.gdrive_local_dest_dir / str(source_gdrive_path)
    elif source_filename:
        local_path = settings.gdrive_local_dest_dir / str(source_filename)
    return source_filename, source_gdrive_path, local_path


# ============================================================================
# Candidate Rendering
# ============================================================================


def render_candidate_context(context: dict[str, object]) -> None:
    """Render summary, experience, and tags sections for a candidate."""
    st.markdown("##### Summary")
    render_summary_card(context.get("summary_text", ""))

    st.markdown("##### Experience")
    render_experience_cards(context.get("experience_text", ""))

    st.markdown("##### Tags")
    render_tag_chips(context.get("tags_text", ""))


def render_candidate_result(
    result: dict[str, object],
    db: CVDatabase,
    settings: Settings,
    key_prefix: str,
    score_label: str = "Score",
) -> None:
    """Render a single candidate result with expander, tabs, and details."""
    candidate_id = result["candidate_id"]
    score = result["score"]["value"]
    profile = db.get_candidate_profile(candidate_id)
    context = db.get_full_candidate_context(candidate_id)
    experiences = db.get_candidate_experiences(candidate_id)
    qualifications = db.get_candidate_qualifications(candidate_id)
    tags = db.get_candidate_tags(candidate_id)

    display_name = (profile or {}).get("name")
    label = f"{display_name} ({candidate_id})" if display_name else candidate_id

    with st.expander(f"**{label}** ({score_label}: {score:.3f})"):
        justification = result.get("llm_justification")
        if justification:
            render_justification_block(justification)
        else:
            st.info("Justification was not run for this candidate.")

        render_score_breakdown(result)

        tabs = st.tabs(["Summary & Evidence", "Full CV (.md)"])

        with tabs[0]:
            meta_cols = st.columns(4)
            meta_cols[0].markdown("**Name**")
            meta_cols[0].write((profile or {}).get("name") or "-")
            meta_cols[1].markdown("**Location**")
            meta_cols[1].write((profile or {}).get("location") or "-")
            meta_cols[2].markdown("**Seniority**")
            meta_cols[2].write((profile or {}).get("seniority") or "-")
            meta_cols[3].markdown("**Last Updated**")
            last_updated = format_timestamp((profile or {}).get("last_updated"), empty_label="-")
            meta_cols[3].write(last_updated)

            tag_cols = st.columns(2)
            with tag_cols[0]:
                st.markdown("**Roles**")
                st.markdown(format_tag_chips(tags.get("role", [])))
                st.markdown("**Domains**")
                st.markdown(format_tag_chips(tags.get("domain", [])))
            with tag_cols[1]:
                st.markdown("**Expertise**")
                st.markdown(format_tag_chips(tags.get("expertise", [])))
                st.markdown("**Tech**")
                st.markdown(format_tag_chips(tags.get("tech", [])))

            if context:
                render_candidate_context(context)
            else:
                st.error(f"Could not retrieve context for {candidate_id}.")

        with tabs[1]:
            source_filename, source_gdrive_path, local_path = resolve_source_info(settings, profile)
            raw_text = None
            markdown = build_cv_markdown(
                candidate_id=candidate_id,
                profile=profile,
                context=context,
                experiences=experiences,
                qualifications=qualifications,
                tags=tags,
                raw_text=raw_text,
            )
            st.download_button(
                "Download CV (.md)",
                data=markdown,
                file_name=f"{candidate_id}.md",
                mime="text/markdown",
                key=f"{key_prefix}_cv_md_{candidate_id}",
            )
            if not source_filename and not source_gdrive_path:
                st.caption("Source file metadata is not available for this candidate.")
            st.code(markdown, language="markdown")

        with st.expander("Show Full Result JSON"):
            st.json(result)


# ============================================================================
# Preset Utilities
# ============================================================================


def apply_text_preset(key: str, value: str) -> None:
    """Callback to apply a text preset to session state."""
    st.session_state[key] = value


# ============================================================================
# Role Chips (for Presale)
# ============================================================================


def render_role_chips(label: str, roles: list[str]) -> None:
    """Render a labeled list of role chips."""
    st.markdown(f"**{label}**")
    if not roles:
        st.write("-")
        return
    st.markdown(" ".join(f"`{r}`" for r in roles))
