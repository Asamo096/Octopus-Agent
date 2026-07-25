"""Octopus Agent Providers — LLM provider protocol and adapters."""

from .base import Provider
from .litellm_adapter import LiteLLMProvider

__all__ = [
    "Provider",
    "LiteLLMProvider",
]
