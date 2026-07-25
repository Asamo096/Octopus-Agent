"""Base agent protocol and agent definition schema."""

from __future__ import annotations

from typing import Any, Protocol

from pydantic import BaseModel, Field


class AgentDefinition(BaseModel):
    """Definition of an agent — loaded from markdown with YAML frontmatter.

    Agent definitions specify the agent's identity, capabilities, and
    the system prompt that governs its behavior.
    """

    name: str = Field(description="Agent name (kebab-case)")
    description: str = Field(description="One-line description")
    model: str | None = Field(default=None, description="Model override")
    tools: list[str] = Field(default_factory=list, description="Allowed tools")
    system_prompt: str = Field(default="", description="System prompt for the agent")
    max_turns: int = Field(default=50, description="Max turns before stopping")
    metadata: dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def from_markdown(cls, content: str) -> AgentDefinition:
        """Parse an agent definition from markdown with YAML frontmatter."""
        if not content.startswith("---"):
            # Plain text — use as system prompt
            return cls(
                name="unnamed", description="Unnamed agent", system_prompt=content
            )

        parts = content.split("---", 2)
        if len(parts) < 3:
            return cls(
                name="unnamed", description="Unnamed agent", system_prompt=content
            )

        import yaml

        try:
            frontmatter = yaml.safe_load(parts[1].strip())
            if not isinstance(frontmatter, dict):
                frontmatter = {}
        except yaml.YAMLError:
            frontmatter = {}

        system_prompt = parts[2].strip()

        return cls(
            name=frontmatter.get("name", "unnamed"),
            description=frontmatter.get("description", "Unnamed agent"),
            model=frontmatter.get("model"),
            tools=frontmatter.get("tools", []),
            system_prompt=system_prompt,
            max_turns=frontmatter.get("max_turns", 50),
            metadata=frontmatter.get("metadata", {}),
        )


class BaseAgent(Protocol):
    """Protocol that all agents must implement."""

    name: str
    definition: AgentDefinition

    async def run(self, task: str) -> str:
        """Execute the agent on a task and return the result."""
        ...

    async def stop(self) -> None:
        """Stop the agent."""
        ...
