"""Tests for octopus.core.state — StateManager."""

from __future__ import annotations

from pathlib import Path

import pytest

from octopus.core.state import StateManager


@pytest.fixture
async def state(tmp_path: Path):
    """Provide a StateManager with a temporary database."""
    db_path = tmp_path / "state.db"
    manager = StateManager(db_path=db_path)
    yield manager
    await manager.close()


class TestStateManager:
    async def test_create_and_get_session(self, state: StateManager) -> None:
        session = await state.create_session("s1", name="Test Session")
        assert session.session_id == "s1"
        assert session.name == "Test Session"

        retrieved = await state.get_session("s1")
        assert retrieved is not None
        assert retrieved.session_id == "s1"

    async def test_get_nonexistent_session(self, state: StateManager) -> None:
        result = await state.get_session("nonexistent")
        assert result is None

    async def test_list_sessions(self, state: StateManager) -> None:
        await state.create_session("s1", name="First")
        await state.create_session("s2", name="Second")
        sessions = await state.list_sessions()
        assert len(sessions) == 2
        names = {s.name for s in sessions}
        assert "First" in names
        assert "Second" in names

    async def test_update_session(self, state: StateManager) -> None:
        await state.create_session("s1", name="Old Name")
        await state.update_session("s1", name="New Name")

        session = await state.get_session("s1")
        assert session is not None
        assert session.name == "New Name"

    async def test_delete_session(self, state: StateManager) -> None:
        await state.create_session("s1")
        await state.delete_session("s1")
        result = await state.get_session("s1")
        assert result is None

    async def test_kv_store_set_get(self, state: StateManager) -> None:
        await state.set_value("theme", "dark")
        value = await state.get_value("theme")
        assert value == "dark"

    async def test_kv_store_default(self, state: StateManager) -> None:
        value = await state.get_value("nonexistent", default="fallback")
        assert value == "fallback"

    async def test_kv_store_overwrite(self, state: StateManager) -> None:
        await state.set_value("key", "v1")
        await state.set_value("key", "v2")
        value = await state.get_value("key")
        assert value == "v2"

    async def test_kv_store_delete(self, state: StateManager) -> None:
        await state.set_value("key", "value")
        await state.delete_value("key")
        value = await state.get_value("key", default=None)
        assert value is None

    async def test_kv_store_complex_value(self, state: StateManager) -> None:
        data = {"nested": {"key": [1, 2, 3]}}
        await state.set_value("complex", data)
        value = await state.get_value("complex")
        assert value == data

    async def test_list_values(self, state: StateManager) -> None:
        await state.set_value("app.theme", "dark")
        await state.set_value("app.font_size", 14)
        await state.set_value("user.name", "test")

        all_values = await state.list_values()
        assert len(all_values) == 3

        app_values = await state.list_values(prefix="app.")
        assert len(app_values) == 2
        assert "app.theme" in app_values
        assert "app.font_size" in app_values

    async def test_session_with_workspace(self, state: StateManager) -> None:
        session = await state.create_session("s1", workspace="/home/user/project")
        assert session.workspace == "/home/user/project"

        retrieved = await state.get_session("s1")
        assert retrieved is not None
        assert retrieved.workspace == "/home/user/project"
