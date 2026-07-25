"""Agent registry — discover and register agent definitions."""

from __future__ import annotations

import logging
from pathlib import Path

from octopus.agents.base import AgentDefinition

logger = logging.getLogger(__name__)

# Default agent definitions directory
DEFAULT_AGENTS_DIR = Path.home() / ".octopus" / "agents"

# Built-in agent definitions
BUILTIN_AGENTS: dict[str, str] = {
    "general": (
        "---\n"
        "name: general\n"
        "description: General-purpose coding assistant\n"
        "tools: [read_file, write_file, edit_file, shell, glob, grep, git_status, git_diff]\n"
        "---\n"
        "You are a general-purpose coding assistant. Help users with coding tasks,\n"
        "file operations, debugging, and code review. Be thorough and precise."
    ),
    "explorer": (
        "---\n"
        "name: explorer\n"
        "description: Code exploration and understanding\n"
        "tools: [read_file, glob, grep, git_status, git_diff, git_log]\n"
        "---\n"
        "You are a code explorer. Your job is to understand codebases by reading\n"
        "files, searching for patterns, and analyzing git history. Provide clear\n"
        "explanations of what you find."
    ),
    "reviewer": (
        "---\n"
        "name: reviewer\n"
        "description: Code review and quality analysis\n"
        "tools: [read_file, glob, grep, git_diff]\n"
        "---\n"
        "You are a code reviewer. Analyze code for bugs, security issues,\n"
        "performance problems, and style violations. Provide specific,\n"
        "actionable feedback with file paths and line numbers."
    ),
    "planner": (
        "---\n"
        "name: planner\n"
        "description: Task planning and decomposition\n"
        "tools: [read_file, glob, grep]\n"
        "---\n"
        "You are a task planner. Break down complex tasks into clear,\n"
        "actionable steps. Consider dependencies, risks, and testing\n"
        "strategies. Output a structured plan."
    ),
}


class AgentRegistry:
    """Registry for agent definitions — discovers and stores agent definitions.

    Discovers agents from:
    1. Built-in definitions (compiled in)
    2. User directory (~/.octopus/agents/)
    3. Project directory (<workspace>/.octopus/agents/)
    """

    def __init__(self) -> None:
        self._agents: dict[str, AgentDefinition] = {}

    def register(self, definition: AgentDefinition) -> None:
        """Register an agent definition."""
        self._agents[definition.name] = definition
        logger.debug("Registered agent: %s", definition.name)

    def get(self, name: str) -> AgentDefinition | None:
        """Get an agent definition by name."""
        return self._agents.get(name)

    def list_agents(self) -> list[AgentDefinition]:
        """List all registered agent definitions."""
        return list(self._agents.values())

    def discover(
        self,
        user_dir: Path | None = None,
        project_dir: Path | None = None,
    ) -> int:
        """Discover agent definitions from directories.

        Returns the number of agents discovered.
        """
        count = 0

        # Load built-in agents
        for name, content in BUILTIN_AGENTS.items():
            if name not in self._agents:
                self.register(AgentDefinition.from_markdown(content))
                count += 1

        # Load from user directory
        agents_dir = user_dir or DEFAULT_AGENTS_DIR
        if agents_dir.exists():
            for file_path in agents_dir.glob("*.md"):
                try:
                    content = file_path.read_text()
                    definition = AgentDefinition.from_markdown(content)
                    self.register(definition)
                    count += 1
                except Exception as e:
                    logger.warning("Failed to load agent %s: %s", file_path, e)

        # Load from project directory
        if project_dir:
            project_agents = project_dir / ".octopus" / "agents"
            if project_agents.exists():
                for file_path in project_agents.glob("*.md"):
                    try:
                        content = file_path.read_text()
                        definition = AgentDefinition.from_markdown(content)
                        self.register(definition)
                        count += 1
                    except Exception as e:
                        logger.warning("Failed to load agent %s: %s", file_path, e)

        return count
