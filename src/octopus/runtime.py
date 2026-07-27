"""Shared runtime — utilities, single-prompt mode, and CLI subcommands.

All interactive mode is handled by the TUI (tui_runtime.py).
This module provides shared helpers used by both the TUI and the
non-interactive CLI commands (single prompt, code, session, config).
"""

from __future__ import annotations

import json
import os
import re
import time
import uuid
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.live import Live
from rich.markdown import Markdown
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from octopus.config.manager import load_auth, load_config, save_auth, save_config
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

console = Console()

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """You are Octopus, a professional AI coding assistant with harness governance.

<system>
You help users with software engineering tasks using tools for files, shell,
search, and git. All tool calls pass through a permission system — you do NOT
need to ask for confirmation. The system auto-compresses conversation history.

# Critical Rules

1. USE TOOLS to accomplish tasks. NEVER describe what you "would do" — call the
   tools, then report the actual results.
2. When a tool SUCCEEDS, move on. NEVER retry a successful operation.
3. When a tool FAILS, diagnose the error. Try a DIFFERENT approach.
4. Read files BEFORE editing them.
5. Write complete, working code. No placeholders or TODOs.
6. One write per file. Use edit_file for subsequent changes.

# File Operations

| Task               | Tool       | Example                                    |
|--------------------|------------|--------------------------------------------|
| Create new file    | write_file | write_file(path="app.py", content="...")   |
| Modify file        | edit_file  | edit_file(path, old_string, new_string)    |
| Read file          | read_file  | read_file(path="src/main.py")             |
| Delete file        | shell rm   | shell(command="rm old.txt")               |
| List files         | shell ls   | shell(command="ls -la")                   |
| Search code        | grep       | grep(pattern="def foo", path="src/")      |
| Find files         | glob       | glob(pattern="**/*.py")                   |

# Shell Commands

Use shell for: git, npm, pip, pytest, cargo, go, make, ls, mkdir, rm, mv, cp,
cat, grep, find, python, node, and any CLI tools.

Check exit codes. Non-zero = failure. Diagnose and try a different approach.
For writing file content, prefer write_file over shell heredocs.

# Writing Code

- Read files you plan to modify first
- Write complete files with imports and error handling
- Follow existing code style and conventions
- Use edit_file for precise changes, matching exact indentation
- Test after writing: run the test suite or a quick smoke test

# Response Style

- After tool execution, describe what was done with actual results
- Be concise. Lead with the answer, not the reasoning
- Reference code as file_path:line_number
- Use markdown: ```code blocks```, **bold**, lists

# Limits

- Maximum 50 tool-calling turns per message
- Never retry the same operation more than twice
- If stuck after 3 attempts, explain the problem to the user
</system>"""


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _get_db_path() -> Path:
    db_dir = Path.home() / ".octopus"
    db_dir.mkdir(parents=True, exist_ok=True)
    return db_dir / "octopus.db"


def _resolve_model(model_arg: str | None) -> str:
    if model_arg:
        return _prefix_model_for_litellm(model_arg)
    config = load_config()
    if config.model:
        return _prefix_model_for_litellm(config.model)
    return ""


def _prefix_model_for_litellm(model: str) -> str:
    if "/" in model:
        return model
    config = load_config()
    if config.model_provider:
        return f"{config.model_provider}/{model}"
    return model


def _resolve_permission_mode(mode_str: str) -> PermissionMode:
    mapping = {
        "default": PermissionMode.DEFAULT,
        "plan": PermissionMode.PLAN,
        "accept_edits": PermissionMode.ACCEPT_EDITS,
        "full_auto": PermissionMode.FULL_AUTO,
    }
    return mapping.get(mode_str, PermissionMode.DEFAULT)


def _shorten_model(model: str) -> str:
    for suffix in ("-20250514", "-2024-08-06", "-2024-06-20", "-latest"):
        if model.endswith(suffix):
            return model[: -len(suffix)]
    return model


def _strip_xml_artifacts(text: str) -> str:
    for tag in ("tool_call", "function=.*?", "thinking", "tool_result"):
        text = re.sub(f"<{tag}>.*?</{tag}>", "", text, flags=re.DOTALL)
    text = re.sub(r"<\|.*?\|>", "", text)
    return text


# ---------------------------------------------------------------------------
# Banner (for single-prompt mode)
# ---------------------------------------------------------------------------


def print_banner(
    model: str = "",
    workspace: str | None = None,
    permission_mode: str = "default",
    session_id: str | None = None,
) -> None:
    logo = [
        " ██████╗  ██████╗████████╗ ██████╗ ██████╗ ██╗   ██╗███████╗",
        "██╔═══██╗██╔════╝╚══██╔══╝██╔═══██╗██╔══██╗██║   ██║██╔════╝",
        "██║   ██║██║        ██║   ██║   ██║██████╔╝██║   ██║███████╗",
        "██║   ██║██║        ██║   ██║   ██║██╔═══╝ ██║   ██║╚════██║",
        "╚██████╔╝╚██████╗   ██║   ╚██████╔╝██║     ╚██████╔╝███████║",
        " ╚═════╝  ╚═════╝   ╚═╝    ╚═════╝ ╚═╝      ╚═════╝ ╚══════╝",
    ]
    console.print()
    for line in logo:
        console.print(f"[bold #00afff]{line}[/]")
    model_display = _shorten_model(model) if model else "(none)"
    parts = [f"MODEL: [cyan]{model_display}[/]", f"PERMISSION: [cyan]{permission_mode}[/]"]
    console.print(" | ".join(parts))
    if workspace:
        console.print(f"PATH: [dim]{workspace}[/]")
    if session_id:
        console.print(f"SESSION: [dim]{session_id}[/]")
    console.print()


# ---------------------------------------------------------------------------
# Single-prompt mode
# ---------------------------------------------------------------------------


async def _setup_runtime(
    *,
    model: str | None = None,
    permission_mode: str = "default",
    workspace: Path | None = None,
    permission_prompt: Any = None,
) -> tuple[Kernel, ToolRegistry, LiteLLMProvider, Context]:
    ws = workspace or Path.cwd()
    db_path = _get_db_path()
    pm = _resolve_permission_mode(permission_mode)

    kernel = Kernel(db_path=db_path, workspace=ws, permission_mode=pm)
    if permission_prompt is not None:
        kernel._permission_prompt = permission_prompt
    await kernel.initialize()

    registry = ToolRegistry()
    for fn in [
        register_filesystem_tools,
        register_shell_tool,
        register_git_tool,
        register_diff_tools,
        register_search_tools,
    ]:
        fn(registry, kernel)

    config = load_config()
    auth = load_auth()
    api_key = auth.openai_api_key
    if api_key and config.model_provider:
        os.environ[f"{config.model_provider.upper()}_API_KEY"] = api_key

    base_url: str | None = None
    for p in config.model_providers.values():
        if p.base_url:
            base_url = p.base_url
            break

    provider = LiteLLMProvider(api_key=api_key, base_url=base_url)

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
    """Run a single prompt and print the response (non-interactive)."""
    kernel, registry, provider, ctx = await _setup_runtime(
        model=model, permission_mode=permission_mode,
    )
    try:
        conversation = ConversationContext(
            session_id=ctx.session_id,
            system_prompt=SYSTEM_PROMPT,
            model=_resolve_model(model),
        )
        conversation.ensure_system_message()
        conversation.add_message(Message(role=Role.USER, content=prompt))

        compaction = CompactionEngine()
        collected_text: list[str] = []
        _first = False

        with Live(
            console.status("[dim]Thinking...[/]", spinner="dots"),
            console=console, refresh_per_second=8, transient=True,
        ) as live:
            async for event in run_query(
                conversation.messages, provider, kernel, registry, ctx,
                model=_resolve_model(model), conversation=conversation,
                compaction=compaction,
            ):
                if not _first and event.type in (
                    StreamEventType.TEXT, StreamEventType.TOOL_CALL,
                ):
                    _first = True
                    live.stop()
                if event.type == StreamEventType.TEXT:
                    collected_text.append(event.text or "")
                    console.print(event.text or "", end="", highlight=False)
                elif event.type == StreamEventType.TOOL_CALL:
                    tc = event.tool_call
                    if tc:
                        console.print(f"\n[bold cyan]{tc.name}[/] ", end="", highlight=False)
                elif event.type == StreamEventType.ERROR:
                    live.stop()
                    console.print(f"\n[red]Error: {event.error}[/]")

        if collected_text:
            console.print()

        full = _strip_xml_artifacts("".join(collected_text))
        if full.strip():
            console.print(Markdown(full))

        await conversation.save(kernel.state)
    finally:
        await kernel.shutdown()


# ---------------------------------------------------------------------------
# Subcommand handlers
# ---------------------------------------------------------------------------


async def code_init_async(path: str) -> None:
    ws = Path(path).resolve()
    octopus_dir = ws / ".octopus"
    octopus_dir.mkdir(parents=True, exist_ok=True)
    config_path = octopus_dir / "config.yaml"
    if not config_path.exists():
        config_path.write_text(
            "# Octopus Agent workspace configuration\n"
            "permissions:\n  mode: default\n  allowed_paths:\n"
            f"    - {ws}/**\n"
            "sandbox:\n  enabled: true\n  allowed_paths:\n"
            f"    - {ws}/**\n"
        )
        console.print(f"[green]Created[/] {config_path}")
    else:
        console.print(f"[dim]Config already exists at {config_path}[/]")
    console.print(f"[green]Workspace initialized at[/] {ws}")
    console.print(f"[dim]Database: {_get_db_path()}[/]")


async def show_audit_logs_async(limit: int = 20, tool: str | None = None) -> None:
    from octopus.core.audit import AuditFilters, AuditLogger

    db_path = _get_db_path()
    if not db_path.exists():
        console.print("[yellow]No audit logs found.[/]")
        return
    audit = AuditLogger(db_path=db_path)
    try:
        events = await audit.query(AuditFilters(limit=limit, tool=tool))
        if not events:
            console.print("[yellow]No audit events found.[/]")
            return
        table = Table(title="Audit Log", show_lines=True)
        table.add_column("Time", style="dim", width=20)
        table.add_column("Tool", style="cyan", width=15)
        table.add_column("Decision", width=15)
        table.add_column("Duration", width=10)
        table.add_column("Args", max_width=40)
        for e in events:
            time_str = e.timestamp.strftime("%Y-%m-%d %H:%M:%S")
            d_style = "green" if e.permission_decision == "ALLOWED" else "red"
            args_str = json.dumps(e.args)
            if len(args_str) > 40:
                args_str = args_str[:37] + "..."
            table.add_row(time_str, e.tool, f"[{d_style}]{e.permission_decision}[/]",
                          f"{e.duration:.3f}s", args_str)
        console.print(table)
    finally:
        await audit.close()


async def list_sessions_async() -> None:
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
        table = Table(title="Sessions")
        table.add_column("ID", style="cyan")
        table.add_column("Name")
        table.add_column("Messages", justify="right")
        table.add_column("Created")
        table.add_column("Last Active")
        for s in sessions:
            created = s.start_time.strftime("%Y-%m-%d %H:%M") if s.start_time else "---"
            last = s.last_activity.strftime("%Y-%m-%d %H:%M") if s.last_activity else "---"
            msg_count = len(s.context.get("messages", []))
            table.add_row(s.session_id[:8], s.name or "(unnamed)",
                          str(msg_count), created, last)
        console.print(table)
    finally:
        await state.close()
