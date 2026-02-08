import secrets
from utilities.dependencies import logger 
from typing import Optional
from pathlib import Path
from fastmcp.server.auth.providers.github import GitHubProvider

# these imports down here are in plans to be implemented.
# Redis Store for KeyValueStore interface from redis client and cryptography packets are needed
# Same for Disk Storage, etc
from utilities.storage import (
    RedisStore,
    MemoryStore,
    DiskStore,
    FernetEncryptionWrapper,
)

from cryptography.fernet import Fernet
from config import settings


def get_auth_provider() -> Optional[GitHubProvider]:
    """
    Returns the Auth Provider based on available configuration.
    There is callback with MemoryStore if no keys or wrong keys identified
    """

    if not settings.AUTH_ENABLED:
        logger.warning("🚫 Authentication DISABLED.")
        return None

    if not settings.FASTMCP_SERVER_AUTH_GITHUB_CLIENT_ID:
        logger.error("❌ Auth enabled but Client ID missing via .env or CLI.")
        return None

    # checking for keys to decide on storage type (persistent or in-memory)
    has_keys = settings.JWT_SIGNING_KEY and settings.STORAGE_ENCRYPTION_KEY
    should_persist = settings.USE_PERSISTENT_STORAGE

    client_storage = None
    jwt_key = None

    if has_keys and should_persist:
        # production( with encryption and persistence) ===
        logger.info("🔒 Using PERSISTENT storage (Encrypted).")

        jwt_key = settings.JWT_SIGNING_KEY
        fernet_key = Fernet(settings.STORAGE_ENCRYPTION_KEY)

        # (Redis or Disk)
        if settings.USE_REDIS:
            try:
                logger.info(f"💾 Connecting to Redis at {settings.REDIS_HOST}...")
                backend = RedisStore(host=settings.REDIS_HOST, port=settings.REDIS_PORT)
            except Exception as e:
                logger.error(f"❌ Redis failed: {e}. Fallback to Disk.")
                backend = DiskStore(".fastmcp_storage")
        else:
            # Local Disk
            Path(".fastmcp_storage").mkdir(exist_ok=True)
            backend = DiskStore(".fastmcp_storage")

        # encrypting
        client_storage = FernetEncryptionWrapper(backend, fernet_key)

    else:
        # for dev/demo or quick usage ===
        logger.warning("⚠️  Running in EPHEMERAL mode (In-Memory).")
        logger.warning("   -> Logins will be lost on server restart.")
        if not has_keys:
            logger.info("   -> Reason: Encryption keys not found in .env")

        # temporary key that lives only in memory
        # (not saved anywhere, so it will be different on each restart)
        jwt_key = secrets.token_urlsafe(32)

        # using in-memory storage( no point in encrypting therefore)
        client_storage = MemoryStore()

    return GitHubProvider(
        client_id=settings.FASTMCP_SERVER_AUTH_GITHUB_CLIENT_ID,
        client_secret=settings.FASTMCP_SERVER_AUTH_GITHUB_CLIENT_SECRET,
        base_url=settings.FASTMCP_SERVER_AUTH_GITHUB_BASE_URL,
        jwt_signing_key=jwt_key,  # either from config or generated on-fly
        client_storage=client_storage,  # either encrypted(Redis/Disk), or Memory
    )
