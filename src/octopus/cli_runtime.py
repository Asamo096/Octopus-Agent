"""CLI runtime — async helpers that wire the agent loop to the CLI.

This module bridges the synchronous Typer CLI with the async agent loop.
Handles conversation context persistence, auto-compaction, and styled UI
matching claude-code's terminal patterns.
"""

from __future__ import annotations

import json
import time
import uuid
from pathlib import Path

from octopus.cli_ui import (
    ToolCallDisplay,
    TurnStats,
    console,
    display_banner,
    print_assistant_text_stream,
    print_error,
    print_help,
    print_info,
    print_prompt_arrow,
    print_separator,
    print_status,
    print_status_line,
    print_stream_newline,
    print_success,
    print_tool_call_output,
    print_tool_call_result,
    print_tool_call_start,
    print_warning,
)
from octopus.core.kernel import Context, Kernel, PermissionMode
from octopus.loop.compaction import CompactionEngine
from octopus.loop.context import ConversationContext
from octopus.loop.engine import run_query
from octopus.loop.models import Message, Role, StreamEventType
from octopus.providers.litellm_adapter import LiteLLMProvider
from octopus.tools.base import ToolRegistry
from octopus.tools.diff import register_diff_tools
from octopus.tools.filesystem import register_filesystem_tools
from octopus.tools.git import register_git_tool
from octopus.tools.search import register_search_tools
from octopus.tools.shell import register_shell_tool

# Default model
DEFAULT_MODEL = "claude-sonnet-4-20250514"

# System prompt
SYSTEM_PROMPT = (
    "You are Octopus, an AI coding assistant with harness governance. "
    "You help users with coding tasks, file operations, and shell commands. "
    "Be concise, accurate, and helpful. When writing code, follow best practices."
)


def _get_db_path() -> Path:
    """Get the path to the Octopus database."""
    db_dir = Path.home() / ".octopus"
    db_dir.mkdir(parents=True, exist_ok=True)
    return db_dir / "octopus.db"


def _resolve_permission_mode(mode_str: str) -> PermissionMode:
    """Convert string to PermissionMode."""
    mapping = {
        "default": PermissionMode.DEFAULT,
        "plan": PermissionMode.PLAN,
        "full_auto": PermissionMode.FULL_AUTO,
    }
    return mapping.get(mode_str, PermissionMode.DEFAULT)


async def _setup_runtime(
    *,
    model: str | None = None,
    permission_mode: str = "default",
    workspace: Path | None = None,
) -> tuple[Kernel, ToolRegistry, LiteLLMProvider, Context]:
    """Set up kernel, registry, provider, and context."""
    ws = workspace or Path.cwd()
    db_path = _get_db_path()
    pm = _resolve_permission_mode(permission_mode)

    kernel = Kernel(db_path=db_path, workspace=ws, permission_mode=pm)
    await kernel.initialize()

    registry = ToolRegistry()
    register_filesystem_tools(registry, kernel)
    register_shell_tool(registry, kernel)
    register_git_tool(registry, kernel)
    register_diff_tools(registry, kernel)
    register_search_tools(registry, kernel)

    provider = LiteLLMProvider()

    ctx = Context(
        session_id=str(uuid.uuid4()),
        kernel=kernel,
        workspace=ws,
        permission_mode=pm,
    )

    return kernel, registry, provider, ctx


async def run_single_prompt_async(
    prompt: str,
    *,
    model: str | None = None,
    permission_mode: str = "default",
) -> None:
    """Run a single prompt and print the response (non-interactive mode)."""
    kernel, registry, provider, ctx = await _setup_runtime(
        model=model,
        permission_mode=permission_mode,
    )

    try:
        conversation = ConversationContext(
            session_id=ctx.session_id,
            system_prompt=SYSTEM_PROMPT,
            model=model or DEFAULT_MODEL,
        )
        conversation.ensure_system_message()
        conversation.add_message(Message(role=Role.USER, content=prompt))

        compaction = CompactionEngine()

        # Track turn stats
        turn_start = time.monotonic()
        tool_call_count = 0
        collected_text: list[str] = []

        async for event in run_query(
            conversation.messages,
            provider,
            kernel,
            registry,
            ctx,
            model=model or DEFAULT_MODEL,
            conversation=conversation,
            compaction=compaction,
        ):
            if event.type == StreamEventType.TEXT:
                collected_text.append(event.text or "")
                print_assistant_text_stream(event.text or "")
            elif event.type == StreamEventType.TOOL_CALL:
                tc = event.tool_call
                if tc:
                    tool_call_count += 1
                    print_tool_call_start(tc.name, tc.arguments)
            elif event.type == StreamEventType.TOOL_RESULT:
                tr = event.tool_result
                if tr:
                    is_error = tr.is_error if hasattr(tr, "is_error") else False
                    result_text = tr.output if hasattr(tr, "output") else str(tr)
                    # Create a temporary ToolCallDisplay for result display
                    temp_tc = ToolCallDisplay(name="tool", arguments="")
                    temp_tc.start_time = turn_start
                    print_tool_call_result(temp_tc, result_text, is_error=is_error)
                    if result_text and not is_error:
                        print_tool_call_output(result_text)
            elif event.type == StreamEventType.STATUS:
                print_status(event.text or "")
            elif event.type == StreamEventType.ERROR:
                print_error(event.error or "Unknown error")
            elif event.type == StreamEventType.DONE:
                pass

        if collected_text:
            print_stream_newline()

        # Print status line
        duration_ms = int((time.monotonic() - turn_start) * 1000)
        stats = TurnStats(
            duration_ms=duration_ms,
            model=model or DEFAULT_MODEL,
            tool_calls=tool_call_count,
        )
        print_status_line(stats)

        # Persist conversation
        await conversation.save(kernel.state)

    finally:
        await kernel.shutdown()


async def run_interactive_async(
    *,
    model: str | None = None,
    permission_mode: str = "default",
    resume_session: str | None = None,
) -> None:
    """Run the interactive chat loop.

    If resume_session is provided, loads that session's conversation history.
    Otherwise starts a new session.
    """
    kernel, registry, provider, ctx = await _setup_runtime(
        model=model,
        permission_mode=permission_mode,
    )

    compaction = CompactionEngine()

    try:
        # Load or create conversation context
        conversation: ConversationContext | None = None
        if resume_session:
            conversation = await ConversationContext.load(resume_session, kernel.state)
            if conversation:
                conversation.sanitize()
                print_info(f"Resumed session {resume_session[:8]} ({len(conversation.messages)} messages)")
            else:
                print_warning(f"Session {resume_session} not found, starting new.")

        if conversation is None:
            conversation = ConversationContext(
                session_id=ctx.session_id,
                system_prompt=SYSTEM_PROMPT,
                model=model or DEFAULT_MODEL,
            )
            conversation.ensure_system_message()
            await kernel.state.create_session(
                ctx.session_id,
                workspace=str(ctx.workspace) if ctx.workspace else None,
            )

        # Display banner
        display_banner(
            model=model or DEFAULT_MODEL,
            workspace=str(ctx.workspace),
            session_id=ctx.session_id,
            permission_mode=permission_mode,
        )

        # prompt_toolkit session for styled input with proper cursor positioning
        from prompt_toolkit import PromptSession
        from prompt_toolkit.formatted_text import HTML
        from prompt_toolkit.styles import Style

        prompt_style = Style.from_dict({"prompt": "bold #00afff"})
        pt_session: PromptSession[str] = PromptSession()

        # Session cost tracking
        session_cost = 0.0
        session_tokens_in = 0
        session_tokens_out = 0
        session_tool_calls = 0

        while True:
            print_separator()
            try:
                user_input = await pt_session.prompt_async(
                    HTML("<prompt>❯ </prompt>"),
                    style=prompt_style,
                )
            except (EOFError, KeyboardInterrupt):
                console.print("\n[dim]Goodbye![/]")
                console.print(f"[dim]octopus session resume {ctx.session_id}[/]")
                break
            print_separator()

            if not user_input.strip():
                continue

            # Handle slash commands
            if user_input.strip().startswith("/"):
                if _handle_slash_command(
                    user_input.strip(),
                    conversation,
                    session_cost=session_cost,
                    session_tokens_in=session_tokens_in,
                    session_tokens_out=session_tokens_out,
                ):
                    break
                continue

            # Add user message
            conversation.add_message(Message(role=Role.USER, content=user_input))
            console.print()

            # Print assistant response arrow
            print_prompt_arrow()

            # Track turn stats
            turn_start = time.monotonic()
            turn_tool_calls = 0
            collected_text: list[str] = []

            # Track tool calls for display
            current_tool = None

            async for event in run_query(
                conversation.messages,
                provider,
                kernel,
                registry,
                ctx,
                model=model or DEFAULT_MODEL,
                conversation=conversation,
                compaction=compaction,
            ):
                if event.type == StreamEventType.TEXT:
                    collected_text.append(event.text or "")
                    print_assistant_text_stream(event.text or "")

                elif event.type == StreamEventType.TOOL_CALL:
                    tc = event.tool_call
                    if tc:
                        turn_tool_calls += 1
                        session_tool_calls += 1
                        # Finish previous tool if still open
                        if current_tool is not None:
                            print_tool_call_result(current_tool, "")
                        # Print new tool with newline prefix
                        console.print()
                        current_tool = print_tool_call_start(tc.name, tc.arguments)

                elif event.type == StreamEventType.TOOL_RESULT:
                    tr = event.tool_result
                    if tr and current_tool is not None:
                        is_error = getattr(tr, "is_error", False)
                        result_text = getattr(tr, "output", str(tr))
                        print_tool_call_result(current_tool, result_text, is_error=is_error)
                        if result_text and not is_error:
                            print_tool_call_output(result_text)
                        current_tool = None

                elif event.type == StreamEventType.STATUS:
                    print_status(event.text or "")

                elif event.type == StreamEventType.ERROR:
                    print_error(event.error or "Unknown error")

                elif event.type == StreamEventType.DONE:
                    pass

            # Close any unclosed tool
            if current_tool is not None:
                print_tool_call_result(current_tool, "")

            if collected_text:
                print_stream_newline()

            # Print turn status line
            duration_ms = int((time.monotonic() - turn_start) * 1000)
            stats = TurnStats(
                duration_ms=duration_ms,
                model=model or DEFAULT_MODEL,
                tool_calls=turn_tool_calls,
            )
            print_status_line(stats)
            console.print()  # Blank line between turns

            # Persist conversation after each turn
            await conversation.save(kernel.state)

    finally:
        await kernel.shutdown()


def _handle_slash_command(
    command: str,
    conversation: ConversationContext,
    *,
    session_cost: float = 0.0,
    session_tokens_in: int = 0,
    session_tokens_out: int = 0,
) -> bool:
    """Handle slash commands. Returns True if should exit."""
    cmd = command.lower().split()[0]  # Get first word

    if cmd in ("/exit", "/quit", "/q"):
        console.print("[dim]Goodbye![/]")
        return True

    if cmd == "/clear":
        console.clear()
        return False

    if cmd == "/reset":
        conversation.clear()
        conversation.ensure_system_message()
        print_info("Conversation reset.")
        return False

    if cmd == "/tokens":
        tokens = conversation.estimate_tokens()
        console.print(f"[tokens]Estimated tokens: {tokens:,}[/]")
        return False

    if cmd == "/cost":
        console.print(f"[cost]Session cost: ${session_cost:.4f}[/]")
        console.print(f"[tokens]Tokens: {session_tokens_in:,} in / {session_tokens_out:,} out[/]")
        return False

    if cmd == "/compact":
        print_info("Compaction not yet implemented in this session.")
        return False

    if cmd == "/model":
        console.print(f"[model]Current model: {conversation.model}[/]")
        return False

    if cmd == "/help":
        print_help()
        return False

    print_error(f"Unknown command: {command}")
    return False


async def session_resume_async(
    session_id: str,
    *,
    model: str | None = None,
    permission_mode: str = "default",
) -> None:
    """Resume a previous session by ID."""
    db_path = _get_db_path()
    if not db_path.exists():
        print_error("No database found. Run `octopus cli` first.")
        return

    await run_interactive_async(
        model=model,
        permission_mode=permission_mode,
        resume_session=session_id,
    )


async def session_new_async(
    *,
    model: str | None = None,
    permission_mode: str = "default",
) -> None:
    """Start a new session (same as interactive mode, explicitly new)."""
    await run_interactive_async(
        model=model,
        permission_mode=permission_mode,
    )


async def show_audit_logs_async(
    limit: int = 20,
    tool: str | None = None,
) -> None:
    """Display recent audit logs."""
    from octopus.core.audit import AuditFilters, AuditLogger

    db_path = _get_db_path()
    if not db_path.exists():
        print_warning("No audit logs found.")
        return

    audit = AuditLogger(db_path=db_path)
    try:
        filters = AuditFilters(limit=limit, tool=tool)
        events = await audit.query(filters)

        if not events:
            print_warning("No audit events found.")
            return

        from rich.table import Table

        table = Table(title="Audit Log", show_lines=True)
        table.add_column("Time", style="dim", width=20)
        table.add_column("Tool", style="cyan", width=15)
        table.add_column("Decision", width=15)
        table.add_column("Duration", width=10)
        table.add_column("Args", max_width=40)

        for e in events:
            time_str = e.timestamp.strftime("%Y-%m-%d %H:%M:%S")
            decision_style = "green" if e.permission_decision == "ALLOWED" else "red"
            args_str = json.dumps(e.args)
            if len(args_str) > 40:
                args_str = args_str[:37] + "..."
            table.add_row(
                time_str,
                e.tool,
                f"[{decision_style}]{e.permission_decision}[/]",
                f"{e.duration:.3f}s",
                args_str,
            )

        console.print(table)
    finally:
        await audit.close()


async def list_sessions_async() -> None:
    """List all sessions with message counts."""
    from octopus.core.state import StateManager

    db_path = _get_db_path()
    if not db_path.exists():
        print_warning("No sessions found.")
        return

    state = StateManager(db_path=db_path)
    try:
        sessions = await state.list_sessions()
        if not sessions:
            print_warning("No sessions found.")
            return

        from rich.table import Table

        table = Table(title="Sessions")
        table.add_column("ID", style="cyan")
        table.add_column("Name")
        table.add_column("Messages", justify="right")
        table.add_column("Created")
        table.add_column("Last Active")

        for s in sessions:
            created = s.start_time.strftime("%Y-%m-%d %H:%M") if s.start_time else "---"
            last = (
                s.last_activity.strftime("%Y-%m-%d %H:%M") if s.last_activity else "---"
            )
            msg_count = len(s.context.get("messages", []))
            table.add_row(
                s.session_id[:8],
                s.name or "(unnamed)",
                str(msg_count),
                created,
                last,
            )

        console.print(table)
    finally:
        await state.close()


async def code_init_async(path: str) -> None:
    """Initialize a workspace -- create .octopus/ config directory."""
    ws = Path(path).resolve()
    octopus_dir = ws / ".octopus"
    octopus_dir.mkdir(parents=True, exist_ok=True)

    config_path = octopus_dir / "config.yaml"
    if not config_path.exists():
        config_path.write_text(
            "# Octopus Agent workspace configuration\n"
            "permissions:\n"
            "  mode: default\n"
            "  allowed_paths:\n"
            f"    - {ws}/**\n"
            "sandbox:\n"
            "  enabled: true\n"
            f"  allowed_paths:\n"
            f"    - {ws}/**\n"
        )
        print_success(f"Created {config_path}")
    else:
        print_info(f"Config already exists at {config_path}")

    db_path = _get_db_path()
    print_success(f"Workspace initialized at {ws}")
    print_info(f"Database: {db_path}")
