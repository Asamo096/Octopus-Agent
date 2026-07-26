"""Integration tests for the memory system.

Tests memory storage, recall, relevance scoring, and extraction.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from octopus.memory.manager import MemoryManager
from octopus.memory.schema import MemoryEntry, MemoryType


@pytest.fixture
def memory_dir(tmp_path: Path) -> Path:
    mem_dir = tmp_path / "memory"
    mem_dir.mkdir()
    return mem_dir


@pytest.fixture
def memory_manager(memory_dir: Path) -> MemoryManager:
    return MemoryManager(memory_dir=memory_dir)


@pytest.mark.asyncio
async def test_store_and_recall(memory_manager: MemoryManager) -> None:
    """Store a memory and recall it by keyword."""
    entry = MemoryEntry(
        name="test-memory",
        description="A test memory about Python testing",
        type=MemoryType.PROJECT,
        content="Use pytest for testing Python projects with async support.",
    )
    memory_manager.store(entry)

    results = memory_manager.recall("pytest Python testing")
    assert len(results) > 0
    assert results[0].name == "test-memory"


@pytest.mark.asyncio
async def test_relevance_scoring(memory_manager: MemoryManager) -> None:
    """More relevant memories score higher in search results."""
    entries = [
        MemoryEntry(
            name="python-testing",
            description="Guide to Python testing with pytest",
            type=MemoryType.PROJECT,
            content="Use pytest fixtures and parametrize for clean test code.",
        ),
        MemoryEntry(
            name="recipe-pasta",
            description="Pasta carbonara recipe",
            type=MemoryType.REFERENCE,
            content="Eggs, guanciale, pecorino, black pepper.",
        ),
    ]

    for entry in entries:
        memory_manager.store(entry)

    results = memory_manager.recall("pytest fixtures parametrize")
    assert len(results) > 0
    if len(results) > 0:
        assert "python" in results[0].name.lower()


@pytest.mark.asyncio
async def test_list_entries_by_type(memory_manager: MemoryManager) -> None:
    """List entries filtered by memory type."""
    for i, mem_type in enumerate(MemoryType):
        entry = MemoryEntry(
            name=f"entry-{i}",
            description=f"Entry of type {mem_type.value}",
            type=mem_type,
            content=f"Content for entry {i}",
        )
        memory_manager.store(entry)

    all_entries = memory_manager.list_entries()
    assert len(all_entries) >= 4  # At least one per MemoryType

    project_entries = memory_manager.list_entries(MemoryType.PROJECT)
    # Filtering by type should return only PROJECT entries
    for e in project_entries:
        assert e.type == MemoryType.PROJECT


@pytest.mark.asyncio
async def test_delete_memory(memory_manager: MemoryManager) -> None:
    """Delete a memory entry."""
    entry = MemoryEntry(
        name="to-delete",
        description="This will be deleted",
        type=MemoryType.REFERENCE,
        content="Temporary content",
    )
    memory_manager.store(entry)

    results = memory_manager.recall("deleted")
    assert len(results) > 0

    success = memory_manager.delete("to-delete")
    assert success

    results_after = memory_manager.recall("deleted")
    assert len(results_after) == 0


@pytest.mark.asyncio
async def test_persistence_across_manager_instances(
    memory_dir: Path,
) -> None:
    """Memories survive creating a new manager instance (disk persistence)."""
    mgr1 = MemoryManager(memory_dir=memory_dir)

    entry = MemoryEntry(
        name="persistent-memory",
        description="Should survive",
        type=MemoryType.USER,
        content="This memory should persist to disk.",
    )
    mgr1.store(entry)

    mgr2 = MemoryManager(memory_dir=memory_dir)
    results = mgr2.recall("persist disk")
    assert len(results) > 0
    assert results[0].name == "persistent-memory"
