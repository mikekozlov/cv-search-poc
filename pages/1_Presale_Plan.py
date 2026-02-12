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
        render_candidate_result,
        render_role_chips,
        render_run_feedback,
    )
    from cv_search.app.streamlit_results import inject_candidate_result_styles
    from cv_search.app.streamlit_theme import inject_streamlit_theme, inject_searching_button_style, render_page_header
    from cv_search.auth_guard import require_login
    from cv_search.clients.openai_client import OpenAIClient
    from cv_search.config.settings import Settings
    from cv_search.core.criteria import Criteria, SeniorityEnum
    from cv_search.core.parser import parse_request
    from cv_search.db.database import CVDatabase
    from cv_search.planner.service import Planner
    from cv_search.presale import build_presale_search_criteria
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


st.set_page_config(page_title="Presale Plan", page_icon="CV", layout="wide")
identity = require_login()
user_email = identity.email
inject_streamlit_theme()
inject_searching_button_style()
inject_candidate_result_styles()

render_page_header(
    "Presale Planning",
    "Generate team compositions for presale briefs and search for candidates.",
)
st.divider()

PRESALE_BRIEF_PRESETS = [
    "Marketplace MVP: buyer/seller flows, payments, and admin console. Mobile-first web app "
    "with React, Node.js, and Postgres. Need guidance on presale roles.",
    "AI-enabled customer support portal with chat and knowledge base search. Uses Python, "
    "FastAPI, vector search, and React UI. Need a presale team plan.",
]


ensure_services_loaded()

try:
    planner: Planner = st.session_state.planner
    settings: Settings = st.session_state.settings
    client: OpenAIClient = st.session_state.client
except KeyError as e:
    st.error(f"Failed to load service: {e}. Please return to the Home page and reload.")
    st.stop()


# Two-column layout
layout_cols = st.columns([1.15, 1.45], gap="large")

with layout_cols[0]:
    st.markdown("#### Presale brief")
    st.caption("Quick briefs")
    preset_cols = st.columns(2)
    preset_cols[0].button(
        "Marketplace MVP",
        key="presale_brief_preset_0",
        on_click=apply_text_preset,
        args=("presale_plan_text_brief", PRESALE_BRIEF_PRESETS[0]),
        use_container_width=True,
    )
    preset_cols[1].button(
        "AI support portal",
        key="presale_brief_preset_1",
        on_click=apply_text_preset,
        args=("presale_plan_text_brief", PRESALE_BRIEF_PRESETS[1]),
        use_container_width=True,
    )

    presale_text = st.text_area(
        "Enter a project brief to plan for:",
        height=200,
        placeholder=(
            "e.g., 'Mobile + web app with Flutter/React; AI chatbot for goal setting...'"
        ),
        key="presale_plan_text_brief",
    )

    # Track planning state for button disable
    if "presale_planning" not in st.session_state:
        st.session_state["presale_planning"] = False

    submitted = st.button(
        "Generating..." if st.session_state["presale_planning"] else "Generate Presale Plan",
        type="primary",
        disabled=st.session_state["presale_planning"],
        use_container_width=True,
    )

    # Handle plan generation right after button (so status appears here)
    if submitted:
        if not presale_text.strip():
            st.warning("Please enter a brief.")
        else:
            st.session_state["presale_planning"] = True
            presale_run_dir = None
            llm_token = None
            try:
                with st.status("Generating presale plan...", expanded=True) as status:
                    status.write("Creating run directory...")
                    try:
                        run_root = Path(settings.active_runs_dir) / "presale_search"
                        presale_run_dir = default_run_dir(run_root, subdir=None)
                        llm_token = llm_set_run_dir(presale_run_dir)
                    except Exception as e:
                        st.warning(
                            f"Failed to create run directory: {e}. "
                            "Presale plan will not write artifacts."
                        )

                    status.write("Parsing brief...")
                    crit = parse_request(
                        presale_text,
                        model=settings.openai_model,
                        settings=settings,
                        client=client,
                        include_presale=True,
                    )

                    status.write("Deriving presale team...")
                    raw_text_en = getattr(crit, "_english_brief", None) or presale_text
                    crit = planner.derive_presale_team(
                        crit,
                        raw_text=raw_text_en,
                        client=client,
                        settings=settings,
                    )

                    if presale_run_dir:
                        status.write("Saving artifacts...")
                        try:
                            Path(presale_run_dir, "criteria.json").write_text(
                                crit.to_json(),
                                encoding="utf-8",
                            )
                        except Exception as e:
                            st.warning(f"Failed to write presale plan artifacts: {e}")

                    st.session_state["presale_criteria"] = crit
                    st.session_state["presale_source_text"] = presale_text
                    st.session_state["presale_plan_run_dir"] = presale_run_dir
                    st.session_state.pop("presale_search_payload", None)
                    st.session_state.pop("presale_search_run_dir", None)
                    st.session_state.pop("presale_search_run_id", None)
                    st.session_state.pop("presale_search_criteria", None)

                    min_team = len(crit.minimum_team or [])
                    ext_team = len(crit.extended_team or [])
                    status.update(label=f"Plan complete! {min_team} minimum + {ext_team} extended roles.", state="complete")

            except Exception as e:
                st.error(f"Error during planning: {e}")
            finally:
                st.session_state["presale_planning"] = False
                if llm_token is not None:
                    llm_reset_run_dir(llm_token)

    st.divider()
    st.markdown("#### Search controls")

    include_extended = st.toggle(
        "Include extended roles",
        value=False,
        key="presale_search_include_extended",
    )
    seniority_choice = st.selectbox(
        "Default seniority",
        options=[e.value for e in SeniorityEnum],
        index=2,
        key="presale_search_seniority",
    )

    presale_top_k = st.slider("Top-K", min_value=1, max_value=10, value=3, key="presale_search_top_k")

    # Mode is always "llm" - other modes kept in code but hidden from UI
    presale_mode = "llm"
    presale_with_justification = False

    # LLM mode settings (always shown since mode is always "llm")
    presale_llm_pool_size = None
    with st.expander("LLM Ranking Settings", expanded=True):
        presale_llm_pool_size = st.slider(
            "Candidates to send to LLM",
            min_value=5,
            max_value=50,
            value=10,
            step=5,
            help="Number of lexical search results to pass to LLM for ranking. "
                 "Higher = more candidates evaluated, but higher token cost.",
            key="presale_search_llm_pool_size",
        )
        st.caption(f"LLM will rank top {presale_llm_pool_size} lexical matches and return top {presale_top_k}")

    # Track search state for button disable
    if "presale_searching" not in st.session_state:
        st.session_state["presale_searching"] = False

    run_presale_search = st.button(
        "Searching..." if st.session_state["presale_searching"] else "Search for Candidates",
        type="primary",
        disabled=st.session_state["presale_searching"],
        use_container_width=True,
        key="presale_search_btn",
    )

    # Search execution inside left column so status block has correct width
    if run_presale_search:
        presale_criteria_for_search: Criteria | None = st.session_state.get("presale_criteria")
        if not presale_criteria_for_search:
            st.warning("Please generate a presale plan first.")
        else:
            search_criteria = build_presale_search_criteria(
                presale_criteria_for_search,
                include_extended=include_extended,
                seniority=seniority_choice,
            )
            if not search_criteria.team_size or not search_criteria.team_size.members:
                st.warning("No roles selected for search. Generate a plan with roles first.")
            else:
                st.session_state["presale_searching"] = True
                db = None

                # Mode is always "llm"
                presale_search_mode = "llm"
                presale_search_llm_pool_size = st.session_state.get("presale_search_llm_pool_size", 10)

                try:
                    with st.status("Searching for candidates...", expanded=True) as status:
                        status.write("Setting up run directory...")
                        run_dir = st.session_state.get("presale_plan_run_dir")
                        if not run_dir:
                            run_root = Path(settings.active_runs_dir) / "presale_search"
                            run_dir = default_run_dir(run_root, subdir=None)

                        status.write("Connecting to database...")
                        db = CVDatabase(settings)

                        status.write("Initializing search processor...")
                        processor = SearchProcessor(db, client, settings)

                        status.write("Running LLM-based ranking...")

                        payload = processor.search_for_project(
                            criteria=search_criteria,
                            top_k=presale_top_k,
                            run_dir=run_dir,
                            raw_text=None,
                            with_justification=presale_with_justification,
                            run_kind="presale_search",
                            user_email=user_email,
                            llm_pool_size=presale_search_llm_pool_size,
                        )

                        seat_count = len(payload.get("seats", []))
                        status.update(label=f"Search complete! Found results for {seat_count} role(s).", state="complete")

                        st.session_state["presale_search_payload"] = payload
                        st.session_state["presale_search_run_dir"] = payload.get("run_dir")
                        st.session_state["presale_search_run_id"] = payload.get("run_id")
                        st.session_state["presale_search_criteria"] = search_criteria

                except Exception as e:
                    st.error(f"An error occurred during presale search: {e}")
                finally:
                    st.session_state["presale_searching"] = False
                    if db:
                        db.close()

# Right panel - Results
presale_criteria: Criteria | None = st.session_state.get("presale_criteria")
presale_search_payload = st.session_state.get("presale_search_payload")

with layout_cols[1]:
    st.markdown("#### Results")

    if not presale_criteria and not presale_search_payload:
        st.markdown(
            '<div class="tt-empty-state"><strong>No results yet</strong>'
            "Generate a presale plan on the left to see recommended team roles."
            "</div>",
            unsafe_allow_html=True,
        )
    else:
        # Show presale plan results
        if presale_criteria:
            st.subheader("Recommended Presale Team")

            cols = st.columns(2)
            with cols[0]:
                render_role_chips("Minimum team", presale_criteria.minimum_team)
            with cols[1]:
                render_role_chips("Extended team", presale_criteria.extended_team)

            if presale_criteria.presale_rationale:
                st.markdown("**Rationale**")
                st.info(presale_criteria.presale_rationale)

            criteria_json = presale_criteria.to_json()

            presale_plan_run_dir = st.session_state.get("presale_plan_run_dir")
            if presale_plan_run_dir:
                st.caption(f"Artifacts: {presale_plan_run_dir}")
                if Path(presale_plan_run_dir).exists():
                    try:
                        zip_bytes = zip_directory(presale_plan_run_dir)
                        folder = Path(presale_plan_run_dir)
                        zip_name = f"{folder.parent.name}_{folder.name}.zip"
                        st.download_button(
                            "Download plan artifacts (.zip)",
                            data=zip_bytes,
                            file_name=zip_name,
                            mime="application/zip",
                        )
                    except Exception as e:
                        st.error(f"Failed to create zip: {e}")

            with st.expander("Show / Copy Criteria JSON"):
                st.code(criteria_json, language="json")

        # Show search results
        if presale_search_payload:
            st.divider()
            st.subheader("Candidate Search Results")

            presale_search_run_dir = st.session_state.get("presale_search_run_dir")
            if presale_search_run_dir:
                st.caption(f"Artifacts: {presale_search_run_dir}")
                if Path(presale_search_run_dir).exists():
                    try:
                        zip_bytes = zip_directory(presale_search_run_dir)
                        folder = Path(presale_search_run_dir)
                        zip_name = f"{folder.parent.name}_{folder.name}.zip"
                        st.download_button(
                            "Download search artifacts (.zip)",
                            data=zip_bytes,
                            file_name=zip_name,
                            mime="application/zip",
                        )
                    except Exception as e:
                        st.error(f"Failed to create zip: {e}")

            with st.expander("Show search criteria"):
                st.json(presale_search_payload.get("project_criteria"))

            gaps = presale_search_payload.get("gaps") or []
            if gaps:
                gap_roles = [
                    s.get("role")
                    for s in (presale_search_payload.get("seats") or [])
                    if s.get("index") in set(gaps)
                ]
                gap_label = ", ".join([r for r in gap_roles if r]) or str(gaps)
                st.warning(f"Could not find candidates for: {gap_label}")

            seats = presale_search_payload.get("seats") or []
            if not seats:
                st.warning("No seats were searched. Generate a plan and try again.")
            else:
                db = None
                try:
                    db = CVDatabase(settings)
                    seat_tabs = st.tabs([f"Seat {s['index']}: {s['role']}" for s in seats])

                    for i, seat_data in enumerate(seats):
                        with seat_tabs[i]:
                            st.write(f"**Role:** {seat_data['role']}")
                            if not seat_data.get("results"):
                                st.write("No matching candidates found.")
                                continue

                            for result in seat_data["results"]:
                                key_prefix = f"presale_seat_{seat_data['index']}"
                                render_candidate_result(result, db, settings, key_prefix)
                except Exception as e:
                    st.error(f"An error occurred during results rendering: {e}")
                finally:
                    if db:
                        db.close()

            presale_run_id = st.session_state.get("presale_search_run_id")
            if presale_run_id:
                st.divider()
                render_run_feedback(presale_run_id, settings, "presale_search")
