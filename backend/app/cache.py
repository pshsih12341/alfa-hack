"""Кэш. Сейчас in-memory, в stage 2 — Redis."""

import time
from typing import Protocol


class CacheBackend(Protocol):
    def get(self, key: str) -> str | None: ...
    def set(self, key: str, value: str, ttl: int | None = None) -> None: ...
    def delete(self, key: str) -> None: ...


class InMemoryCache:
    def __init__(self) -> None:
        self._data: dict[str, tuple[str, float | None]] = {}

    def get(self, key: str) -> str | None:
        item = self._data.get(key)
        if item is None:
            return None
        value, expires_at = item
        if expires_at is not None and expires_at < time.time():
            del self._data[key]
            return None
        return value

    def set(self, key: str, value: str, ttl: int | None = None) -> None:
        expires_at = time.time() + ttl if ttl else None
        self._data[key] = (value, expires_at)

    def delete(self, key: str) -> None:
        self._data.pop(key, None)


# stage 2: class RedisCache: ... (redis-py, NotImplementedError сейчас)