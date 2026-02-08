import json
import logging
from typing import Any, Optional
from abc import ABC, abstractmethod

import redis.asyncio as redis
from cryptography.fernet import Fernet

logger = logging.getLogger("fastmcp.storage")

# base class for storage backends
class KeyValueStore(ABC):
    """Abstract base class for Key-Value storage."""
    
    @abstractmethod
    async def read(self, key: str) -> Optional[str]:
        pass

    @abstractmethod
    async def write(self, key: str, value: str) -> None:
        pass

class RedisStore(KeyValueStore):
    """Storage implementation using Redis."""
    
    def __init__(self, host: str = "localhost", port: int = 6379, db: int = 0, password: str = None):
        self.redis = redis.Redis(
            host=host, 
            port=port, 
            db=db, 
            password=password, 
            decode_responses=True 
        )

    async def read(self, key: str) -> Optional[str]:
        try:
            return await self.redis.get(key)
        except Exception as e:
            logger.error(f"Redis read error: {e}")
            return None

    async def write(self, key: str, value: str) -> None:
        try:
            await self.redis.set(key, value)
        except Exception as e:
            logger.error(f"Redis write error: {e}")

class MemoryStore(KeyValueStore):
    """Ephemeral in-memory storage (for dev/demo)."""
    
    def __init__(self):
        self._store: dict[str, str] = {}

    async def read(self, key: str) -> Optional[str]:
        return self._store.get(key)

    async def write(self, key: str, value: str) -> None:
        self._store[key] = value

class DiskStore(KeyValueStore):
    """Simple JSON file storage."""
    
    def __init__(self, file_path: str = "mcp_storage.json"):
        self.file_path = file_path

    async def _load(self) -> dict:
        try:
            with open(self.file_path, "r") as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return {}

    async def _save(self, data: dict):
        with open(self.file_path, "w") as f:
            json.dump(data, f)

    async def read(self, key: str) -> Optional[str]:
        data = await self._load()
        return data.get(key)

    async def write(self, key: str, value: str) -> None:
        data = await self._load()
        data[key] = value
        await self._save(data)

# using Fernet symmetric encryption
class FernetEncryptionWrapper(KeyValueStore):
    """Decorator that encrypts values before saving to the underlying store."""
    
    def __init__(self, store: KeyValueStore, fernet_key: str | bytes):
        self.store = store
        # converted to bytes
        if isinstance(fernet_key, str):
            fernet_key = fernet_key.encode()
        self.fernet = Fernet(fernet_key)

    async def read(self, key: str) -> Optional[str]:
        encrypted_value = await self.store.read(key)
        if not encrypted_value:
            return None
        try:
            # Decrypt
            decrypted = self.fernet.decrypt(encrypted_value.encode()).decode()
            return decrypted
        except Exception as e:
            logger.error(f"Decryption failed for key {key}: {e}")
            return None

    async def write(self, key: str, value: str) -> None:
        try:
            # Encrypt
            encrypted = self.fernet.encrypt(value.encode()).decode()
            await self.store.write(key, encrypted)
        except Exception as e:
            logger.error(f"Encryption failed for key {key}: {e}")