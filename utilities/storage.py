"""Storage abstractions and implementations for auth/session persistence."""

import json
import logging
import os
from abc import ABC, abstractmethod
from typing import Any

from cryptography.fernet import Fernet

redis_async: Any | None

try:
    import redis.asyncio as _redis_async

    redis_async = _redis_async
except ImportError:
    redis_async = None


logger = logging.getLogger("fastmcp.storage")


class KeyValueStore(ABC):
    """Abstract base class for Key-Value storage complying with FastMCP interface."""

    @abstractmethod
    async def get(self, key: str, collection: str | None = None) -> Any:
        """Fetch value by key and optional collection.

        Args:
            key: Storage key.
            collection: Optional namespace.

        Returns:
            Any: Stored value or ``None``.
        """
        pass

    @abstractmethod
    async def put(
        self, key: str, value: Any, collection: str | None = None, ttl: int | None = None
    ) -> None:
        """Store value by key and optional collection.

        Args:
            key: Storage key.
            value: Value to persist.
            collection: Optional namespace.
            ttl: Optional TTL in seconds.
        """
        pass

    @abstractmethod
    async def delete(self, key: str, collection: str | None = None) -> None:
        """Delete value by key and optional collection.

        Args:
            key: Storage key.
            collection: Optional namespace.
        """
        pass


class RedisStore(KeyValueStore):
    """Redis-backed ``KeyValueStore`` implementation."""

    def __init__(
        self,
        host: str = "localhost",
        port: int = 6379,
        db: int = 0,
        password: str | None = None,
    ):
        """Initialize Redis-backed store client."""
        if redis_async is None:
            raise ImportError("Redis library is not installed. Run 'pip install redis'")

        self.redis = redis_async.Redis(
            host=host, port=port, db=db, password=password, decode_responses=True
        )

    def _make_key(self, key: str, collection: str | None) -> str:
        return f"{collection}:{key}" if collection else key

    async def get(self, key: str, collection: str | None = None) -> str | None:
        """Get value from Redis by key and optional collection."""
        try:
            return await self.redis.get(self._make_key(key, collection))
        except Exception as e:
            logger.error("Redis read error: %s", e)
            return None

    async def put(
        self, key: str, value: str, collection: str | None = None, ttl: int | None = None
    ) -> None:
        """Store value in Redis with optional TTL."""
        try:
            # ex=ttl встановлює час життя ключа в секундах
            await self.redis.set(self._make_key(key, collection), value, ex=ttl)
        except Exception as e:
            logger.error("Redis write error: %s", e)

    async def delete(self, key: str, collection: str | None = None) -> None:
        """Delete value from Redis by key and optional collection."""
        try:
            await self.redis.delete(self._make_key(key, collection))
        except Exception as e:
            logger.error("Redis delete error: %s", e)


class DiskStore(KeyValueStore):
    """Disk-backed JSON ``KeyValueStore`` implementation."""

    def __init__(self, file_path: str = "mcp_storage.json"):
        """Initialize disk store using JSON file path."""
        self.file_path = file_path

    async def _load(self) -> dict:
        try:
            if not os.path.exists(self.file_path):
                return {}
            with open(self.file_path) as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return {}

    async def _save(self, data: dict):
        try:
            with open(self.file_path, "w") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.error("Disk save error: %s", e)

    async def get(self, key: str, collection: str | None = None) -> Any:
        """Get value from JSON-backed store."""
        data = await self._load()
        coll = collection or "default"
        return data.get(coll, {}).get(key)

    async def put(
        self, key: str, value: Any, collection: str | None = None, ttl: int | None = None
    ) -> None:
        """Store value in JSON-backed store."""
        data = await self._load()
        coll = collection or "default"
        if coll not in data:
            data[coll] = {}
        data[coll][key] = value
        await self._save(data)

    async def delete(self, key: str, collection: str | None = None) -> None:
        """Delete value from JSON-backed store."""
        data = await self._load()
        coll = collection or "default"
        if coll in data and key in data[coll]:
            del data[coll][key]
            await self._save(data)


class FernetEncryptionWrapper(KeyValueStore):
    """Encrypted wrapper over another ``KeyValueStore`` backend."""

    def __init__(self, store: KeyValueStore, fernet_key: str | bytes):
        """Initialize encrypted wrapper over underlying key-value store."""
        self.store = store
        if isinstance(fernet_key, str):
            fernet_key = fernet_key.encode()
        self.fernet = Fernet(fernet_key)

    async def get(self, key: str, collection: str | None = None) -> Any:
        """Read encrypted value and return decrypted payload."""
        encrypted_value = await self.store.get(key, collection=collection)
        if not encrypted_value:
            return None
        try:
            decrypted = self.fernet.decrypt(encrypted_value.encode()).decode()

            try:
                return json.loads(decrypted)
            except json.JSONDecodeError:
                return decrypted

        except Exception as e:
            logger.error("Decryption failed for key %s: %s", key, e)
            return None

    async def put(
        self, key: str, value: Any, collection: str | None = None, ttl: int | None = None
    ) -> None:
        """Encrypt and store value in underlying backend."""
        try:
            if isinstance(value, dict):
                value = json.dumps(value)

            # Якщо value це число або щось інше, перетворюємо в рядок
            if not isinstance(value, str):
                value = str(value)

            encrypted = self.fernet.encrypt(value.encode()).decode()

            await self.store.put(key, encrypted, collection=collection, ttl=ttl)
        except Exception as e:
            logger.error("Encryption failed for key %s: %s", key, e)
            raise e

    async def delete(self, key: str, collection: str | None = None) -> None:
        """Delete value from underlying backend."""
        await self.store.delete(key, collection=collection)
