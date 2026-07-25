"""Octopus Agent System — multi-agent coordination with in-process backend."""

from .base import AgentDefinition, BaseAgent
from .coordinator import AgentCoordinator
from .llm_agent import LLMAgent
from .registry import AgentRegistry

__all__ = [
    "BaseAgent",
    "AgentDefinition",
    "LLMAgent",
    "AgentCoordinator",
    "AgentRegistry",
]
