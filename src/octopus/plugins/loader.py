"""Plugin loader — discover and load plugins from directories."""

from __future__ import annotations

import importlib
import json
import logging
from pathlib import Path
from typing import Any

import yaml

from octopus.plugins.schemas import PluginManifest

logger = logging.getLogger(__name__)

# Plugin search directories
PLUGIN_DIRS = [
    Path.home() / ".octopus" / "plugins",
    Path.cwd() / ".octopus" / "plugins",
]


def discover_plugins(
    extra_dirs: list[Path] | None = None,
) -> list[tuple[Path, PluginManifest]]:
    """Discover plugins in standard directories.

    Returns a list of (plugin_dir, manifest) tuples.
    """
    dirs = PLUGIN_DIRS + (extra_dirs or [])
    found: list[tuple[Path, PluginManifest]] = []

    for search_dir in dirs:
        if not search_dir.exists():
            continue

        for plugin_dir in sorted(search_dir.iterdir()):
            if not plugin_dir.is_dir():
                continue

            manifest = _load_manifest(plugin_dir)
            if manifest:
                found.append((plugin_dir, manifest))
                logger.info(
                    "Discovered plugin: %s v%s", manifest.name, manifest.version
                )

    return found


def _load_manifest(plugin_dir: Path) -> PluginManifest | None:
    """Load a plugin manifest from a directory."""
    # Try plugin.json first, then plugin.yaml
    for filename in ("plugin.json", "plugin.yaml", "plugin.yml"):
        manifest_path = plugin_dir / filename
        if manifest_path.exists():
            try:
                content = manifest_path.read_text(encoding="utf-8")
                if filename.endswith(".json"):
                    data = json.loads(content)
                else:
                    data = yaml.safe_load(content) or {}
                return PluginManifest(**data)
            except Exception as e:
                logger.warning("Failed to load manifest from %s: %s", manifest_path, e)
                return None

    return None


def load_plugin_module(module_path: str, plugin_dir: Path) -> Any:
    """Load a Python module from a plugin directory.

    Args:
        module_path: Dotted module path relative to the plugin directory
                     (e.g., "tools.my_tool" or "hooks.my_hook")
        plugin_dir: The plugin's root directory

    Returns:
        The loaded module
    """
    # Add plugin dir to sys.path temporarily
    import sys

    plugin_dir_str = str(plugin_dir)
    if plugin_dir_str not in sys.path:
        sys.path.insert(0, plugin_dir_str)

    try:
        return importlib.import_module(module_path)
    finally:
        if plugin_dir_str in sys.path:
            sys.path.remove(plugin_dir_str)
