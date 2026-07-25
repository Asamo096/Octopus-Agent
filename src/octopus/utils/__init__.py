"""Octopus Agent Utilities -- file operations, logging, platform detection."""

from .file_cache import CachedFile, FileStateCache
from .files import atomic_write, file_lock
from .platform import get_platform, is_linux, is_macos, is_windows

__all__ = [
    "atomic_write",
    "file_lock",
    "get_platform",
    "is_windows",
    "is_macos",
    "is_linux",
    "CachedFile",
    "FileStateCache",
]
