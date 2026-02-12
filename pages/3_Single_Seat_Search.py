import streamlit as st
import sys
from pathlib import Path
from typing import List

APP_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = APP_ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

try:
    from cv_search.app.streamlit_page_utils import (
        ensure_services_loaded,
        format_tag_chips,
        render_candidate_result,
        render_run_feedback,
    )
    from cv_search.app.streamlit_results import inject_candidate_result_styles
    from cv_search.app.streamlit_theme import inject_streamlit_theme, inject_searching_button_style, render_page_header
    from cv_search.auth_guard import require_login
    from cv_search.clients.openai_client import OpenAIClient
    from cv_search.config.settings import Settings
    from cv_search.db.database import CVDatabase
    from cv_search.search import SearchProcessor, default_run_dir
    from cv_search.utils.archive import zip_directory
except ImportError as e:
    st.error(f"""
    **Failed to import project modules.**

    Ensure `app.py` is running from the project root and the `src` directory is correct.
    **Error:** {e}
    """)
    st.stop()


st.set_page_config(page_title="Single Seat Search", page_icon="CV", layout="wide")
identity = require_login()
user_email = identity.email
inject_streamlit_theme()
inject_searching_button_style()
inject_candidate_result_styles()

render_page_header(
    "Single Seat Search",
    "Build a focused seat query and review ranked candidates.",
)
st.divider()

SINGLE_SEAT_PRESETS = [
    {
        "label": "Fintech backend (Python/FastAPI)",
        "role": "backend_engineer",
        "seniority": "senior",
        "must_have": ["python", "fastapi", "postgresql"],
        "nice_to_have": ["aws", "docker"],
        "domains": ["fintech"],
    },
    {
        "label": "SaaS frontend (React/TypeScript)",
        "role": "frontend_engineer",
        "seniority": "middle",
        "must_have": ["react", "typescript"],
        "nice_to_have": ["nextjs", "tailwindcss"],
        "domains": ["saas_b2b"],
    },
]


def _apply_single_seat_preset(preset: dict[str, object]) -> None:
    st.session_state["single_seat_role"] = preset["role"]
    st.session_state["single_seat_seniority"] = preset["seniority"]
    st.session_state["single_seat_must_have"] = preset["must_have"]
    st.session_state["single_seat_nice_to_have"] = preset["nice_to_have"]
    st.session_state["single_seat_domains"] = preset["domains"]


ensure_services_loaded()

try:
    settings: Settings = st.session_state.settings
    client: OpenAIClient = st.session_state.client

    # Load the new list-based lexicons
    role_lex_list: List[str] = st.session_state.role_lex
    tech_lex_list: List[str] = st.session_state.tech_lex
    domain_lex_list: List[str] = st.session_state.domain_lex
except KeyError as e:
    st.error(f"Failed to load service or lexicon: {e}. Please return to the Home page and reload.")
    st.stop()

# Initialize session state defaults (avoids conflict with preset callbacks)
if "single_seat_seniority" not in st.session_state:
    st.session_state["single_seat_seniority"] = "senior"

layout_cols = st.columns([1.15, 1.45], gap="large")
with layout_cols[0]:
    st.markdown("#### Seat definition")

    # Quick presets at the top
    st.caption("Quick presets")
    preset_cols = st.columns(2)
    with preset_cols[0]:
        st.button(
            SINGLE_SEAT_PRESETS[0]["label"],
            key="single_seat_preset_0",
            on_click=_apply_single_seat_preset,
            args=(SINGLE_SEAT_PRESETS[0],),
            use_container_width=True,
        )
    with preset_cols[1]:
        st.button(
            SINGLE_SEAT_PRESETS[1]["label"],
            key="single_seat_preset_1",
            on_click=_apply_single_seat_preset,
            args=(SINGLE_SEAT_PRESETS[1],),
            use_container_width=True,
        )

    st.markdown("##### Role definition")
    col1, col2 = st.columns(2)
    with col1:
        role = st.selectbox(
            "Role",
            options=[""] + sorted(role_lex_list),
            help="The primary role for this seat.",
            key="single_seat_role",
        )
    with col2:
        seniority = st.selectbox(
            "Seniority",
            options=["junior", "middle", "senior", "lead", "manager"],
            key="single_seat_seniority",
        )

    st.markdown("##### Technical skills & domains")
    must_have = st.multiselect(
        "Must-Have Tech",
        options=sorted(tech_lex_list),
        help="Hard requirements. Candidates will be ranked on matching these.",
        key="single_seat_must_have",
    )
    nice_to_have = st.multiselect(
        "Nice-to-Have Tech",
        options=sorted(tech_lex_list),
        help="Optional skills that add to the score.",
        key="single_seat_nice_to_have",
    )
    domains = st.multiselect(
        "Domains",
        options=sorted(domain_lex_list),
        help="Optional domain experience (e.g., 'fintech', 'healthtech').",
        key="single_seat_domains",
    )

    st.markdown("##### Search controls")
    top_k = st.slider("Top-K", min_value=1, max_value=10, value=2, key="single_seat_top_k")

    # Mode is always "llm" - other modes kept in code but hidden from UI
    mode = "llm"
    with_justification = False

    # LLM mode settings (always shown since mode is always "llm")
    llm_pool_size = None
    with st.expander("LLM Ranking Settings", expanded=True):
        llm_pool_size = st.slider(
            "Candidates to send to LLM",
            min_value=5,
            max_value=50,
            value=10,
            step=5,
            help="Number of lexical search results to pass to LLM for ranking. "
                 "Higher = more candidates evaluated, but higher token cost.",
            key="single_seat_llm_pool_size",
        )
        st.caption(f"LLM will rank top {llm_pool_size} lexical matches and return top {top_k}")

    # Track search state for button disable
    if "single_seat_searching" not in st.session_state:
        st.session_state["single_seat_searching"] = False

    submitted = st.button(
        "Searching..." if st.session_state["single_seat_searching"] else "Search for Candidates",
        type="primary",
        disabled=st.session_state["single_seat_searching"],
        use_container_width=True,
    )

    # Search execution inside left column so status block has correct width
    if submitted:
        if not role:
            st.warning("Please select a role.")
            st.stop()

        # Get values - mode is always "llm"
        search_mode = "llm"
        search_top_k = st.session_state.get("single_seat_top_k", 2)
        search_llm_pool_size = st.session_state.get("single_seat_llm_pool_size", 10)
        search_with_justification = False

        tech_stack = list(set(must_have + nice_to_have))
        seat_payload = {
            "role": role,
            "seniority": seniority,
            "domains": domains,
            "tech_tags": must_have,
            "nice_to_have": nice_to_have,
            "rationale": "Query built from Single Seat Search UI",
        }
        criteria = {
            "domain": domains,
            "tech_stack": tech_stack,
            "expert_roles": [role],
            "project_type": "greenfield",
            "team_size": {"total": 1, "members": [seat_payload]},
        }

        run_dir = None
        try:
            run_dir = default_run_dir(settings.active_runs_dir)
        except Exception as e:
            st.warning(f"Failed to create run directory: {e}. Running search without artifacts.")

        db = None
        payload = None

        # Set searching state and rerun to show disabled button immediately
        st.session_state["single_seat_searching"] = True

        try:
            with st.status("Searching for candidates...", expanded=True) as status:
                status.write("Connecting to database...")
                db = CVDatabase(settings)

                status.write("Initializing search processor...")
                processor = SearchProcessor(db, client, settings)

                status.write("Running LLM-based ranking...")

                payload = processor.search_for_seat(
                    criteria=criteria,
                    top_k=search_top_k,
                    run_dir=run_dir,
                    with_justification=search_with_justification,
                    user_email=user_email,
                    llm_pool_size=search_llm_pool_size,
                )

                if payload:
                    result_count = len(payload.get("results", []))
                    status.update(label=f"Search complete! Found {result_count} candidates.", state="complete")
                    st.session_state["single_seat_payload"] = payload
                    st.session_state["single_seat_run_id"] = payload.get("run_id")
                    st.session_state["single_seat_run_dir"] = run_dir
                else:
                    status.update(label="Search complete. No results.", state="complete")

        except Exception as e:
            st.error(f"An error occurred during search: {e}")

        finally:
            st.session_state["single_seat_searching"] = False
            if db:
                db.close()

single_payload = st.session_state.get("single_seat_payload")
with layout_cols[1]:
    st.markdown("#### Results")
    if not single_payload:
        st.markdown(
            '<div class="tt-empty-state"><strong>No results yet</strong>'
            "Run a single-seat search on the left to see ranked candidates."
            "</div>",
            unsafe_allow_html=True,
        )
    else:
        single_run_dir = st.session_state.get("single_seat_run_dir")
        single_run_id = st.session_state.get("single_seat_run_id")
        if single_run_dir:
            st.caption(f"Artifacts: {single_run_dir}")
            if Path(single_run_dir).exists():
                try:
                    zip_bytes = zip_directory(single_run_dir)
                    folder = Path(single_run_dir)
                    zip_name = f"{folder.parent.name}_{folder.name}.zip"
                    st.download_button(
                        "Download artifacts (.zip)",
                        data=zip_bytes,
                        file_name=zip_name,
                        mime="application/zip",
                    )
                except Exception as e:
                    st.error(f"Failed to create zip: {e}")

        if single_run_id:
            st.caption(f"Run ID: {single_run_id}")

        # Show token usage for LLM mode
        llm_ranking = single_payload.get("llm_ranking")
        if llm_ranking and llm_ranking.get("usage"):
            usage = llm_ranking["usage"]
            pool_size = len(llm_ranking.get("pool_candidate_ids", []))
            st.info(
                f"**LLM Ranking:** {pool_size} candidates evaluated | "
                f"Tokens: {usage.get('prompt_tokens', 0):,} prompt + "
                f"{usage.get('completion_tokens', 0):,} completion = "
                f"{usage.get('total_tokens', 0):,} total"
            )

        if not single_payload.get("results"):
            st.warning("No matching candidates found for this query.")

        db = None
        try:
            db = CVDatabase(settings)

            for result in single_payload.get("results", []):
                render_candidate_result(result, db, settings, "single_seat", score_label="Hybrid Score")
        except Exception as e:
            st.error(f"An error occurred during results rendering: {e}")
        finally:
            if db:
                db.close()

    run_id = single_payload.get("run_id") if single_payload else None
    if run_id:
        st.divider()
        render_run_feedback(run_id, settings, "single_seat")
