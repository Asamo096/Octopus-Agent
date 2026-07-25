"""Plugin manager — lifecycle management for plugins."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from octopus.plugins.loader import discover_plugins, load_plugin_module
from octopus.plugins.schemas import PluginManifest

logger = logging.getLogger(__name__)


class PluginInfo:
    """Information about a loaded plugin."""

    def __init__(self, directory: Path, manifest: PluginManifest) -> None:
        self.directory = directory
        self.manifest = manifest
        self.enabled = True
        self.loaded_tools: list[Any] = []
        self.loaded_hooks: list[Any] = []


class PluginManager:
    """Manage plugin lifecycle: discover, load, enable, disable."""

    def __init__(self) -> None:
        self._plugins: dict[str, PluginInfo] = {}

    def discover(self, extra_dirs: list[Path] | None = None) -> list[PluginManifest]:
        """Discover plugins and register them."""
        found = discover_plugins(extra_dirs)
        manifests: list[PluginManifest] = []

        for directory, manifest in found:
            if manifest.name in self._plugins:
                logger.warning("Duplicate plugin: %s", manifest.name)
                continue

            self._plugins[manifest.name] = PluginInfo(directory, manifest)
            manifests.append(manifest)

        return manifests

    def load_tools(
        self,
        registry: Any,
        kernel: Any,
        extra_dirs: list[Path] | None = None,
    ) -> int:
        """Load tool classes from all enabled plugins.

        Returns the number of tools loaded.
        """
        count = 0
        for name, info in self._plugins.items():
            if not info.enabled:
                continue

            for tool_module_path in info.manifest.tools:
                try:
                    module = load_plugin_module(tool_module_path, info.directory)
                    # Look for a register function or tool classes
                    if hasattr(module, "register"):
                        module.register(registry, kernel)
                        count += 1
                        logger.info(
                            "Loaded tool from plugin %s: %s", name, tool_module_path
                        )
                    else:
                        # Try to find Tool classes
                        for attr_name in dir(module):
                            attr = getattr(module, attr_name)
                            if (
                                hasattr(attr, "name")
                                and hasattr(attr, "execute")
                                and hasattr(attr, "input_schema")
                            ):
                                tool_instance = (
                                    attr() if isinstance(attr, type) else attr
                                )
                                registry.register(tool_instance)
                                kernel.register_tool(tool_instance)
                                info.loaded_tools.append(tool_instance)
                                count += 1
                                logger.info(
                                    "Loaded tool %s from plugin %s",
                                    tool_instance.name,
                                    name,
                                )
                except Exception as e:
                    logger.error(
                        "Failed to load tool %s from plugin %s: %s",
                        tool_module_path,
                        name,
                        e,
                    )

        return count

    def load_hooks(
        self,
        hook_manager: Any,
        extra_dirs: list[Path] | None = None,
    ) -> int:
        """Load hooks from all enabled plugins.

        Returns the number of hooks loaded.
        """
        from octopus.core.hooks import Hook, HookEvent

        count = 0
        for name, info in self._plugins.items():
            if not info.enabled:
                continue

            for event_name, hook_paths in info.manifest.hooks.items():
                try:
                    event = HookEvent(event_name)
                except ValueError:
                    logger.warning(
                        "Unknown hook event %s in plugin %s", event_name, name
                    )
                    continue

                for hook_path in hook_paths:
                    # Format: "module:function"
                    if ":" in hook_path:
                        module_path, func_name = hook_path.rsplit(":", 1)
                    else:
                        module_path, func_name = hook_path, "hook"

                    try:
                        module = load_plugin_module(module_path, info.directory)
                        func = getattr(module, func_name, None)
                        if func is None:
                            logger.warning(
                                "Function %s not found in %s", func_name, module_path
                            )
                            continue

                        hook = Hook(f"{name}:{func_name}", func)
                        hook_manager.register(event, hook)
                        info.loaded_hooks.append(hook)
                        count += 1
                        logger.info(
                            "Loaded hook %s:%s for %s", name, func_name, event_name
                        )
                    except Exception as e:
                        logger.error(
                            "Failed to load hook %s from plugin %s: %s",
                            hook_path,
                            name,
                            e,
                        )

        return count

    def enable(self, name: str) -> bool:
        """Enable a plugin."""
        if name in self._plugins:
            self._plugins[name].enabled = True
            return True
        return False

    def disable(self, name: str) -> bool:
        """Disable a plugin."""
        if name in self._plugins:
            self._plugins[name].enabled = False
            return True
        return False

    def list_plugins(self) -> list[dict[str, Any]]:
        """List all discovered plugins."""
        return [
            {
                "name": info.manifest.name,
                "version": info.manifest.version,
                "description": info.manifest.description,
                "enabled": info.enabled,
                "tools": info.manifest.tools,
                "hooks": list(info.manifest.hooks.keys()),
            }
            for info in self._plugins.values()
        ]

    def get_plugin(self, name: str) -> PluginInfo | None:
        """Get a plugin by name."""
        return self._plugins.get(name)
