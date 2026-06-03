import logging
from abc import ABC, abstractmethod
from collections.abc import Mapping, Sequence
from typing import Any, SupportsFloat

from key_value.aio.protocols.key_value import AsyncKeyValue

from utilities.error_handling import ToolOperationError

logger = logging.getLogger("fastmcp.storage")


class KeyValueStore(ABC):
    """Abstract base class for Key-Value storage complying with FastMCP interface."""

    @abstractmethod
    async def get(self, key: str, collection: str | None = None) -> Any:
        pass

    @abstractmethod
    async def put(
        self,
        key: str,
        value: Mapping[str, Any],
        collection: str | None = None,
        ttl: SupportsFloat | None = None,
    ) -> None:
        pass

    @abstractmethod
    async def delete(self, key: str, collection: str | None = None) -> None:
        pass


class LoggingStore(KeyValueStore):
    def __init__(self, store: AsyncKeyValue):
        self.store = store

    async def get(self, key: str, collection: str | None = None) -> Any:
        try:
            return await self.store.get(key, collection=collection)
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
        self,
        key: str,
        value: Mapping[str, Any],
        collection: str | None = None,
        ttl: SupportsFloat | None = None,
    ) -> None:
        try:
            await self.store.put(key, value, collection=collection, ttl=ttl)
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

    async def ttl(
        self, key: str, collection: str | None = None
    ) -> tuple[dict[str, Any] | None, float | None]:
        try:
            return await self.store.ttl(key, collection=collection)
        except ToolOperationError:
            raise
        except Exception as e:
            logger.error("Store ttl error: %s", e)
            raise ToolOperationError(
                "operation_failed",
                f"Failed to read TTL from storage: {e}",
                actions=[
                    "Verify the underlying storage is accessible.",
                    "Check storage configuration and permissions.",
                    "Retry the operation.",
                ],
            ) from e

    async def delete(self, key: str, collection: str | None = None) -> None:
        try:
            await self.store.delete(key, collection=collection)
            return None
        except ToolOperationError:
            raise
        except Exception as e:
            logger.error("Store delete error: %s", e)
            raise ToolOperationError(
                "operation_failed",
                f"Failed to delete from storage: {e}",
                actions=[
                    "Verify the underlying storage is accessible.",
                    "Check storage configuration and permissions.",
                    "Retry the operation.",
                ],
            ) from e

    async def get_many(
        self, keys: Sequence[str], collection: str | None = None
    ) -> list[dict[str, Any] | None]:
        try:
            return await self.store.get_many(keys, collection=collection)
        except ToolOperationError:
            raise
        except Exception as e:
            logger.error("Store get_many error: %s", e)
            raise ToolOperationError(
                "operation_failed",
                f"Failed to read multiple values from storage: {e}",
                actions=[
                    "Verify the underlying storage is accessible.",
                    "Check storage configuration and permissions.",
                    "Retry the operation.",
                ],
            ) from e

    async def ttl_many(
        self, keys: Sequence[str], collection: str | None = None
    ) -> list[tuple[dict[str, Any] | None, float | None]]:
        try:
            return await self.store.ttl_many(keys, collection=collection)
        except ToolOperationError:
            raise
        except Exception as e:
            logger.error("Store ttl_many error: %s", e)
            raise ToolOperationError(
                "operation_failed",
                f"Failed to read multiple TTL values from storage: {e}",
                actions=[
                    "Verify the underlying storage is accessible.",
                    "Check storage configuration and permissions.",
                    "Retry the operation.",
                ],
            ) from e

    async def put_many(
        self,
        keys: Sequence[str],
        values: Sequence[Mapping[str, Any]],
        collection: str | None = None,
        ttl: SupportsFloat | None = None,
    ) -> None:
        try:
            await self.store.put_many(keys, values, collection=collection, ttl=ttl)
        except ToolOperationError:
            raise
        except Exception as e:
            logger.error("Store put_many error: %s", e)
            raise ToolOperationError(
                "operation_failed",
                f"Failed to store multiple values on storage: {e}",
                actions=[
                    "Verify the underlying storage is accessible.",
                    "Check storage configuration and permissions.",
                    "Retry the operation.",
                ],
            ) from e

    async def delete_many(self, keys: Sequence[str], collection: str | None = None) -> int:
        try:
            return await self.store.delete_many(keys, collection=collection)
        except ToolOperationError:
            raise
        except Exception as e:
            logger.error("Store delete_many error: %s", e)
            raise ToolOperationError(
                "operation_failed",
                f"Failed to delete multiple values from storage: {e}",
                actions=[
                    "Verify the underlying storage is accessible.",
                    "Check storage configuration and permissions.",
                    "Retry the operation.",
                ],
            ) from e


class LoggingRedisStore(LoggingStore):
    def __init__(self, store: AsyncKeyValue):
        super().__init__(store)


class LoggingDiskStore(LoggingStore):
    def __init__(self, store: AsyncKeyValue):
        super().__init__(store)
