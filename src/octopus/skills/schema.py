"""Skill definition schema -- parsing SKILL.md files with YAML frontmatter.

Skills are markdown files with YAML frontmatter that define reusable
instructions for the agent. They support argument substitution and
per-skill tool restrictions.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any

import yaml


class SkillSource(StrEnum):
    """Where a skill was loaded from."""

    BUNDLED = "bundled"  # Ships with Octopus
    USER = "user"  # User's home config
    PROJECT = "project"  # Project-level .octopus/skills/
    PLUGIN = "plugin"  # From a plugin


@dataclass
class SkillDefinition:
    """A skill loaded from a SKILL.md file.

    Skills are markdown files with YAML frontmatter. The frontmatter
    defines metadata (name, description, allowed tools, etc.) and the
    body contains the instructions that are injected into the agent's
    context when the skill is activated.

    Usage:
        skill = SkillDefinition.from_file(Path("review/SKILL.md"), SkillSource.BUNDLED)
        if skill:
            instructions = skill.render_instructions("src/main.py")
    """

    name: str
    description: str
    source: SkillSource
    path: Path

    # From frontmatter
    allowed_tools: list[str] = field(default_factory=list)
    blocked_tools: list[str] = field(default_factory=list)
    model: str | None = None
    effort: str | None = None
    system_prompt_suffix: str | None = None

    # Body (markdown after frontmatter)
    instructions: str = ""

    # Metadata
    argument_names: list[str] = field(default_factory=list)
    hooks: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_file(cls, path: Path, source: SkillSource) -> SkillDefinition | None:
        """Parse a SKILL.md file into a SkillDefinition.

        Returns None if the file doesn't exist, has invalid frontmatter,
        or is missing the required 'name' field.
        """
        try:
            content = path.read_text(encoding="utf-8")
        except OSError:
            return None

        if not content.startswith("---"):
            return None

        # Split frontmatter and body
        parts = content.split("---", 2)
        if len(parts) < 3:
            return None

        try:
            meta = yaml.safe_load(parts[1]) or {}
        except yaml.YAMLError:
            return None

        if not isinstance(meta, dict) or "name" not in meta:
            return None

        body = parts[2].strip()

        # Extract argument placeholder names from body ($ARGUMENTS, $1, $2, etc.)
        arg_names = list(set(re.findall(r"\$(?:ARGUMENTS|\d+)", body)))

        return cls(
            name=meta["name"],
            description=meta.get("description", ""),
            source=source,
            path=path,
            allowed_tools=meta.get("allowed-tools", []),
            blocked_tools=meta.get("blocked-tools", []),
            model=meta.get("model"),
            effort=meta.get("effort"),
            system_prompt_suffix=meta.get("system-prompt"),
            instructions=body,
            argument_names=arg_names,
            hooks=meta.get("hooks", {}),
        )

    def render_instructions(self, arguments: str = "") -> str:
        """Render skill instructions with argument substitution.

        Replaces $ARGUMENTS with the full argument string, and
        $1, $2, etc. with individual whitespace-separated parts.
        """
        result = self.instructions
        result = result.replace("$ARGUMENTS", arguments)
        # Replace $1, $2, etc. with split arguments
        parts = arguments.split() if arguments else []
        for i, part in enumerate(parts, 1):
            result = result.replace(f"${i}", part)
        return result
