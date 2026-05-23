import json
import os
import asyncio
import logging

logger = logging.getLogger(__name__)

# Root of the python-sidecar package (one level above utils/)
_SIDECAR_ROOT = os.path.dirname(os.path.dirname(__file__))


class DiskCache:
    """
    Lightweight persistent JSON key-value cache stored at the sidecar root.

    Usage:
        cache = DiskCache("search_cache.json")
        result = cache.get(key)
        if result is None:
            result = expensive_call()
            cache.set(key, result)

    Thread / async safety: individual get/set calls are synchronous and GIL-
    protected for the dict mutation; the JSON write is a single atomic open().
    This is sufficient for single-process asyncio usage.
    """

    def __init__(self, filename: str):
        self._path = os.path.join(_SIDECAR_ROOT, filename)
        self._store: dict = {}
        self._load()

    def _load(self) -> None:
        if not os.path.exists(self._path):
            return
        try:
            with open(self._path, "r") as f:
                self._store = json.load(f)
            logger.debug(f"DiskCache loaded {len(self._store)} entries from {self._path}")
        except Exception as e:
            logger.error(f"DiskCache failed to load {self._path}: {e}")
            self._store = {}

    async def _save(self) -> None:
        try:
            data = json.dumps(self._store, indent=2)
            await asyncio.to_thread(self._write_file, data)
        except Exception as e:
            logger.error(f"DiskCache failed to save {self._path}: {e}")

    def _write_file(self, data: str) -> None:
        with open(self._path, "w") as f:
            f.write(data)

    def get(self, key: str):
        """Return cached value or None if not present."""
        return self._store.get(key)

    async def set(self, key: str, value) -> None:
        """Store a value and immediately persist to disk."""
        self._store[key] = value
        await self._save()

    def __contains__(self, key: str) -> bool:
        return key in self._store

    def __len__(self) -> int:
        return len(self._store)
