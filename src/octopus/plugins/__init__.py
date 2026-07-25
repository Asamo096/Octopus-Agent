"""Octopus Agent Plugins — plugin discovery, loading, and management."""

from .loader import discover_plugins
from .manager import PluginInfo, PluginManager
from .schemas import PluginManifest

__all__ = [
    "PluginManager",
    "PluginInfo",
    "PluginManifest",
    "discover_plugins",
]
