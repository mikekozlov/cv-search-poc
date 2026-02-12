import streamlit as st
import sys
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = APP_ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

try:
    from cv_search.app.streamlit_page_utils import (
        apply_text_preset,
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
    from cv_search.core.parser import parse_request
    from cv_search.db.database import CVDatabase
    from cv_search.planner.service import Planner
    from cv_search.search import SearchProcessor, default_run_dir
    from cv_search.llm.logger import set_run_dir as llm_set_run_dir, reset_run_dir as llm_reset_run_dir
    from cv_search.utils.archive import zip_directory
except ImportError as e:
    st.error(f"""
    **Failed to import project modules.**

    Ensure `app.py` is running from the project root and the `src` directory is correct.
    **Error:** {e}
    """)
    st.stop()


st.set_page_config(page_title="Project Search", page_icon="CV", layout="wide")
identity = require_login()
user_email = identity.email
inject_streamlit_theme()
inject_searching_button_style()
inject_candidate_result_styles()

render_page_header(
    "Project Search",
    "Build a multi-seat brief and search for matching candidates.",
)
st.divider()

PROJECT_BRIEF_PRESETS = [
    "Fintech lending platform needing senior backend in Python/FastAPI, plus one FE with "
    "React/TypeScript. Cloud on AWS, Postgres database.",
    "Healthcare SaaS analytics dashboard with data_engineer for pipelines (Python, SQL, dbt) "
    "and frontend_engineer for React charts. Must have HIPAA domain exposure.",
]


ensure_services_loaded()

try:
    planner: Planner = st.session_state.planner
    settings: Settings = st.session_state.settings
    client: OpenAIClient = st.session_state.client
except KeyError as e:
    st.error(f"Failed to load service: {e}. Please return to the Home page and reload.")
    st.stop()


layout_cols = st.columns([1.15, 1.45], gap="large")
with layout_cols[0]:
    st.markdown("#### Project brief")
    st.caption("Quick briefs")
    preset_cols = st.columns(2)
    preset_cols[0].button(
        "Fintech lending platform",
        key="project_brief_preset_0",
        on_click=apply_text_preset,
        args=("project_search_text_brief", PROJECT_BRIEF_PRESETS[0]),
        use_container_width=True,
    )
    preset_cols[1].button(
        "Healthcare analytics dashboard",
        key="project_brief_preset_1",
        on_click=apply_text_preset,
        args=("project_search_text_brief", PROJECT_BRIEF_PRESETS[1]),
        use_container_width=True,
    )
    text_brief = st.text_area(
        "Enter a free-text project brief:",
        height=200,
        placeholder=(
            "e.g., 'We need two senior .NET developers and one React dev for a fintech project...'"
        ),
        key="project_search_text_brief",
    )

    st.divider()
    st.markdown("#### Search controls")
    top_k = st.slider("Top-K", min_value=1, max_value=10, value=2, key="project_search_top_k")

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
            key="project_search_llm_pool_size",
        )
        st.caption(f"LLM will rank top {llm_pool_size} lexical matches and return top {top_k}")

    # Track search state for button disable
    if "project_searching" not in st.session_state:
        st.session_state["project_searching"] = False

    run_project_search = st.button(
        "Searching..." if st.session_state["project_searching"] else "Search for Project",
        type="primary",
        disabled=st.session_state["project_searching"],
        use_container_width=True,
    )

    # Search execution inside left column so status block has correct width
    if run_project_search:
        payload = None
        raw_text = None
        crit_obj = None
        run_dir = None
        llm_token = None

        if not text_brief or not text_brief.strip():
            st.warning("Please provide a text brief.")
            st.stop()

        # Set searching state
        st.session_state["project_searching"] = True

        raw_text = text_brief.strip()

        # Mode is always "llm"
        search_mode = "llm"
        search_llm_pool_size = st.session_state.get("project_search_llm_pool_size", 10)

        try:
            with st.status("Processing project search...", expanded=True) as status:
                status.write("Creating run directory...")
                try:
                    run_dir = default_run_dir(settings.active_runs_dir)
                    llm_token = llm_set_run_dir(run_dir)
                except Exception as e:
                    st.warning(
                        f"Failed to create run directory: {e}. Running search without artifacts."
                    )

                status.write("Parsing text brief...")
                try:
                    crit_obj = parse_request(
                        raw_text,
                        settings.openai_model,
                        settings,
                        client,
                        run_dir=run_dir,
                    )
                    raw_text = getattr(crit_obj, "_english_brief", None) or raw_text
                finally:
                    if llm_token is not None:
                        llm_reset_run_dir(llm_token)

                if crit_obj:
                    status.write("Connecting to database...")
                    db = CVDatabase(settings)

                    status.write("Initializing search processor...")
                    processor = SearchProcessor(db, client, settings)

                    status.write("Running LLM-based ranking...")

                    payload = processor.search_for_project(
                        criteria=crit_obj,
                        top_k=top_k,
                        run_dir=run_dir,
                        raw_text=raw_text,
                        with_justification=with_justification,
                        user_email=user_email,
                        llm_pool_size=search_llm_pool_size,
                    )

                    if db:
                        db.close()

                    if not payload:
                        status.update(label="Search failed to return results.", state="error")
                    else:
                        seat_count = len(payload.get("seats", []))
                        status.update(label=f"Search complete! Found results for {seat_count} seat(s).", state="complete")
                        st.session_state["project_search_payload"] = payload
                        st.session_state["project_search_raw_text"] = raw_text
                        st.session_state["project_search_run_id"] = payload.get("run_id")
                        st.session_state["project_search_run_dir"] = payload.get("run_dir")

        except Exception as e:
            st.error(f"An error occurred during search: {e}")

        finally:
            st.session_state["project_searching"] = False

project_payload = st.session_state.get("project_search_payload")
project_raw_text = st.session_state.get("project_search_raw_text")
with layout_cols[1]:
    st.markdown("#### Results")
    if not project_payload:
        st.markdown(
            '<div class="tt-empty-state"><strong>No results yet</strong>'
            "Run a project search on the left to see candidate seats and summaries."
            "</div>",
            unsafe_allow_html=True,
        )
    else:
        if project_raw_text:
            with st.expander("Show Derived Criteria"):
                st.json(project_payload.get("project_criteria"))

        if not project_payload.get("seats"):
            st.warning(
                "No canonical roles could be derived from this brief, so no candidates were searched."
            )
            note = project_payload.get("note")
            if note:
                st.info(note)
        else:
            if project_payload.get("gaps"):
                st.warning(f"Could not find candidates for seat(s): {project_payload['gaps']}")

            seat_tabs = st.tabs(
                [f"Seat {s['index']}: {s['role']}" for s in project_payload["seats"]]
            )
            db = None
            try:
                db = CVDatabase(settings)

                for i, seat_data in enumerate(project_payload["seats"]):
                    with seat_tabs[i]:
                        st.write(f"**Role:** {seat_data['role']}")
                        seat_rationale = "No rationale provided."
                        try:
                            seat_rationale = seat_data["criteria"]["team_size"]["members"][0][
                                "rationale"
                            ]
                        except (KeyError, IndexError):
                            pass
                        st.write(f"**Rationale:** *{seat_rationale}*")

                        if not seat_data["results"]:
                            st.write("No matching candidates found.")
                            continue

                        for result in seat_data["results"]:
                            key_prefix = f"project_seat_{seat_data['index']}"
                            render_candidate_result(result, db, settings, key_prefix)
            except Exception as e:
                st.error(f"An error occurred during results rendering: {e}")
            finally:
                if db:
                    db.close()

        # Display SME/Specialist recommendations (not searched)
        sme_roles = project_payload.get("sme_roles", [])
        if sme_roles:
            st.divider()
            st.markdown("#### Additional Specialists (Recommended)")
            st.info(
                "These specialist roles were identified but not searched. "
                "Consider adding them for specialized requirements."
            )
            for sme in sme_roles:
                seniority_raw = sme.get("seniority") or "senior"
                # Handle enum objects (e.g., SeniorityEnum.senior -> "senior")
                seniority = seniority_raw.value if hasattr(seniority_raw, "value") else str(seniority_raw)
                role_name = (sme.get("role") or "").replace("_", " ").title()
                st.markdown(f"- **{role_name}** ({seniority})")

        project_run_dir = st.session_state.get("project_search_run_dir")
        project_run_id = st.session_state.get("project_search_run_id")
        if project_run_dir:
            st.caption(f"Artifacts: {project_run_dir}")
            if Path(project_run_dir).exists():
                try:
                    zip_bytes = zip_directory(project_run_dir)
                    folder = Path(project_run_dir)
                    zip_name = f"{folder.parent.name}_{folder.name}.zip"
                    st.download_button(
                        "Download artifacts (.zip)",
                        data=zip_bytes,
                        file_name=zip_name,
                        mime="application/zip",
                    )
                except Exception as e:
                    st.error(f"Failed to create zip: {e}")

        if project_run_id:
            st.caption(f"Run ID: {project_run_id}")
            st.divider()
            render_run_feedback(project_run_id, settings, "project_search")
