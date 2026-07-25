"""Memory entry schema — Pydantic models for memory storage."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class MemoryType(StrEnum):
    """Types of memory entries."""

    USER = "user"  # User preferences, info
    FEEDBACK = "feedback"  # Corrections, confirmed approaches
    PROJECT = "project"  # Ongoing work, goals, constraints
    REFERENCE = "reference"  # External resources, URLs, tickets


class MemoryEntry(BaseModel):
    """A single memory entry stored as a markdown file with YAML frontmatter."""

    name: str = Field(description="Short kebab-case slug")
    description: str = Field(description="One-line summary for relevance matching")
    memory_type: MemoryType = Field(default=MemoryType.USER)
    content: str = Field(description="The actual memory content")
    tags: list[str] = Field(default_factory=list)
    importance: int = Field(default=3, ge=1, le=5)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    metadata: dict[str, Any] = Field(default_factory=dict)

    def to_frontmatter(self) -> str:
        """Serialize to YAML frontmatter + markdown body."""
        lines = [
            "---",
            f"name: {self.name}",
            f"description: {self.description}",
            f"memory_type: {self.memory_type.value}",
            f"importance: {self.importance}",
            f"created_at: {self.created_at.isoformat()}",
            f"updated_at: {self.updated_at.isoformat()}",
        ]
        if self.tags:
            lines.append(f"tags: [{', '.join(self.tags)}]")
        lines.append("---")
        lines.append("")
        lines.append(self.content)
        return "\n".join(lines)

    @classmethod
    def from_file(cls, content: str) -> MemoryEntry:
        """Parse a markdown file with YAML frontmatter."""
        if not content.startswith("---"):
            raise ValueError("Not a valid memory file (missing frontmatter)")

        # Split frontmatter and body
        parts = content.split("---", 2)
        if len(parts) < 3:
            raise ValueError("Invalid frontmatter format")

        frontmatter_text = parts[1].strip()
        body = parts[2].strip()

        # Parse YAML frontmatter
        import yaml

        frontmatter = yaml.safe_load(frontmatter_text)

        # YAML may parse ISO dates as datetime objects directly
        created_raw = frontmatter.get("created_at", datetime.now(UTC).isoformat())
        updated_raw = frontmatter.get("updated_at", datetime.now(UTC).isoformat())

        if isinstance(created_raw, str):
            created_at = datetime.fromisoformat(created_raw)
        else:
            created_at = created_raw

        if isinstance(updated_raw, str):
            updated_at = datetime.fromisoformat(updated_raw)
        else:
            updated_at = updated_raw

        return cls(
            name=frontmatter.get("name", "unknown"),
            description=frontmatter.get("description", ""),
            memory_type=MemoryType(frontmatter.get("memory_type", "user")),
            content=body,
            tags=frontmatter.get("tags", []),
            importance=frontmatter.get("importance", 3),
            created_at=created_at,
            updated_at=updated_at,
        )
