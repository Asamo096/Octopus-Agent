"""Plugin schemas — manifest format for Octopus plugins."""

from __future__ import annotations

from pydantic import BaseModel, Field


class PluginManifest(BaseModel):
    """Plugin manifest (plugin.json / plugin.yaml)."""

    name: str
    version: str = "0.1.0"
    description: str = ""
    author: str = ""
    octopus_version: str = ">=0.1.0"

    # What the plugin provides
    tools: list[str] = Field(default_factory=list)  # Python module paths
    providers: list[str] = Field(default_factory=list)
    hooks: dict[str, list[str]] = Field(
        default_factory=dict
    )  # event -> [module:function]
