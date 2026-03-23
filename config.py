"""Application settings model and environment parsing helpers."""

from pathlib import Path
from typing import Annotated

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration loaded from `.env` and process environment."""

    # --- Server Configuration ---
    MCP_HOST: str = "127.0.0.1"
    MCP_PORT: int = 8000
    TRANSPORT: str = "sse"
    DEBUG: bool = False
    LOG_LEVEL: str = "INFO"
    LOG_JSON: bool = False
    LOG_FILE: str = "logs/fastmcp.log"
    LOG_MAX_BYTES: int = 5_242_880
    LOG_BACKUP_COUNT: int = 5
    ERROR_LOCALE: str = "uk"
    ALERT_WEBHOOK_URL: str | None = None
    ALERT_WEBHOOK_TIMEOUT_SEC: float = 3.0
    ERROR_REPORTS_FILE: str = "logs/error_reports.jsonl"

    # --- Authentication (GitHub) ---
    # can be switched off, therefore Optional
    # it's recommended to set these authentication variables via env/(or even os) variables or CLI, not hardcoded
    AUTH_ENABLED: bool = True

    FASTMCP_SERVER_AUTH_GITHUB_CLIENT_ID: str | None = None
    FASTMCP_SERVER_AUTH_GITHUB_CLIENT_SECRET: str | None = None
    FASTMCP_SERVER_AUTH_GITHUB_BASE_URL: str | None = None

    # admin GitHub user IDs
    # write users in .env that you want to have access to potentially dangerous operations (delete, write, modify roots, etc.)
    # (comma-separated in .env: ADMIN_GITHUB_IDS=githubid,githubid2)])
    ADMIN_GITHUB_IDS: Annotated[list[str], NoDecode] = Field(default_factory=list)

    # --- Security & Storage ---
    USE_PERSISTENT_STORAGE: bool = False

    # turns out github jwt keys are opaque,so they verify them by calling GitHub's API
    JWT_SIGNING_KEY: str | None = None
    STORAGE_ENCRYPTION_KEY: str | None = None
    USE_REDIS: bool = False
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379

    # --- Filesystem Config ---
    # Please specify allowed root directories for file operations
    # (comma-separated as list items in .env: ALLOWED_ROOTS=["path1","path2"])
    # in other formats pydantic validator will complain
    ALLOWED_ROOTS: list[Path] = Field(default_factory=list)
    ALLOW_CWD: bool = Field(
        default=False, description="Allow access to current working directory if no roots specified"
    )
    # DOWNLOAD_DIR: str = "./for_download"

    # RECURSIVE: bool = Field(
    #     default=True,
    #     description="Allow access to subdirectories within roots (default: True)"
    # )

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    @field_validator("ADMIN_GITHUB_IDS", mode="before")
    @classmethod
    def parse_admin_ids(cls, v) -> list[str]:
        """Parse comma-separated admin IDs from environment variable."""
        if isinstance(v, str):
            # split by comma and strip whitespace
            return [id.strip() for id in v.split(",") if id.strip()]
        elif isinstance(v, list):
            return v
        return []

    @field_validator("ALLOWED_ROOTS", mode="before")
    @classmethod
    def parse_allowed_roots(cls, v) -> list[Path]:
        """Parse comma-separated paths from environment variable."""
        if isinstance(v, str):
            return [Path(p.strip()) for p in v.split(",") if p.strip()]
        elif isinstance(v, list):
            return [Path(p) if not isinstance(p, Path) else p for p in v]
        return []


settings = Settings()
