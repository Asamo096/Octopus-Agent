"""Memory manager — CRUD, search, and relevance scoring for memory entries.

Memory entries are stored as markdown files with YAML frontmatter in
~/.octopus/memory/ (user-scoped) or <workspace>/.octopus/memory/ (project-scoped).
"""

from __future__ import annotations

import logging
import re
from datetime import UTC, datetime
from pathlib import Path

from octopus.memory.schema import MemoryEntry, MemoryType

logger = logging.getLogger(__name__)

# Default memory directory
DEFAULT_MEMORY_DIR = Path.home() / ".octopus" / "memory"


class MemoryManager:
    """Manages persistent memory entries stored as markdown files.

    Usage:
        manager = MemoryManager()
        manager.store(MemoryEntry(name="user-pref", content="Prefers dark mode"))
        results = manager.recall("dark mode")
    """

    def __init__(self, memory_dir: Path | None = None) -> None:
        self.memory_dir = memory_dir or DEFAULT_MEMORY_DIR
        self.memory_dir.mkdir(parents=True, exist_ok=True)

    # ---- CRUD ---------------------------------------------------------------

    def store(self, entry: MemoryEntry) -> Path:
        """Store a memory entry. Returns the file path."""
        entry.updated_at = datetime.now(UTC)
        file_path = self.memory_dir / f"{entry.name}.md"
        file_path.write_text(entry.to_frontmatter())
        logger.debug("Stored memory: %s", entry.name)
        return file_path

    def get(self, name: str) -> MemoryEntry | None:
        """Get a memory entry by name."""
        file_path = self.memory_dir / f"{name}.md"
        if not file_path.exists():
            return None
        try:
            return MemoryEntry.from_file(file_path.read_text())
        except Exception as e:
            logger.warning("Failed to parse memory %s: %s", name, e)
            return None

    def delete(self, name: str) -> bool:
        """Delete a memory entry. Returns True if deleted."""
        file_path = self.memory_dir / f"{name}.md"
        if file_path.exists():
            file_path.unlink()
            logger.debug("Deleted memory: %s", name)
            return True
        return False

    def list_entries(
        self,
        memory_type: MemoryType | None = None,
        tag: str | None = None,
    ) -> list[MemoryEntry]:
        """List all memory entries, optionally filtered by type or tag."""
        entries = []
        for file_path in sorted(self.memory_dir.glob("*.md")):
            try:
                entry = MemoryEntry.from_file(file_path.read_text())
                if memory_type and entry.memory_type != memory_type:
                    continue
                if tag and tag not in entry.tags:
                    continue
                entries.append(entry)
            except Exception as e:
                logger.warning("Skipping invalid memory file %s: %s", file_path, e)
        return entries

    # ---- Search & relevance -------------------------------------------------

    def recall(
        self,
        query: str,
        limit: int = 5,
        memory_type: MemoryType | None = None,
    ) -> list[MemoryEntry]:
        """Search memory entries by keyword relevance.

        Uses simple TF-based scoring against name, description, and content.
        """
        entries = self.list_entries(memory_type=memory_type)
        if not entries:
            return []

        # Score each entry
        scored: list[tuple[float, MemoryEntry]] = []
        query_terms = _tokenize(query.lower())

        for entry in entries:
            score = self._score_entry(entry, query_terms)
            if score > 0:
                scored.append((score, entry))

        # Sort by score descending, then importance descending
        scored.sort(key=lambda x: (x[0], x[1].importance), reverse=True)
        return [entry for _, entry in scored[:limit]]

    def _score_entry(self, entry: MemoryEntry, query_terms: list[str]) -> float:
        """Score a memory entry against query terms."""
        score = 0.0

        # Searchable text fields with weights
        searchable = [
            (entry.name.lower(), 3.0),  # Name matches are most relevant
            (entry.description.lower(), 2.0),  # Description is second
            (entry.content.lower(), 1.0),  # Content is broadest
        ]

        for text, weight in searchable:
            text_terms = _tokenize(text)
            for term in query_terms:
                if term in text_terms:
                    score += weight
                elif any(term in t for t in text_terms):
                    score += weight * 0.5  # Partial match

        # Boost by importance
        score *= 1.0 + (entry.importance - 3) * 0.1

        # Boost recent entries
        if entry.updated_at:
            days_old = (datetime.now(UTC) - entry.updated_at).days
            if days_old < 7:
                score *= 1.2
            elif days_old < 30:
                score *= 1.1

        return score

    # ---- Utility ------------------------------------------------------------

    def count(self) -> int:
        """Count total memory entries."""
        return len(list(self.memory_dir.glob("*.md")))

    def clear(self) -> int:
        """Delete all memory entries. Returns count deleted."""
        count = 0
        for file_path in self.memory_dir.glob("*.md"):
            file_path.unlink()
            count += 1
        return count


def _tokenize(text: str) -> list[str]:
    """Simple tokenization: split on non-alphanumeric, filter short tokens."""
    tokens = re.split(r"[^a-z0-9]+", text)
    return [t for t in tokens if len(t) >= 2]
