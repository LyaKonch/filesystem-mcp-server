from pathlib import Path
from typing import List, Optional
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field

class Settings(BaseSettings):
    # --- Server Configuration ---
    MCP_HOST: str = "127.0.0.1"
    MCP_PORT: int = 8000
    TRANSPORT: str = "sse"
    DEBUG: bool = False

    # --- Authentication (GitHub) ---
    # can be switched off, therefore Optional
    # it's recommended to set these authentication variables via env/(or even os) variables or CLI, not hardcoded
    AUTH_ENABLED: bool = True

    FASTMCP_SERVER_AUTH_GITHUB_CLIENT_ID: Optional[str] = None
    FASTMCP_SERVER_AUTH_GITHUB_CLIENT_SECRET: Optional[str] = None
    FASTMCP_SERVER_AUTH_GITHUB_BASE_URL: Optional[str] = None

    # --- Security & Storage ---
    USE_PERSISTENT_STORAGE: bool = False
    
    # turns out github jwt keys are opaque,so they verify them by calling GitHub's API
    JWT_SIGNING_KEY: Optional[str] = None
    STORAGE_ENCRYPTION_KEY: Optional[str] = None
    USE_REDIS: bool = False
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379

    # --- Filesystem Config ---
    ALLOWED_ROOTS: List[Path] = Field(default_factory=list)
    ALLOW_CWD: bool = Field(
        default=False,
        description="Allow access to current working directory if no roots specified"
    )
    DOWNLOAD_DIR: str = "./for_download"

    # RECURSIVE: bool = Field(
    #     default=True,
    #     description="Allow access to subdirectories within roots (default: True)"
    # )

    model_config = SettingsConfigDict(
        env_file=".env", 
        env_file_encoding="utf-8",
        extra="ignore"
    )
    
settings = Settings()    

