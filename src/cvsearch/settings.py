from __future__ import annotations
from pathlib import Path
from typing import Optional
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import SecretStr

REPO_ROOT = Path(__file__).resolve().parents[2]

class Settings(BaseSettings):
    """
    Centralized application settings. Loads from .env file or environment variables.
    """
    model_config = SettingsConfigDict(
        env_file=REPO_ROOT / '.env',
        env_file_encoding='utf-8',
        extra='ignore'
    )

    # --- Client Toggle ---
    use_azure_openai: bool = Field(
        default=False,
        description="Set to True to use AzureOpenAI, False for standard OpenAI."
    )

    # --- Standard OpenAI Settings ---
    openai_api_key: Optional[SecretStr] = None # This will ALSO be used for Azure's 'api_key'

    # --- Azure OpenAI Settings ---
    azure_endpoint: Optional[str] = Field(
        default=None,
        description="The endpoint for your Azure OpenAI resource (e.g., 'https://...')"
    )
    azure_api_version: Optional[str] = Field(
        default=None,
        description="The API version for Azure OpenAI (e.g., '2024-12-01-preview')"
    )

    # --- Model Names (Deployment Names for Azure) ---
    openai_model: str = Field(
        default="gpt-4.1-mini",
        description="The model name (OpenAI) or deployment name (Azure) for chat."
    )
    openai_embed_model: str = Field(
        default="text-embedding-3-large",
        description="The model name (OpenAI) or deployment name (Azure) for embeddings."
    )


    search_mode: str = "hybrid"
    search_vs_topk: int = 8
    search_w_lex: float = 1.0
    search_w_sem: float = 0.8

    db_path: Path = Field(default_factory=lambda: REPO_ROOT / "cvsearch.db")
    data_dir: Path = Field(default_factory=lambda: REPO_ROOT / "data")
    lexicon_dir: Path = Field(default_factory=lambda: REPO_ROOT / "data" / "lexicons")
    schema_file: Path = Field(default_factory=lambda: REPO_ROOT / "src" / "cvsearch" / "schema.sql")

    faiss_index_path: Path = Field(default_factory=lambda: REPO_ROOT / "data" / "cv_search.faiss")
    faiss_doc_map_path: Path = Field(default_factory=lambda: REPO_ROOT / "data" / "cv_search_docs.json")

    # --- NEW: Google Drive Sync Settings ---
    gdrive_rclone_config_path: Optional[Path] = Field(
        default=None,
        description="Path to your rclone.conf file. If None, rclone will try its default locations."
    )
    gdrive_remote_name: str = Field(
        default="gdrive",
        description="The name of your Google Drive remote in rclone (e.g., 'gdrive')."
    )
    gdrive_source_dir: str = Field(
        default="CV_Inbox",
        description="The specific folder path on Google Drive to sync from."
    )
    gdrive_local_dest_dir: Path = Field(
        default_factory=lambda: REPO_ROOT / "data" / "gdrive_inbox",
        description="The local directory to download/sync files into."
    )

    @property
    def openai_api_key_str(self) -> str | None:
        """Return the OpenAI API key as a plain string."""
        return self.openai_api_key.get_secret_value() if self.openai_api_key else None