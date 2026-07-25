"""Skill discovery -- scanning directories for SKILL.md files.

Skills are discovered by recursively scanning directories for SKILL.md
files. The scan order determines priority: later sources override earlier
ones with the same name (bundled < user < project).
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Iterator

from octopus.skills.schema import SkillDefinition, SkillSource

logger = logging.getLogger(__name__)


def discover_skills(
    bundled_dir: Path | None = None,
    user_dir: Path | None = None,
    project_dir: Path | None = None,
) -> list[SkillDefinition]:
    """Discover all skills from standard directories.

    Skills are loaded in priority order: bundled, user, project.
    If two skills share the same name, the later source wins (project
    overrides user, user overrides bundled).

    Args:
        bundled_dir: Path to bundled skills (ships with Octopus).
        user_dir: Path to user-level skills (~/.octopus/skills/).
        project_dir: Path to project-level skills (.octopus/skills/).

    Returns:
        List of discovered SkillDefinitions, deduplicated by name
        with later sources taking priority.
    """
    skills: list[SkillDefinition] = []
    seen_names: set[str] = set()

    # Collect in reverse priority order so we can deduplicate cleanly
    search_dirs: list[tuple[Path, SkillSource]] = []

    if bundled_dir and bundled_dir.exists():
        search_dirs.append((bundled_dir, SkillSource.BUNDLED))
    if user_dir and user_dir.exists():
        search_dirs.append((user_dir, SkillSource.USER))
    if project_dir and project_dir.exists():
        search_dirs.append((project_dir, SkillSource.PROJECT))

    for dir_path, source in search_dirs:
        for skill_file in _scan_directory(dir_path):
            skill = SkillDefinition.from_file(skill_file, source)
            if skill is None:
                continue
            if skill.name in seen_names:
                logger.warning(
                    "Duplicate skill name '%s' at %s (already loaded)",
                    skill.name,
                    skill_file,
                )
                continue
            seen_names.add(skill.name)
            skills.append(skill)

    return skills


def _scan_directory(directory: Path) -> Iterator[Path]:
    """Recursively find SKILL.md files in a directory.

    Skips hidden directories (those starting with a dot).
    """
    for path in directory.rglob("SKILL.md"):
        # Skip hidden directories
        if any(part.startswith(".") for part in path.relative_to(directory).parts):
            continue
        yield path
