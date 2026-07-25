"""Tests for octopus.plugins — PluginManager and loader."""

from __future__ import annotations

import json
from pathlib import Path

from octopus.plugins.loader import discover_plugins
from octopus.plugins.manager import PluginManager
from octopus.plugins.schemas import PluginManifest


class TestPluginManifest:
    def test_create(self) -> None:
        m = PluginManifest(name="test", version="1.0.0", description="A test plugin")
        assert m.name == "test"
        assert m.version == "1.0.0"
        assert m.tools == []
        assert m.hooks == {}

    def test_with_tools(self) -> None:
        m = PluginManifest(name="test", tools=["tools.my_tool"])
        assert m.tools == ["tools.my_tool"]

    def test_with_hooks(self) -> None:
        m = PluginManifest(name="test", hooks={"pre_tool_use": ["hooks.check"]})
        assert "pre_tool_use" in m.hooks


class TestDiscoverPlugins:
    def test_discover_empty_dirs(self, tmp_path: Path) -> None:
        # No plugin dirs exist
        found = discover_plugins(extra_dirs=[tmp_path / "nonexistent"])
        assert found == []

    def test_discover_valid_plugin(self, tmp_path: Path) -> None:
        # Create a plugin
        plugin_dir = tmp_path / "my-plugin"
        plugin_dir.mkdir()
        manifest = {
            "name": "my-plugin",
            "version": "1.0.0",
            "description": "Test plugin",
            "tools": ["tools.example"],
        }
        (plugin_dir / "plugin.json").write_text(json.dumps(manifest))

        found = discover_plugins(extra_dirs=[tmp_path])
        assert len(found) == 1
        assert found[0][1].name == "my-plugin"
        assert found[0][1].version == "1.0.0"

    def test_discover_yaml_manifest(self, tmp_path: Path) -> None:
        import yaml

        plugin_dir = tmp_path / "yaml-plugin"
        plugin_dir.mkdir()
        manifest = {"name": "yaml-plugin", "version": "0.1.0"}
        (plugin_dir / "plugin.yaml").write_text(yaml.dump(manifest))

        found = discover_plugins(extra_dirs=[tmp_path])
        assert len(found) == 1
        assert found[0][1].name == "yaml-plugin"

    def test_discover_skips_non_directories(self, tmp_path: Path) -> None:
        # Create a file (not a directory) in the plugins dir
        (tmp_path / "not-a-dir.txt").write_text("ignore me")

        found = discover_plugins(extra_dirs=[tmp_path])
        assert found == []

    def test_discover_multiple_plugins(self, tmp_path: Path) -> None:
        for name in ("plugin-a", "plugin-b"):
            d = tmp_path / name
            d.mkdir()
            (d / "plugin.json").write_text(json.dumps({"name": name}))

        found = discover_plugins(extra_dirs=[tmp_path])
        names = {m.name for _, m in found}
        assert names == {"plugin-a", "plugin-b"}


class TestPluginManager:
    def test_discover_and_list(self, tmp_path: Path) -> None:
        plugin_dir = tmp_path / "test-plugin"
        plugin_dir.mkdir()
        (plugin_dir / "plugin.json").write_text(
            json.dumps(
                {
                    "name": "test-plugin",
                    "version": "1.0.0",
                    "description": "A test plugin",
                }
            )
        )

        pm = PluginManager()
        pm.discover(extra_dirs=[tmp_path])

        plugins = pm.list_plugins()
        assert len(plugins) == 1
        assert plugins[0]["name"] == "test-plugin"
        assert plugins[0]["enabled"] is True

    def test_enable_disable(self, tmp_path: Path) -> None:
        plugin_dir = tmp_path / "test-plugin"
        plugin_dir.mkdir()
        (plugin_dir / "plugin.json").write_text(json.dumps({"name": "test-plugin"}))

        pm = PluginManager()
        pm.discover(extra_dirs=[tmp_path])

        assert pm.disable("test-plugin") is True
        info = pm.get_plugin("test-plugin")
        assert info is not None
        assert info.enabled is False

        assert pm.enable("test-plugin") is True
        assert info.enabled is True

    def test_disable_nonexistent(self) -> None:
        pm = PluginManager()
        assert pm.disable("nonexistent") is False

    def test_load_tools_from_plugin(self, tmp_path: Path) -> None:
        # Create a plugin with a tool module
        plugin_dir = tmp_path / "tool-plugin"
        plugin_dir.mkdir()

        # Create the tool module
        tool_code = """
class MyPluginTool:
    name = "my_plugin_tool"
    description = "A tool from a plugin"
    input_schema = {"type": "object", "properties": {}}

    async def execute(self, args, ctx):
        return None
"""
        (plugin_dir / "tools.py").write_text(tool_code)

        # Create manifest
        (plugin_dir / "plugin.json").write_text(
            json.dumps(
                {
                    "name": "tool-plugin",
                    "tools": ["tools"],
                }
            )
        )

        pm = PluginManager()
        pm.discover(extra_dirs=[tmp_path])

        # Create mock registry and kernel
        class MockRegistry:
            def __init__(self):
                self.tools = {}

            def register(self, tool):
                self.tools[tool.name] = tool

        class MockKernel:
            def __init__(self):
                self.tools = {}

            def register_tool(self, tool):
                self.tools[tool.name] = tool

        registry = MockRegistry()
        kernel = MockKernel()

        count = pm.load_tools(registry, kernel, extra_dirs=[tmp_path])
        assert count >= 1
        assert "my_plugin_tool" in registry.tools
