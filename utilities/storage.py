import json
import logging
import os
from abc import ABC, abstractmethod
from typing import Any

from cryptography.fernet import Fernet

from utilities.error_handling import ToolOperationError

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
        pass

    @abstractmethod
    async def put(
        self, key: str, value: Any, collection: str | None = None, ttl: int | None = None
    ) -> None:
        pass

    @abstractmethod
    async def delete(self, key: str, collection: str | None = None) -> None:
        pass


class RedisStore(KeyValueStore):
    def __init__(
        self,
        host: str = "localhost",
        port: int = 6379,
        db: int = 0,
        password: str | None = None,
    ):
        if redis_async is None:
            raise ToolOperationError(
                "operation_failed",
                "Redis library is not installed. Run 'pip install redis'",
                actions=[
                    "Install the redis package: pip install redis",
                    "Or use DiskStore for local storage instead.",
                    "Retry after installing dependencies.",
                ],
            )

        self.redis = redis_async.Redis(
            host=host, port=port, db=db, password=password, decode_responses=True
        )

    def _make_key(self, key: str, collection: str | None) -> str:
        return f"{collection}:{key}" if collection else key

    async def get(self, key: str, collection: str | None = None) -> str | None:
        try:
            return await self.redis.get(self._make_key(key, collection))
        except ToolOperationError:
            raise
        except Exception as e:
            logger.error("Redis read error: %s", e)
            raise ToolOperationError(
                "operation_failed",
                f"Failed to read from Redis: {e}",
                actions=[
                    "Verify Redis server is running.",
                    "Check network connectivity to Redis.",
                    "Review Redis configuration.",
                    "Retry the operation.",
                ],
            ) from e

    async def put(
        self, key: str, value: str, collection: str | None = None, ttl: int | None = None
    ) -> None:
        try:
            # ex=ttl встановлює час життя ключа в секундах
            await self.redis.set(self._make_key(key, collection), value, ex=ttl)
        except ToolOperationError:
            raise
        except Exception as e:
            logger.error("Redis write error: %s", e)
            raise ToolOperationError(
                "operation_failed",
                f"Failed to write to Redis: {e}",
                actions=[
                    "Verify Redis server is running.",
                    "Check network connectivity to Redis.",
                    "Ensure sufficient disk space on Redis server.",
                    "Retry the operation.",
                ],
            ) from e

    async def delete(self, key: str, collection: str | None = None) -> None:
        try:
            await self.redis.delete(self._make_key(key, collection))
        except ToolOperationError:
            raise
        except Exception as e:
            logger.error("Redis delete error: %s", e)
            raise ToolOperationError(
                "operation_failed",
                f"Failed to delete from Redis: {e}",
                actions=[
                    "Verify Redis server is running.",
                    "Check network connectivity to Redis.",
                    "Review Redis configuration.",
                    "Retry the operation.",
                ],
            ) from e


class DiskStore(KeyValueStore):
    def __init__(self, file_path: str = "mcp_storage.json"):
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
        except ToolOperationError:
            raise
        except Exception as e:
            logger.error("Disk save error: %s", e)
            raise ToolOperationError(
                "operation_failed",
                f"Failed to save data to disk: {e}",
                actions=[
                    "Verify disk space is available.",
                    "Check file permissions.",
                    "Ensure the storage directory is writable.",
                    "Retry the operation.",
                ],
            ) from e

    async def get(self, key: str, collection: str | None = None) -> Any:
        try:
            data = await self._load()
            coll = collection or "default"
            return data.get(coll, {}).get(key)
        except ToolOperationError:
            raise
        except Exception as e:
            logger.error("Disk load error: %s", e)
            raise ToolOperationError(
                "operation_failed",
                f"Failed to read data from disk: {e}",
                actions=[
                    "Verify the storage file is accessible.",
                    "Check file permissions and format.",
                    "Ensure the storage directory exists.",
                    "Retry the operation.",
                ],
            ) from e

    async def put(
        self, key: str, value: Any, collection: str | None = None, ttl: int | None = None
    ) -> None:
        try:
            data = await self._load()
            coll = collection or "default"
            if coll not in data:
                data[coll] = {}
            data[coll][key] = value
            await self._save(data)
        except ToolOperationError:
            raise
        except Exception as e:
            logger.error("Disk store error: %s", e)
            raise ToolOperationError(
                "operation_failed",
                f"Failed to store data on disk: {e}",
                actions=[
                    "Verify disk space is available.",
                    "Check file permissions and format.",
                    "Ensure the storage directory is writable.",
                    "Retry the operation.",
                ],
            ) from e

    async def delete(self, key: str, collection: str | None = None) -> None:
        try:
            data = await self._load()
            coll = collection or "default"
            if coll in data and key in data[coll]:
                del data[coll][key]
                await self._save(data)
        except ToolOperationError:
            raise
        except Exception as e:
            logger.error("Disk delete error: %s", e)
            raise ToolOperationError(
                "operation_failed",
                f"Failed to delete data from disk: {e}",
                actions=[
                    "Verify the storage file is accessible.",
                    "Check file permissions and format.",
                    "Ensure the storage directory is writable.",
                    "Retry the operation.",
                ],
            ) from e


class FernetEncryptionWrapper(KeyValueStore):
    def __init__(self, store: KeyValueStore, fernet_key: str | bytes):
        self.store = store
        if isinstance(fernet_key, str):
            fernet_key = fernet_key.encode()
        self.fernet = Fernet(fernet_key)

    async def get(self, key: str, collection: str | None = None) -> Any:
        try:
            encrypted_value = await self.store.get(key, collection=collection)
            if not encrypted_value:
                return None
            try:
                decrypted = self.fernet.decrypt(encrypted_value.encode()).decode()
                try:
                    return json.loads(decrypted)
                except json.JSONDecodeError:
                    return decrypted
            except Exception as decrypt_error:
                logger.error("Decryption failed for key %s: %s", key, decrypt_error)
                raise ToolOperationError(
                    "operation_failed",
                    f"Failed to decrypt data for key '{key}'",
                    actions=[
                        "Verify the encryption key is correct.",
                        "Ensure the encrypted data has not been corrupted.",
                        "Check that the Fernet key matches the stored data.",
                        "Retry the operation.",
                    ],
                ) from decrypt_error
        except ToolOperationError:
            raise
        except Exception as e:
            logger.error("Store get error: %s", e)
            raise ToolOperationError(
                "operation_failed",
                f"Failed to retrieve encrypted data: {e}",
                actions=[
                    "Verify the underlying storage is accessible.",
                    "Check storage configuration and permissions.",
                    "Retry the operation.",
                ],
            ) from e

    async def put(
        self, key: str, value: Any, collection: str | None = None, ttl: int | None = None
    ) -> None:
        try:
            if isinstance(value, dict):
                value = json.dumps(value)

            # Якщо value це число або щось інше, перетворюємо в рядок
            if not isinstance(value, str):
                value = str(value)

            try:
                encrypted = self.fernet.encrypt(value.encode()).decode()
            except Exception as encrypt_error:
                logger.error("Encryption failed for key %s: %s", key, encrypt_error)
                raise ToolOperationError(
                    "operation_failed",
                    f"Failed to encrypt data for key '{key}'",
                    actions=[
                        "Verify the encryption key is valid.",
                        "Check that the Fernet key has not been modified.",
                        "Ensure the data can be serialized to string.",
                        "Retry the operation.",
                    ],
                ) from encrypt_error

            await self.store.put(key, encrypted, collection=collection, ttl=ttl)
        except ToolOperationError:
            raise
        except Exception as e:
            logger.error("Store put error: %s", e)
            raise ToolOperationError(
                "operation_failed",
                f"Failed to store encrypted data: {e}",
                actions=[
                    "Verify the underlying storage is accessible.",
                    "Check storage configuration and permissions.",
                    "Retry the operation.",
                ],
            ) from e

    async def delete(self, key: str, collection: str | None = None) -> None:
        try:
            await self.store.delete(key, collection=collection)
        except ToolOperationError:
            raise
        except Exception as e:
            logger.error("Store delete error: %s", e)
            raise ToolOperationError(
                "operation_failed",
                f"Failed to delete encrypted data: {e}",
                actions=[
                    "Verify the underlying storage is accessible.",
                    "Check storage configuration and permissions.",
                    "Retry the operation.",
                ],
            ) from e
