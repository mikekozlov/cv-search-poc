from __future__ import annotations

from pathlib import Path
from typing import Optional

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


REPO_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=REPO_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    use_azure_openai: bool = Field(
        default=False,
        description="Set to True to use Azure OpenAI, False for standard OpenAI.",
    )

    openai_api_key: Optional[SecretStr] = None

    azure_endpoint: Optional[str] = Field(default=None)
    azure_api_version: Optional[str] = Field(default=None)

    openai_model: str = Field(default="gpt-4.1-mini")
    openai_audio_model: str = Field(default="whisper-1")
    openai_reasoning_effort: str = Field(
        default="medium",
        validation_alias="OPENAI_REASONING_EFFORT",
        description="Reasoning effort for GPT-5 models: minimal, low, medium, high.",
    )

    candidate_name_salt: Optional[str] = Field(
        default=None,
        validation_alias="CANDIDATE_NAME_SALT",
        description="Optional salt for anonymized candidate display names.",
    )
    candidate_name_prefix: str = Field(
        default="Candidate",
        validation_alias="CANDIDATE_NAME_PREFIX",
        description="Prefix for anonymized candidate display names.",
    )

    search_fanin_multiplier: int = Field(
        default=10,
        description="Scale lexical fan-in as top_k * multiplier.",
    )
    search_lex_fanin_max: int = Field(
        default=250,
        description="Hard cap on lexical fan-in to keep queries bounded.",
    )

    # --- LLM verdict ranking (lexical -> LLM) ---
    search_llm_pool_multiplier: int = Field(
        default=10,
        description="Candidate pool size sent to LLM as top_k * multiplier (bounded by search_llm_pool_max).",
    )
    search_llm_pool_max: int = Field(
        default=30,
        description="Hard cap on number of lexical candidates to send to the LLM for ranking.",
    )
    search_llm_context_chars: int = Field(
        default=2500,
        description="Max characters of per-candidate CV context included in the LLM ranking prompt.",
    )
    search_llm_compact_context: bool = Field(
        default=True,
        description="Use compact evidence-only format for LLM ranking context (reduces input tokens).",
    )
    search_llm_tiered_output: bool = Field(
        default=True,
        description="Request scores for all candidates but narratives only for top_k (reduces output tokens).",
    )
    search_llm_evidence_max_chars: int = Field(
        default=400,
        description="Max characters for compact evidence context per candidate.",
    )

    db_url: str = Field(
        default="postgresql://cvsearch:cvsearch@localhost:5433/cvsearch",
        validation_alias="DB_URL",
        description="Primary Postgres DSN for all environments.",
    )
    db_pool_min_size: int = Field(default=1)
    db_pool_max_size: int = Field(default=4)
    schema_pg_file: Path = Field(
        default_factory=lambda: REPO_ROOT / "src" / "cv_search" / "db" / "schema_pg.sql"
    )

    data_dir: Path = Field(default_factory=lambda: REPO_ROOT / "data")
    test_data_dir: Path = Field(default_factory=lambda: REPO_ROOT / "data" / "test")
    lexicon_dir: Path = Field(default_factory=lambda: REPO_ROOT / "data" / "lexicons")
    runs_dir: Path = Field(default_factory=lambda: REPO_ROOT / "runs")

    gdrive_rclone_config_path: Optional[Path] = Field(default=None)
    gdrive_remote_name: str = Field(default="gdrive")
    gdrive_source_dir: str = Field(default="CV_Inbox")
    gdrive_local_dest_dir: Path = Field(default_factory=lambda: REPO_ROOT / "data" / "gdrive_inbox")
    uploads_dir: Path = Field(default_factory=lambda: REPO_ROOT / "data" / "uploads")

    ingest_watch_debounce_ms: int = Field(
        default=750,
        description="Debounce window (ms) for local inbox filesystem events.",
    )
    ingest_watch_stable_ms: int = Field(
        default=1500,
        description="Stability window (ms) before ingesting a changing file.",
    )
    ingest_watch_dedupe_ttl_s: int = Field(
        default=24 * 60 * 60,
        description="TTL (seconds) for per-file event dedupe keys in Redis.",
    )
    ingest_watch_reconcile_interval_s: Optional[int] = Field(
        default=10 * 60,
        description="Periodic reconciliation scan interval (seconds). Set empty/0 to disable.",
    )

    llm_stub_dir: Path = Field(default_factory=lambda: REPO_ROOT / "data" / "test" / "llm_stubs")

    # --- API Server Settings ---
    api_host: str = Field(
        default="0.0.0.0",
        validation_alias="API_HOST",
        description="Host to bind the API server to.",
    )
    api_port: int = Field(
        default=8000,
        validation_alias="API_PORT",
        description="Port to bind the API server to.",
    )
    api_key: Optional[SecretStr] = Field(
        default=None,
        validation_alias="API_KEY",
        description="Optional API key for chatbot authentication. If not set, no auth required.",
    )
    api_cors_origins: str = Field(
        default="*",
        validation_alias="API_CORS_ORIGINS",
        description="Comma-separated list of allowed CORS origins, or '*' for all.",
    )

    log_level: str = Field(
        default="INFO",
        validation_alias="LOG_LEVEL",
        description="Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL).",
    )

    @property
    def openai_api_key_str(self) -> str | None:
        return self.openai_api_key.get_secret_value() if self.openai_api_key else None

    @property
    def active_db_url(self) -> str:
        return self.db_url

    @property
    def active_runs_dir(self) -> Path:
        return self.runs_dir
