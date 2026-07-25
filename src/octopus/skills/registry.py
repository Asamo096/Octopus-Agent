"""Skill registry -- loading, querying, and rendering skills.

The SkillRegistry is the primary interface for working with skills.
It loads skills from standard directories and provides lookup and
prompt-generation methods.
"""

from __future__ import annotations

from pathlib import Path

from octopus.skills.loader import discover_skills
from octopus.skills.schema import SkillDefinition


class SkillRegistry:
    """Registry of available skills.

    Usage:
        registry = SkillRegistry()
        registry.load(
            bundled_dir=Path("src/octopus/skills/bundled"),
            user_dir=Path.home() / ".octopus" / "skills",
            project_dir=Path(".octopus/skills"),
        )

        skill = registry.get("review")
        if skill:
            instructions = skill.render_instructions("src/main.py")
    """

    def __init__(self) -> None:
        self._skills: dict[str, SkillDefinition] = {}

    def load(
        self,
        bundled_dir: Path | None = None,
        user_dir: Path | None = None,
        project_dir: Path | None = None,
    ) -> None:
        """Load skills from standard directories.

        Later sources override earlier ones if they share the same name
        (project overrides user, user overrides bundled).
        """
        for skill in discover_skills(bundled_dir, user_dir, project_dir):
            self._skills[skill.name] = skill

    def get(self, name: str) -> SkillDefinition | None:
        """Get a skill by name. Returns None if not found."""
        return self._skills.get(name)

    def list_skills(self) -> list[SkillDefinition]:
        """List all loaded skills, sorted by name."""
        return sorted(self._skills.values(), key=lambda s: s.name)

    def to_tool_prompt(self) -> str:
        """Generate a prompt section listing available skills.

        Returns an empty string if no skills are loaded.
        """
        if not self._skills:
            return ""
        lines = ["## Available Skills", ""]
        for skill in self.list_skills():
            lines.append(f"- **{skill.name}**: {skill.description}")
        return "\n".join(lines)

    def __len__(self) -> int:
        return len(self._skills)

    def __contains__(self, name: str) -> bool:
        return name in self._skills
