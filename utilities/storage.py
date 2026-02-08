import json
import logging
import os
from typing import Any, Optional
from abc import ABC, abstractmethod
from pathlib import Path

try:
    import redis.asyncio as redis
except ImportError:
    redis = None

from cryptography.fernet import Fernet

logger = logging.getLogger("fastmcp.storage")

class KeyValueStore(ABC):
    """Abstract base class for Key-Value storage complying with FastMCP interface."""
    
    @abstractmethod
    async def get(self, key: str, collection: Optional[str] = None) -> Any:
        pass

    @abstractmethod
    async def put(self, key: str, value: Any, collection: Optional[str] = None, ttl: Optional[int] = None) -> None:
        pass

    @abstractmethod
    async def delete(self, key: str, collection: Optional[str] = None) -> None:
        pass

class RedisStore(KeyValueStore):
    def __init__(self, host: str = "localhost", port: int = 6379, db: int = 0, password: str = None):
        if redis is None:
            raise ImportError("Redis library is not installed. Run 'pip install redis'")
        
        self.redis = redis.Redis(
            host=host, 
            port=port, 
            db=db, 
            password=password, 
            decode_responses=True 
        )

    def _make_key(self, key: str, collection: Optional[str]) -> str:
        return f"{collection}:{key}" if collection else key

    async def get(self, key: str, collection: Optional[str] = None) -> Optional[str]:
        try:
            return await self.redis.get(self._make_key(key, collection))
        except Exception as e:
            logger.error(f"Redis read error: {e}")
            return None

    async def put(self, key: str, value: str, collection: Optional[str] = None, ttl: Optional[int] = None) -> None:
        try:
            # ex=ttl встановлює час життя ключа в секундах
            await self.redis.set(self._make_key(key, collection), value, ex=ttl)
        except Exception as e:
            logger.error(f"Redis write error: {e}")

    async def delete(self, key: str, collection: Optional[str] = None) -> None:
        try:
            await self.redis.delete(self._make_key(key, collection))
        except Exception as e:
            logger.error(f"Redis delete error: {e}")

class DiskStore(KeyValueStore):
    def __init__(self, file_path: str = "mcp_storage.json"):
        self.file_path = file_path

    async def _load(self) -> dict:
        try:
            if not os.path.exists(self.file_path):
                return {}
            with open(self.file_path, "r") as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return {}

    async def _save(self, data: dict):
        try:
            with open(self.file_path, "w") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.error(f"Disk save error: {e}")

    async def get(self, key: str, collection: Optional[str] = None) -> Any:
        data = await self._load()
        coll = collection or "default"
        return data.get(coll, {}).get(key)

    async def put(self, key: str, value: Any, collection: Optional[str] = None, ttl: Optional[int] = None) -> None:
        data = await self._load()
        coll = collection or "default"
        if coll not in data:
            data[coll] = {}
        data[coll][key] = value
        await self._save(data)

    async def delete(self, key: str, collection: Optional[str] = None) -> None:
        data = await self._load()
        coll = collection or "default"
        if coll in data and key in data[coll]:
            del data[coll][key]
            await self._save(data)

class FernetEncryptionWrapper(KeyValueStore):
    def __init__(self, store: KeyValueStore, fernet_key: str | bytes):
        self.store = store
        if isinstance(fernet_key, str):
            fernet_key = fernet_key.encode()
        self.fernet = Fernet(fernet_key)

    async def get(self, key: str, collection: Optional[str] = None) -> Any:
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
            logger.error(f"Decryption failed for key {key}: {e}")
            return None

    async def put(self, key: str, value: Any, collection: Optional[str] = None, ttl: Optional[int] = None) -> None:
        try:
            if isinstance(value, dict):
                value = json.dumps(value)
            
            # Якщо value це число або щось інше, перетворюємо в рядок
            if not isinstance(value, str):
                 value = str(value)

            encrypted = self.fernet.encrypt(value.encode()).decode()
            
            await self.store.put(key, encrypted, collection=collection, ttl=ttl)
        except Exception as e:
            logger.error(f"Encryption failed for key {key}: {e}")
            raise e

    async def delete(self, key: str, collection: Optional[str] = None) -> None:
        await self.store.delete(key, collection=collection)