"""Thread-safe in-memory TTL/LRU cache for high-throughput operational state."""

from __future__ import annotations

import threading
import time
from collections import OrderedDict
from typing import Generic, TypeVar

K = TypeVar("K")
V = TypeVar("V")


class TTLCache(Generic[K, V]):
    """Thread-safe in-memory cache with TTL expiration and LRU capacity bounds."""

    def __init__(self, maxsize: int = 1000, default_ttl_seconds: float = 300.0) -> None:
        self.maxsize = maxsize
        self.default_ttl_seconds = default_ttl_seconds
        self._data: OrderedDict[K, tuple[V, float]] = OrderedDict()
        self._lock = threading.RLock()

    def get(self, key: K, default: V | None = None) -> V | None:
        """Retrieve key value if present and not expired; moves to end for LRU."""
        now = time.monotonic()
        with self._lock:
            if key not in self._data:
                return default
            val, expiry = self._data[key]
            if now > expiry:
                del self._data[key]
                return default
            self._data.move_to_end(key)
            return val

    def set(self, key: K, value: V, ttl_seconds: float | None = None) -> None:
        """Store key value with specific or default TTL; evicts LRU if maxsize reached."""
        ttl = self.default_ttl_seconds if ttl_seconds is None else ttl_seconds
        expiry = time.monotonic() + ttl
        with self._lock:
            if key in self._data:
                del self._data[key]
            elif len(self._data) >= self.maxsize:
                # Evict oldest entry
                self._data.popitem(last=False)
            self._data[key] = (value, expiry)

    def delete(self, key: K) -> bool:
        """Remove a key from cache if present."""
        with self._lock:
            if key in self._data:
                del self._data[key]
                return True
            return False

    def clear(self) -> None:
        """Clear all entries."""
        with self._lock:
            self._data.clear()

    def size(self) -> int:
        """Count non-expired entries."""
        now = time.monotonic()
        with self._lock:
            # Purge expired items
            expired = [k for k, (_, exp) in self._data.items() if now > exp]
            for k in expired:
                del self._data[k]
            return len(self._data)

    def __len__(self) -> int:
        return self.size()

    def __contains__(self, key: K) -> bool:
        return self.get(key) is not None

