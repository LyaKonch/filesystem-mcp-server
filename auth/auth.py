import logging
import secrets
from pathlib import Path
from typing import Any

from fastmcp.server.auth.providers.github import GitHubProvider

from config import settings

# these imports down here are in plans to be implemented.
# Redis Store for KeyValueStore interface from redis client and cryptography packets are needed
# Same for Disk Storage, etc
from utilities.storage import (
    DiskStore,
    FernetEncryptionWrapper,
    RedisStore,
)

module_logger = logging.getLogger(__name__)


def get_auth_provider() -> GitHubProvider | None:
    """
    Returns the Auth Provider based on available configuration.
    There is callback with MemoryStore if no keys or wrong keys identified
    """

    if not settings.AUTH_ENABLED:
        module_logger.warning("🚫 Authentication DISABLED.")
        module_logger.warning("   All users have FULL ACCESS to all tools!")
        module_logger.warning("   Remove --no-auth flag to enable authentication.")
        return None

    if not settings.FASTMCP_SERVER_AUTH_GITHUB_CLIENT_ID:
        module_logger.error("❌ Auth enabled but Client ID missing via .env or CLI.")
        return None

    if settings.POLICY_CONFIG_PATH:
        module_logger.info(f"Policy config found at {settings.POLICY_CONFIG_PATH}")
    else:
        module_logger.warning(
            "Policy config not found, using default with 'guest' role and no permissions."
        )

    # checking for keys to decide on storage type (persistent or in-memory)
    #  and
    has_keys = settings.STORAGE_ENCRYPTION_KEY is not None
    should_persist = settings.USE_PERSISTENT_STORAGE
    jwt_key = secrets.token_urlsafe(32)
    client_storage: Any = None

    if has_keys and should_persist:
        # production( with encryption and persistence) ===
        module_logger.info("🔒 Using PERSISTENT storage (Encrypted).")

        jwt_key = settings.JWT_SIGNING_KEY or secrets.token_urlsafe(32)

        # (Redis or Disk)
        backend: RedisStore | DiskStore
        if settings.USE_REDIS:
            try:
                module_logger.info(f"💾 Connecting to Redis at {settings.REDIS_HOST}...")
                backend = RedisStore(host=settings.REDIS_HOST, port=settings.REDIS_PORT)
            except Exception as e:
                module_logger.error(f"❌ Redis failed: {e}. Fallback to Disk.")
                backend = DiskStore(".fastmcp_storage")
        else:
            # Local Disk
            storage_path = Path(".fastmcp_storage")
            storage_path.mkdir(exist_ok=True)

            backend = DiskStore(str(storage_path / "storage.json"))

        # encrypting
        if settings.STORAGE_ENCRYPTION_KEY is None:
            module_logger.error("Missing STORAGE_ENCRYPTION_KEY while persistence is enabled")
            return None
        client_storage = FernetEncryptionWrapper(backend, settings.STORAGE_ENCRYPTION_KEY)

    else:
        # for dev/demo or quick usage ===
        module_logger.warning("⚠️  Running in EPHEMERAL mode (In-Memory).")
        module_logger.warning("   -> Logins will be lost on server restart.")
        if not has_keys:
            module_logger.info("   -> Reason: Encryption keys not found in .env")

        # using in-memory storage( no point in encrypting therefore)
        client_storage = None

    provider_kwargs: dict[str, Any] = {
        "client_id": settings.FASTMCP_SERVER_AUTH_GITHUB_CLIENT_ID,
        "jwt_signing_key": jwt_key,
        "client_storage": client_storage,
    }
    if settings.FASTMCP_SERVER_AUTH_GITHUB_CLIENT_SECRET is not None:
        provider_kwargs["client_secret"] = settings.FASTMCP_SERVER_AUTH_GITHUB_CLIENT_SECRET
    if settings.FASTMCP_SERVER_AUTH_GITHUB_BASE_URL is not None:
        provider_kwargs["base_url"] = settings.FASTMCP_SERVER_AUTH_GITHUB_BASE_URL

    return GitHubProvider(**provider_kwargs)
