"""File state cache -- LRU cache of file contents with mtime-based invalidation.

Prevents re-reading unchanged files during a session. Used by filesystem
tools to avoid redundant disk I/O and for dedup in compaction (files
already in context don't need re-reading).
"""

from __future__ import annotations

import hashlib
import os
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class CachedFile:
    """A cached file entry."""

    path: str
    content: str
    mtime: float
    size: int
    content_hash: str


class FileStateCache:
    """LRU cache of file contents read during a session.

    Uses file modification time (mtime) and size for invalidation.
    Entries are evicted in LRU order when the cache exceeds max_size.

    Usage:
        cache = FileStateCache(max_size=200)
        cached = cache.get("/path/to/file.py")
        if cached is None:
            content = Path("/path/to/file.py").read_text()
            cache.put("/path/to/file.py", content)
        else:
            content = cached.content
    """

    def __init__(self, max_size: int = 200) -> None:
        self._cache: OrderedDict[str, CachedFile] = OrderedDict()
        self._max_size = max_size
        self._hits = 0
        self._misses = 0

    def get(self, path: str) -> CachedFile | None:
        """Get cached file if still valid (exists and mtime unchanged).

        Returns None if the file is not cached, has been modified since
        caching, or has been deleted.
        """
        abs_path = str(Path(path).resolve())

        cached = self._cache.get(abs_path)
        if cached is None:
            self._misses += 1
            return None

        # Check if file has changed on disk
        try:
            stat = os.stat(abs_path)
        except OSError:
            # File deleted -- evict from cache
            self._cache.pop(abs_path, None)
            self._misses += 1
            return None

        if stat.st_mtime != cached.mtime or stat.st_size != cached.size:
            # File changed -- evict stale entry
            self._cache.pop(abs_path, None)
            self._misses += 1
            return None

        # Cache hit -- move to end (most recently used)
        self._cache.move_to_end(abs_path)
        self._hits += 1
        return cached

    def put(self, path: str, content: str) -> CachedFile:
        """Cache a file's content.

        Reads mtime and size from disk for future invalidation checks.
        If the file doesn't exist on disk, mtime is set to 0 and size
        to the content length.
        """
        abs_path = str(Path(path).resolve())

        try:
            stat = os.stat(abs_path)
            mtime = stat.st_mtime
            size = stat.st_size
        except OSError:
            mtime = 0.0
            size = len(content)

        content_hash = hashlib.sha256(content.encode()).hexdigest()[:16]

        entry = CachedFile(
            path=abs_path,
            content=content,
            mtime=mtime,
            size=size,
            content_hash=content_hash,
        )

        self._cache[abs_path] = entry
        self._cache.move_to_end(abs_path)

        # Evict oldest entries if over capacity
        while len(self._cache) > self._max_size:
            self._cache.popitem(last=False)

        return entry

    def invalidate(self, path: str) -> None:
        """Remove a specific file from the cache."""
        abs_path = str(Path(path).resolve())
        self._cache.pop(abs_path, None)

    def clear(self) -> None:
        """Clear the entire cache and reset statistics."""
        self._cache.clear()
        self._hits = 0
        self._misses = 0

    @property
    def size(self) -> int:
        """Current number of entries in the cache."""
        return len(self._cache)

    @property
    def stats(self) -> dict[str, Any]:
        """Cache statistics including hit rate."""
        total = self._hits + self._misses
        return {
            "size": len(self._cache),
            "max_size": self._max_size,
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": self._hits / total if total > 0 else 0.0,
        }
