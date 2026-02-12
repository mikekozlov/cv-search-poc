import streamlit as st
import sys
from datetime import datetime
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = APP_ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

try:
    from cv_search.app.bootstrap import load_stateless_services as bootstrap_stateless_services
    from cv_search.app.streamlit_theme import inject_streamlit_theme, render_page_header
    from cv_search.auth_guard import require_login
    from cv_search.clients.openai_client import OpenAIClient
    from cv_search.config.settings import Settings
    from cv_search.db.database import CVDatabase
    from cv_search.ingestion.pipeline import CVIngestionPipeline
except ImportError as e:
    st.error(f"""
    **Failed to import project modules.**
    
    Ensure `app.py` is running from the project root and the `src` directory is correct.
    **Error:** {e}
    """)
    st.stop()


st.set_page_config(page_title="Admin & Ingest", page_icon="CV", layout="wide")
require_login()
inject_streamlit_theme()

render_page_header(
    "Admin & Ingest",
    "Upload CVs, run ingestion, and review system status.",
)
st.divider()


@st.cache_resource
def load_stateless_services() -> dict[str, object]:
    return bootstrap_stateless_services()


if "services_loaded" not in st.session_state:
    services = load_stateless_services()
    st.session_state.update(services)
    st.session_state["services_loaded"] = True

try:
    settings: Settings = st.session_state.settings
    client: OpenAIClient = st.session_state.client
except KeyError as e:
    st.error(f"Failed to load service: {e}. Please return to the Home page and reload.")
    st.stop()


def get_db_pipeline():
    """Creates a new DB and Pipeline instance for thread safety."""
    db = CVDatabase(settings)
    pipeline = CVIngestionPipeline(db, settings)
    return db, pipeline


layout_cols = st.columns([2, 1])
with layout_cols[0]:
    st.markdown("#### Upload CV (.pptx)")
    st.info(
        "Upload a single .pptx CV file. It will be processed with the same flow as the "
        "Google Drive ingestion, and the source will be recorded as uploads."
    )

    uploaded_file = st.file_uploader(
        "Upload CV (.pptx)",
        type=["pptx"],
        accept_multiple_files=False,
    )

    if st.button("Ingest uploaded CV", type="primary"):
        if not uploaded_file:
            st.warning("Please upload a .pptx file.")
        else:
            db, pipeline = get_db_pipeline()
            try:
                upload_dir = settings.uploads_dir
                upload_dir.mkdir(parents=True, exist_ok=True)

                original_name = Path(uploaded_file.name).name
                target_path = upload_dir / original_name
                if target_path.exists():
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    target_path = (
                        upload_dir
                        / f"{Path(original_name).stem}_{timestamp}{Path(original_name).suffix}"
                    )

                with open(target_path, "wb") as handle:
                    handle.write(uploaded_file.getbuffer())

                json_output_dir = settings.data_dir / "ingested_cvs_json"
                json_output_dir.mkdir(exist_ok=True)
                inbox_root = settings.uploads_dir.parent

                with st.spinner("Parsing and ingesting CV..."):
                    status, data = pipeline._process_single_cv_file(
                        target_path,
                        pipeline.parser,
                        client,
                        json_output_dir,
                        inbox_root,
                    )

                    if status != "processed":
                        st.error("Failed to parse the uploaded file. Check logs for details.")
                    else:
                        _, cv_data = data
                        count = pipeline.upsert_cvs([cv_data])

                        st.cache_resource.clear()
                        st.session_state.clear()

                        st.success(f"Successfully ingested {count} CV from upload.")
                        st.info(
                            "Source category set to 'uploads'. Refresh or return Home to continue."
                        )

            except Exception as e:
                st.error(f"An error occurred during upload ingestion: {e}")

            finally:
                if db:
                    db.close()

with layout_cols[1]:
    st.markdown("#### System status")
    if st.button("Refresh System Status"):
        db = None
        try:
            db = CVDatabase(settings)
            tables = db.check_tables()
            counts = db.conn.execute("SELECT COUNT(*) AS c FROM candidate").fetchone()
            docs = db.conn.execute(
                "SELECT COUNT(*) AS total_docs, COUNT(embedding) AS with_embeddings FROM candidate_doc"
            ).fetchone()
            ext = db.check_extensions()

            col1, col2 = st.columns(2)
            col1.metric("Candidates", counts["c"])
            col2.metric("Docs w/ embeddings", docs["with_embeddings"])
            st.metric("Tables", len(tables))
            st.info(f"Tables found: {', '.join(tables)}")
            st.caption(f"Extensions -> vector: {ext.get('vector')}, pg_trgm: {ext.get('pg_trgm')}")

        except Exception as e:
            st.error(f"Could not read system status. Is the DB initialized? Error: {e}")

        finally:
            if db:
                db.close()
