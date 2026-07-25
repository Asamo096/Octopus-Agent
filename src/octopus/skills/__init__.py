"""Octopus Skills System -- markdown-based skill definitions with argument substitution."""

from .loader import discover_skills
from .registry import SkillRegistry
from .schema import SkillDefinition, SkillSource

__all__ = [
    "SkillDefinition",
    "SkillSource",
    "SkillRegistry",
    "discover_skills",
]
