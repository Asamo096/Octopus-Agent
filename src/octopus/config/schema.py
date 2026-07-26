"""Configuration schema — Pydantic settings models for Octopus Agent."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class ProviderProfile(BaseModel):
    """A named LLM provider configuration."""

    name: str
    provider: str = "openai"  # "anthropic", "openai", "ollama", "custom"
    model: str = "claude-sonnet-4-20250514"
    api_key: str | None = None
    base_url: str | None = None
    api_format: str = "openai"  # "openai" or "anthropic"


class PermissionSettings(BaseModel):
    """Harness permission settings."""

    mode: Literal["default", "plan", "full_auto"] = "default"
    allowed_tools: list[str] = Field(default_factory=list)
    denied_tools: list[str] = Field(default_factory=list)
    denied_commands: list[str] = Field(
        default_factory=lambda: ["rm -rf /", "sudo rm", "mkfs", "dd if="]
    )


class SandboxSettings(BaseModel):
    """Filesystem sandbox settings."""

    enabled: bool = True
    backend: Literal["local", "cube"] = "local"
    allowed_paths: list[str] = Field(default_factory=lambda: ["~/*", "/tmp/*"])
    sensitive_paths: list[str] = Field(
        default_factory=lambda: [
            "~/.ssh/*",
            "~/.aws/*",
            "~/.gnupg/*",
            "**/.env",
            "**/.env.*",
            "**/id_rsa*",
            "**/id_ed25519*",
        ]
    )
    # CubeSandbox settings
    cube_api_url: str = "http://127.0.0.1:3000"
    cube_template_id: str = ""
    cube_api_key: str = ""
    cube_auto_pause_timeout: int = 300
    cube_allow_internet: bool = True


class GUISettings(BaseModel):
    """GUI preferences (used in Phase 3)."""

    theme: str = "system"
    font_size: int = 14
    terminal_shell: str = "/bin/bash"
    show_harness_panel: bool = True


class CLISettings(BaseModel):
    """CLI preferences."""

    output_style: str = "rich"
    streaming: bool = True
    max_turns: int = 50


class OctopusSettings(BaseModel):
    """Top-level Octopus Agent settings."""

    # Provider profiles
    providers: list[ProviderProfile] = Field(default_factory=list)
    default_provider: str = "claude"
    default_model: str = "claude-sonnet-4-20250514"

    # Harness governance
    permissions: PermissionSettings = Field(default_factory=PermissionSettings)
    sandbox: SandboxSettings = Field(default_factory=SandboxSettings)

    # UI preferences
    gui: GUISettings = Field(default_factory=GUISettings)
    cli: CLISettings = Field(default_factory=CLISettings)

    def get_provider(self, name: str | None = None) -> ProviderProfile | None:
        """Get a provider profile by name."""
        target = name or self.default_provider
        for p in self.providers:
            if p.name == target:
                return p
        return None
