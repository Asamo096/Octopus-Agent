"""Tests for octopus.memory — MemoryManager and MemoryEntry."""

from __future__ import annotations

import pytest
from pathlib import Path
from datetime import UTC, datetime

from octopus.memory.manager import MemoryManager
from octopus.memory.schema import MemoryEntry, MemoryType


@pytest.fixture
def memory_dir(tmp_path: Path) -> Path:
    """Create a temporary memory directory."""
    return tmp_path / "memory"


@pytest.fixture
def manager(memory_dir: Path) -> MemoryManager:
    """Create a MemoryManager with a temporary directory."""
    return MemoryManager(memory_dir=memory_dir)


class TestMemoryEntry:
    def test_create_entry(self) -> None:
        entry = MemoryEntry(
            name="test-entry",
            description="A test entry",
            content="This is test content.",
        )
        assert entry.name == "test-entry"
        assert entry.memory_type == MemoryType.USER

    def test_to_frontmatter(self) -> None:
        entry = MemoryEntry(
            name="test-entry",
            description="A test entry",
            content="This is test content.",
            tags=["test", "memory"],
        )
        text = entry.to_frontmatter()
        assert "---" in text
        assert "name: test-entry" in text
        assert "description: A test entry" in text
        assert "This is test content." in text

    def test_from_file_roundtrip(self) -> None:
        entry = MemoryEntry(
            name="roundtrip",
            description="Test roundtrip",
            content="Content here.",
            memory_type=MemoryType.PROJECT,
            importance=4,
            tags=["test"],
        )
        text = entry.to_frontmatter()
        restored = MemoryEntry.from_file(text)

        assert restored.name == entry.name
        assert restored.description == entry.description
        assert restored.content == entry.content
        assert restored.memory_type == entry.memory_type
        assert restored.importance == entry.importance
        assert restored.tags == entry.tags

    def test_from_file_invalid(self) -> None:
        with pytest.raises(ValueError, match="missing frontmatter"):
            MemoryEntry.from_file("not a valid file")


class TestMemoryManager:
    def test_store_and_get(self, manager: MemoryManager) -> None:
        entry = MemoryEntry(name="test", description="test", content="hello")
        path = manager.store(entry)
        assert path.exists()

        loaded = manager.get("test")
        assert loaded is not None
        assert loaded.name == "test"
        assert loaded.content == "hello"

    def test_get_nonexistent(self, manager: MemoryManager) -> None:
        assert manager.get("nonexistent") is None

    def test_delete(self, manager: MemoryManager) -> None:
        entry = MemoryEntry(name="to-delete", description="test", content="bye")
        manager.store(entry)
        assert manager.delete("to-delete")
        assert manager.get("to-delete") is None

    def test_delete_nonexistent(self, manager: MemoryManager) -> None:
        assert not manager.delete("nonexistent")

    def test_list_entries(self, manager: MemoryManager) -> None:
        manager.store(MemoryEntry(name="a", description="a", content="a"))
        manager.store(MemoryEntry(name="b", description="b", content="b"))
        entries = manager.list_entries()
        assert len(entries) == 2

    def test_list_filter_by_type(self, manager: MemoryManager) -> None:
        manager.store(MemoryEntry(name="user-mem", description="u", content="u", memory_type=MemoryType.USER))
        manager.store(MemoryEntry(name="proj-mem", description="p", content="p", memory_type=MemoryType.PROJECT))

        user_entries = manager.list_entries(memory_type=MemoryType.USER)
        assert len(user_entries) == 1
        assert user_entries[0].name == "user-mem"

    def test_list_filter_by_tag(self, manager: MemoryManager) -> None:
        manager.store(MemoryEntry(name="tagged", description="t", content="t", tags=["important"]))
        manager.store(MemoryEntry(name="untagged", description="u", content="u"))

        tagged = manager.list_entries(tag="important")
        assert len(tagged) == 1
        assert tagged[0].name == "tagged"

    def test_recall_by_name(self, manager: MemoryManager) -> None:
        manager.store(MemoryEntry(name="dark-mode", description="User prefers dark mode", content="Dark mode enabled"))
        manager.store(MemoryEntry(name="light-theme", description="Light theme", content="Light theme"))

        results = manager.recall("dark mode")
        assert len(results) >= 1
        assert results[0].name == "dark-mode"

    def test_recall_by_content(self, manager: MemoryManager) -> None:
        manager.store(MemoryEntry(name="pref", description="preferences", content="Prefers Python 3.11"))
        manager.store(MemoryEntry(name="other", description="other", content="Something else"))

        results = manager.recall("Python 3.11")
        assert len(results) >= 1
        assert results[0].name == "pref"

    def test_recall_limit(self, manager: MemoryManager) -> None:
        for i in range(10):
            manager.store(MemoryEntry(name=f"entry-{i}", description=f"entry {i}", content=f"content {i}"))

        results = manager.recall("entry", limit=3)
        assert len(results) == 3

    def test_count(self, manager: MemoryManager) -> None:
        assert manager.count() == 0
        manager.store(MemoryEntry(name="a", description="a", content="a"))
        assert manager.count() == 1

    def test_clear(self, manager: MemoryManager) -> None:
        manager.store(MemoryEntry(name="a", description="a", content="a"))
        manager.store(MemoryEntry(name="b", description="b", content="b"))
        deleted = manager.clear()
        assert deleted == 2
        assert manager.count() == 0
