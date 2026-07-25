"""CLI runtime — async helpers that wire the agent loop to the CLI.

This module bridges the synchronous Typer CLI with the async agent loop.
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path

from rich.console import Console
from rich.markdown import Markdown

from octopus.core.kernel import Context, Kernel, PermissionMode
from octopus.loop.engine import run_query
from octopus.loop.models import Message, Role, StreamEventType
from octopus.providers.litellm_adapter import LiteLLMProvider
from octopus.tools.base import ToolRegistry
from octopus.tools.filesystem import register_filesystem_tools
from octopus.tools.shell import register_shell_tool

console = Console()

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
    """Run a single prompt and print the response."""
    kernel, registry, provider, ctx = await _setup_runtime(
        model=model,
        permission_mode=permission_mode,
    )

    try:
        messages: list[Message] = [
            Message(role=Role.SYSTEM, content=SYSTEM_PROMPT),
            Message(role=Role.USER, content=prompt),
        ]

        collected: list[str] = []
        async for event in run_query(
            messages,
            provider,
            kernel,
            registry,
            ctx,
            model=model or DEFAULT_MODEL,
        ):
            if event.type == StreamEventType.TEXT:
                collected.append(event.text or "")
                # Print tokens as they arrive (no newline)
                console.print(event.text or "", end="", highlight=False)
            elif event.type == StreamEventType.TOOL_CALL:
                # Show tool call indicator
                tc = event.tool_call
                if tc:
                    console.print(f"\n[dim]⚙ Tool: {tc.name}[/]", highlight=False)
            elif event.type == StreamEventType.ERROR:
                console.print(f"\n[red]Error: {event.error}[/]")
            elif event.type == StreamEventType.DONE:
                pass

        if collected:
            console.print()  # Final newline

    finally:
        await kernel.shutdown()


async def run_interactive_async(
    *,
    model: str | None = None,
    permission_mode: str = "default",
) -> None:
    """Run the interactive chat loop."""
    kernel, registry, provider, ctx = await _setup_runtime(
        model=model,
        permission_mode=permission_mode,
    )

    messages: list[Message] = [
        Message(role=Role.SYSTEM, content=SYSTEM_PROMPT),
    ]

    try:
        while True:
            try:
                user_input = console.input("[bold blue]You>[/] ")
            except (EOFError, KeyboardInterrupt):
                console.print("\n[dim]Goodbye![/]")
                break

            if not user_input.strip():
                continue

            if user_input.strip().startswith("/"):
                if _handle_slash_command(user_input.strip(), messages):
                    break
                continue

            messages.append(Message(role=Role.USER, content=user_input))

            # Show assistant response
            console.print("[bold green]Octopus>[/] ", end="", highlight=False)

            collected: list[str] = []
            async for event in run_query(
                messages,
                provider,
                kernel,
                registry,
                ctx,
                model=model or DEFAULT_MODEL,
            ):
                if event.type == StreamEventType.TEXT:
                    collected.append(event.text or "")
                    console.print(event.text or "", end="", highlight=False)
                elif event.type == StreamEventType.TOOL_CALL:
                    tc = event.tool_call
                    if tc:
                        args_preview = (
                            tc.arguments[:80] + "..."
                            if len(tc.arguments) > 80
                            else tc.arguments
                        )
                        console.print(
                            f"\n[dim]⚙ {tc.name}({args_preview})[/]", highlight=False
                        )
                elif event.type == StreamEventType.ERROR:
                    console.print(f"\n[red]Error: {event.error}[/]")
                elif event.type == StreamEventType.DONE:
                    pass

            if collected:
                console.print()  # Final newline
            console.print()  # Blank line between turns

    finally:
        await kernel.shutdown()


def _handle_slash_command(command: str, messages: list[Message]) -> bool:
    """Handle slash commands. Returns True if should exit."""
    cmd = command.lower()
    if cmd in ("/exit", "/quit", "/q"):
        console.print("[dim]Goodbye![/]")
        return True
    if cmd == "/clear":
        console.clear()
        return False
    if cmd == "/reset":
        messages.clear()
        messages.append(Message(role=Role.SYSTEM, content=SYSTEM_PROMPT))
        console.print("[dim]Conversation reset.[/]")
        return False
    if cmd == "/help":
        console.print(
            Markdown(
                "### Available Commands\n"
                "- `/help` — Show this help\n"
                "- `/clear` — Clear screen\n"
                "- `/reset` — Reset conversation history\n"
                "- `/exit` — Exit interactive mode\n"
            )
        )
        return False
    console.print(f"[red]Unknown command:[/] {command}")
    return False


async def show_audit_logs_async(
    limit: int = 20,
    tool: str | None = None,
) -> None:
    """Display recent audit logs."""
    from octopus.core.audit import AuditFilters, AuditLogger

    db_path = _get_db_path()
    if not db_path.exists():
        console.print("[yellow]No audit logs found.[/]")
        return

    audit = AuditLogger(db_path=db_path)
    try:
        filters = AuditFilters(limit=limit, tool=tool)
        events = await audit.query(filters)

        if not events:
            console.print("[yellow]No audit events found.[/]")
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
    """List all sessions."""
    from octopus.core.state import StateManager

    db_path = _get_db_path()
    if not db_path.exists():
        console.print("[yellow]No sessions found.[/]")
        return

    state = StateManager(db_path=db_path)
    try:
        sessions = await state.list_sessions()
        if not sessions:
            console.print("[yellow]No sessions found.[/]")
            return

        from rich.table import Table

        table = Table(title="Sessions")
        table.add_column("ID", style="cyan")
        table.add_column("Name")
        table.add_column("Created")
        table.add_column("Last Active")

        for s in sessions:
            created = s.start_time.strftime("%Y-%m-%d %H:%M") if s.start_time else "—"
            last = (
                s.last_activity.strftime("%Y-%m-%d %H:%M") if s.last_activity else "—"
            )
            table.add_row(s.session_id[:8], s.name or "(unnamed)", created, last)

        console.print(table)
    finally:
        await state.close()


async def code_init_async(path: str) -> None:
    """Initialize a workspace — create .octopus/ config directory."""
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
        console.print(f"[green]✓[/] Created {config_path}")
    else:
        console.print(f"[dim]Config already exists at {config_path}[/]")

    # Create audit db
    db_path = _get_db_path()
    console.print(f"[green]✓[/] Workspace initialized at {ws}")
    console.print(f"[dim]Database: {db_path}[/]")
