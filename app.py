import streamlit as st
import sys
from pathlib import Path
from typing import Dict, Any  # <-- Added Dict, Any for type hints

APP_ROOT = Path(__file__).resolve().parent
SRC_PATH = APP_ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

try:
    from cv_search.app.bootstrap import load_stateless_services as bootstrap_stateless_services
    from cv_search.app.streamlit_theme import card, inject_streamlit_theme, render_page_header
    from cv_search.auth_guard import require_login
except ImportError as e:
    st.error(f"""
    **Failed to import project modules.**
    
    Please ensure:
    1. This `app.py` file is in the root of your `cv-search` repository.
    2. The `src` directory exists and contains your project code.
    
    **Error:** {e}
    """)
    st.stop()


@st.cache_resource
def load_stateless_services() -> Dict[str, Any]:
    """
    Initializes all STATELESS services and lexicons *once* and caches them.
    The DB connection and processor will be created on-demand in each page.
    """
    print("--- [Cache Miss] Loading stateless services... ---")

    services: Dict[str, Any] = bootstrap_stateless_services()
    print("--- Stateless services loaded and cached. ---")
    return services


st.set_page_config(page_title="CV Search Home", page_icon="CV", layout="wide")
require_login()

inject_streamlit_theme()

if "services_loaded" not in st.session_state:
    services = load_stateless_services()
    st.session_state.update(services)
    st.session_state["services_loaded"] = True

render_page_header(
    "It's time to search your CVs!",
    "Pick a workflow from the sidebar to start.",
)

cols = st.columns([2, 1])
with cols[0]:
    with card():
        st.markdown("#### Quick start")
        st.markdown(
            "Use the Streamlit sidebar to navigate the main workflows for CV search and ingestion."
        )
        st.markdown("- Project Search: build a multi-seat brief and get ranked candidates.")
        st.markdown("- Single Seat Search: run focused searches for a single role.")
        st.markdown("- Admin & Ingest: upload CVs and check system status.")

with cols[1]:
    with card():
        st.markdown("#### System status")
        try:
            col1, col2 = st.columns(2)
            # len() works on both lists and dicts, so this logic is unchanged.
            col1.metric("Roles", len(st.session_state.role_lex))
            col2.metric("Tech", len(st.session_state.tech_lex))
            st.metric("Domains", len(st.session_state.domain_lex))
        except Exception as e:
            st.error(f"Failed to load system status. Error: {e}")
