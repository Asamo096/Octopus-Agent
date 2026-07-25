"""Tests for octopus.core.hooks — HookManager with all 4 hook types."""

from __future__ import annotations

from octopus.core.hooks import (
    AggregatedHookResult,
    Hook,
    HookEvent,
    HookManager,
    HookResult,
    HookType,
)


class TestHook:
    async def test_python_hook_returns_hook_result(self) -> None:
        async def callback(data):
            return HookResult(continue_execution=True)

        hook = Hook("test", HookType.PYTHON, HookEvent.PRE_TOOL_USE, callback=callback)
        result = await hook.execute({"key": "value"})
        assert result.continue_execution

    async def test_python_hook_returns_bool(self) -> None:
        async def callback(data):
            return True

        hook = Hook("test", HookType.PYTHON, HookEvent.PRE_TOOL_USE, callback=callback)
        result = await hook.execute({})
        assert result.continue_execution

    async def test_python_hook_returns_false(self) -> None:
        async def callback(data):
            return False

        hook = Hook("test", HookType.PYTHON, HookEvent.PRE_TOOL_USE, callback=callback)
        result = await hook.execute({})
        assert not result.continue_execution

    async def test_python_hook_exception_returns_error(self) -> None:
        async def callback(data):
            raise RuntimeError("boom")

        hook = Hook("test", HookType.PYTHON, HookEvent.PRE_TOOL_USE, callback=callback)
        result = await hook.execute({})
        assert not result.continue_execution
        assert "boom" in (result.error or "")

    async def test_command_hook_no_config(self) -> None:
        hook = Hook("test", HookType.COMMAND, HookEvent.PRE_TOOL_USE)
        result = await hook.execute({})
        assert result.continue_execution

    async def test_http_hook_no_config(self) -> None:
        hook = Hook("test", HookType.HTTP, HookEvent.PRE_TOOL_USE)
        result = await hook.execute({})
        assert result.continue_execution

    async def test_prompt_hook_no_config(self) -> None:
        hook = Hook("test", HookType.PROMPT, HookEvent.PRE_TOOL_USE)
        result = await hook.execute({})
        assert result.continue_execution


class TestHookManager:
    def test_register_and_get(self) -> None:
        manager = HookManager()
        hook = Hook(
            "test", HookType.PYTHON, HookEvent.PRE_TOOL_USE, callback=lambda d: True
        )
        manager.register(HookEvent.PRE_TOOL_USE, hook)

        hooks = manager.get_hooks(HookEvent.PRE_TOOL_USE)
        assert len(hooks) == 1
        assert hooks[0].name == "test"

    def test_priority_ordering(self) -> None:
        manager = HookManager()
        hook_low = Hook(
            "low",
            HookType.PYTHON,
            HookEvent.PRE_TOOL_USE,
            callback=lambda d: True,
            priority=10,
        )
        hook_high = Hook(
            "high",
            HookType.PYTHON,
            HookEvent.PRE_TOOL_USE,
            callback=lambda d: True,
            priority=100,
        )
        manager.register(HookEvent.PRE_TOOL_USE, hook_low)
        manager.register(HookEvent.PRE_TOOL_USE, hook_high)

        hooks = manager.get_hooks(HookEvent.PRE_TOOL_USE)
        assert hooks[0].name == "high"
        assert hooks[1].name == "low"

    async def test_fire_no_hooks(self) -> None:
        manager = HookManager()
        result = await manager.fire(HookEvent.PRE_TOOL_USE, {})
        assert result.continue_execution
        assert not result.blocked

    async def test_fire_stops_on_false(self) -> None:
        manager = HookManager()

        async def blocker(data):
            return HookResult(continue_execution=False, error="blocked")

        async def runner(data):
            return HookResult(continue_execution=True)

        manager.register(
            HookEvent.PRE_TOOL_USE,
            Hook(
                "blocker",
                HookType.PYTHON,
                HookEvent.PRE_TOOL_USE,
                callback=blocker,
                priority=100,
            ),
        )
        manager.register(
            HookEvent.PRE_TOOL_USE,
            Hook(
                "runner",
                HookType.PYTHON,
                HookEvent.PRE_TOOL_USE,
                callback=runner,
                priority=50,
            ),
        )

        result = await manager.fire(HookEvent.PRE_TOOL_USE, {})
        assert result.blocked
        assert "blocked" in (result.error or "")

    async def test_fire_modifies_data(self) -> None:
        manager = HookManager()

        async def modifier(data):
            return HookResult(
                continue_execution=True,
                modified_data={"extra": "added"},
            )

        manager.register(
            HookEvent.PRE_TOOL_USE,
            Hook(
                "modifier", HookType.PYTHON, HookEvent.PRE_TOOL_USE, callback=modifier
            ),
        )
        result = await manager.fire(HookEvent.PRE_TOOL_USE, {"original": True})
        assert result.modified_data is not None
        assert result.modified_data["extra"] == "added"
        assert result.modified_data["original"] is True

    def test_unregister(self) -> None:
        manager = HookManager()
        hook = Hook(
            "test", HookType.PYTHON, HookEvent.PRE_TOOL_USE, callback=lambda d: True
        )
        manager.register(HookEvent.PRE_TOOL_USE, hook)
        manager.unregister(HookEvent.PRE_TOOL_USE, "test")

        hooks = manager.get_hooks(HookEvent.PRE_TOOL_USE)
        assert len(hooks) == 0

    def test_clear(self) -> None:
        manager = HookManager()
        manager.register(
            HookEvent.PRE_TOOL_USE,
            Hook("a", HookType.PYTHON, HookEvent.PRE_TOOL_USE, callback=lambda d: True),
        )
        manager.register(
            HookEvent.POST_TOOL_USE,
            Hook(
                "b", HookType.PYTHON, HookEvent.POST_TOOL_USE, callback=lambda d: True
            ),
        )

        manager.clear(HookEvent.PRE_TOOL_USE)
        assert len(manager.get_hooks(HookEvent.PRE_TOOL_USE)) == 0
        assert len(manager.get_hooks(HookEvent.POST_TOOL_USE)) == 1

    def test_clear_all(self) -> None:
        manager = HookManager()
        manager.register(
            HookEvent.PRE_TOOL_USE,
            Hook("a", HookType.PYTHON, HookEvent.PRE_TOOL_USE, callback=lambda d: True),
        )
        manager.register(
            HookEvent.POST_TOOL_USE,
            Hook(
                "b", HookType.PYTHON, HookEvent.POST_TOOL_USE, callback=lambda d: True
            ),
        )

        manager.clear()
        assert len(manager.list_events()) == 0

    def test_list_events(self) -> None:
        manager = HookManager()
        manager.register(
            HookEvent.PRE_TOOL_USE,
            Hook("a", HookType.PYTHON, HookEvent.PRE_TOOL_USE, callback=lambda d: True),
        )
        manager.register(
            HookEvent.AUDIT_LOG,
            Hook("b", HookType.PYTHON, HookEvent.AUDIT_LOG, callback=lambda d: True),
        )

        events = manager.list_events()
        assert HookEvent.PRE_TOOL_USE in events
        assert HookEvent.AUDIT_LOG in events


class TestAggregatedResult:
    def test_blocked_property(self) -> None:
        result = AggregatedHookResult(continue_execution=False)
        assert result.blocked

    def test_not_blocked(self) -> None:
        result = AggregatedHookResult(continue_execution=True)
        assert not result.blocked


class TestHookTypeEnums:
    def test_hook_types(self) -> None:
        assert HookType.PYTHON == "python"
        assert HookType.COMMAND == "command"
        assert HookType.HTTP == "http"
        assert HookType.PROMPT == "prompt"

    def test_hook_events(self) -> None:
        assert HookEvent.PRE_TOOL_USE == "pre_tool_use"
        assert HookEvent.POST_TOOL_USE == "post_tool_use"
        assert HookEvent.SESSION_START == "session_start"


class TestDefaultHooks:
    def test_register_default_hooks(self) -> None:
        from octopus.core.hooks import register_default_hooks

        manager = HookManager()
        register_default_hooks(manager)

        pre_hooks = manager.get_hooks(HookEvent.PRE_TOOL_USE)
        post_hooks = manager.get_hooks(HookEvent.POST_TOOL_USE)

        # Should have permission_check and rollback_checkpoint in pre
        assert len(pre_hooks) >= 2
        assert any(h.name == "permission_check" for h in pre_hooks)
        assert any(h.name == "rollback_checkpoint" for h in pre_hooks)

        # Should have audit_log in post
        assert len(post_hooks) >= 1
        assert any(h.name == "audit_log" for h in post_hooks)
