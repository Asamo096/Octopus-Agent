"""Tests for octopus.core.hooks — HookManager."""

from __future__ import annotations

import pytest

from octopus.core.hooks import Hook, HookEvent, HookManager, HookResult


class TestHook:
    async def test_execute_returns_hook_result(self) -> None:
        async def callback(data):
            return HookResult(continue_execution=True)

        hook = Hook("test", callback)
        result = await hook.execute({"key": "value"})
        assert result.continue_execution

    async def test_execute_returns_bool(self) -> None:
        async def callback(data):
            return True

        hook = Hook("test", callback)
        result = await hook.execute({})
        assert result.continue_execution

    async def test_execute_returns_false(self) -> None:
        async def callback(data):
            return False

        hook = Hook("test", callback)
        result = await hook.execute({})
        assert not result.continue_execution

    async def test_execute_exception_returns_error(self) -> None:
        async def callback(data):
            raise RuntimeError("boom")

        hook = Hook("test", callback)
        result = await hook.execute({})
        assert not result.continue_execution
        assert "boom" in (result.error or "")


class TestHookManager:
    def test_register_and_get(self) -> None:
        manager = HookManager()
        hook = Hook("test", lambda data: True)
        manager.register(HookEvent.PRE_TOOL_USE, hook)

        hooks = manager.get_hooks(HookEvent.PRE_TOOL_USE)
        assert len(hooks) == 1
        assert hooks[0].name == "test"

    def test_priority_ordering(self) -> None:
        manager = HookManager()
        hook_low = Hook("low", lambda data: True, priority=10)
        hook_high = Hook("high", lambda data: True, priority=100)
        manager.register(HookEvent.PRE_TOOL_USE, hook_low)
        manager.register(HookEvent.PRE_TOOL_USE, hook_high)

        hooks = manager.get_hooks(HookEvent.PRE_TOOL_USE)
        assert hooks[0].name == "high"
        assert hooks[1].name == "low"

    async def test_fire_no_hooks(self) -> None:
        manager = HookManager()
        result = await manager.fire(HookEvent.PRE_TOOL_USE, {})
        assert result.continue_execution

    async def test_fire_stops_on_false(self) -> None:
        manager = HookManager()

        async def blocker(data):
            return HookResult(continue_execution=False, error="blocked")

        async def runner(data):
            return HookResult(continue_execution=True)

        manager.register(HookEvent.PRE_TOOL_USE, Hook("blocker", blocker, priority=100))
        manager.register(HookEvent.PRE_TOOL_USE, Hook("runner", runner, priority=50))

        result = await manager.fire(HookEvent.PRE_TOOL_USE, {})
        assert not result.continue_execution
        assert "blocked" in (result.error or "")

    async def test_fire_modifies_data(self) -> None:
        manager = HookManager()

        async def modifier(data):
            return HookResult(
                continue_execution=True,
                modified_data={"extra": "added"},
            )

        manager.register(HookEvent.PRE_TOOL_USE, Hook("modifier", modifier))
        result = await manager.fire(HookEvent.PRE_TOOL_USE, {"original": True})
        assert result.modified_data is not None
        assert result.modified_data["extra"] == "added"
        assert result.modified_data["original"] is True

    def test_unregister(self) -> None:
        manager = HookManager()
        hook = Hook("test", lambda data: True)
        manager.register(HookEvent.PRE_TOOL_USE, hook)
        manager.unregister(HookEvent.PRE_TOOL_USE, "test")

        hooks = manager.get_hooks(HookEvent.PRE_TOOL_USE)
        assert len(hooks) == 0

    def test_clear(self) -> None:
        manager = HookManager()
        manager.register(HookEvent.PRE_TOOL_USE, Hook("a", lambda d: True))
        manager.register(HookEvent.POST_TOOL_USE, Hook("b", lambda d: True))

        manager.clear(HookEvent.PRE_TOOL_USE)
        assert len(manager.get_hooks(HookEvent.PRE_TOOL_USE)) == 0
        assert len(manager.get_hooks(HookEvent.POST_TOOL_USE)) == 1

    def test_clear_all(self) -> None:
        manager = HookManager()
        manager.register(HookEvent.PRE_TOOL_USE, Hook("a", lambda d: True))
        manager.register(HookEvent.POST_TOOL_USE, Hook("b", lambda d: True))

        manager.clear()
        assert len(manager.list_events()) == 0

    def test_list_events(self) -> None:
        manager = HookManager()
        manager.register(HookEvent.PRE_TOOL_USE, Hook("a", lambda d: True))
        manager.register(HookEvent.AUDIT_LOG, Hook("b", lambda d: True))

        events = manager.list_events()
        assert HookEvent.PRE_TOOL_USE in events
        assert HookEvent.AUDIT_LOG in events
