"""Tests for octopus.agents — agent system, coordinator, and registry."""

from __future__ import annotations

from pathlib import Path

from octopus.agents.base import AgentDefinition
from octopus.agents.registry import AgentRegistry


class TestAgentDefinition:
    def test_from_plain_text(self) -> None:
        defn = AgentDefinition.from_markdown("You are a helpful assistant.")
        assert defn.name == "unnamed"
        assert defn.system_prompt == "You are a helpful assistant."

    def test_from_markdown_with_frontmatter(self) -> None:
        content = (
            "---\n"
            "name: test-agent\n"
            "description: A test agent\n"
            "model: claude-haiku-4-5-20251001\n"
            "tools: [read_file, shell]\n"
            "max_turns: 10\n"
            "---\n"
            "You are a test agent. Do test things."
        )
        defn = AgentDefinition.from_markdown(content)
        assert defn.name == "test-agent"
        assert defn.description == "A test agent"
        assert defn.model == "claude-haiku-4-5-20251001"
        assert defn.tools == ["read_file", "shell"]
        assert defn.max_turns == 10
        assert defn.system_prompt == "You are a test agent. Do test things."

    def test_from_invalid_markdown(self) -> None:
        content = "---\ninvalid: yaml: [\n---\nBody"
        # Should not raise, just use defaults
        defn = AgentDefinition.from_markdown(content)
        assert defn.name is not None


class TestAgentRegistry:
    def test_register_and_get(self) -> None:
        registry = AgentRegistry()
        defn = AgentDefinition(
            name="my-agent", description="test", system_prompt="test"
        )
        registry.register(defn)

        got = registry.get("my-agent")
        assert got is not None
        assert got.name == "my-agent"

    def test_get_nonexistent(self) -> None:
        registry = AgentRegistry()
        assert registry.get("nonexistent") is None

    def test_list_agents(self) -> None:
        registry = AgentRegistry()
        registry.register(AgentDefinition(name="a", description="a", system_prompt="a"))
        registry.register(AgentDefinition(name="b", description="b", system_prompt="b"))

        agents = registry.list_agents()
        assert len(agents) == 2

    def test_discover_builtins(self) -> None:
        registry = AgentRegistry()
        count = registry.discover()
        assert count >= 4  # general, explorer, reviewer, planner

        general = registry.get("general")
        assert general is not None
        assert general.description == "General-purpose coding assistant"

    def test_discover_from_directory(self, tmp_path: Path) -> None:
        agents_dir = tmp_path / "agents"
        agents_dir.mkdir()
        (agents_dir / "custom.md").write_text(
            "---\nname: custom\ndescription: Custom agent\n---\nCustom system prompt."
        )

        registry = AgentRegistry()
        count = registry.discover(user_dir=agents_dir)
        assert count >= 1

        custom = registry.get("custom")
        assert custom is not None
        assert custom.system_prompt == "Custom system prompt."
