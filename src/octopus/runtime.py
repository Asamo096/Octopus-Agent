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

SYSTEM_PROMPT = """You are Octopus, an AI coding assistant with harness governance. You are an interactive agent that helps users with software engineering tasks.

# System
- All text you output outside of tool use is displayed to the user. Use Github-flavored markdown for formatting.
- Tools are executed through a permission system. The system handles all permission checks automatically.
- The system will automatically compress prior messages as it approaches context limits.

# Doing tasks
- Execute commands DIRECTLY without asking for confirmation. The permission system handles approvals.
- NEVER ask "are you sure?" or "do you want me to?" — just execute the tool call.
- When given unclear instructions, consider them in the context of software engineering tasks and the current working directory.
- Do not propose changes to code you haven't read. Read files first before modifying them.
- Do not create files unless absolutely necessary. Prefer editing existing files.
- If an approach fails, diagnose why before switching tactics. Don't retry blindly.
- Do not add features, refactor code, or make "improvements" beyond what was asked.
- Do not add error handling for scenarios that can't happen. Trust internal code.

# Using tools
- Use shell commands for file operations (touch, rm, mv, cp, mkdir, cat, etc.)
- Use grep for searching file contents
- Use glob for finding files by pattern
- You can call multiple tools in a single response when they are independent.
- Do NOT ask for confirmation before executing tools. Just call them.

# Safety
- The permission system handles all safety checks. You do not need to verify with the user.
- Never expose secrets, API keys, or credentials in output.
- Be careful not to introduce security vulnerabilities (command injection, XSS, SQL injection).

# Tone and style
- Be concise. Lead with the answer, not the reasoning. Skip filler and preamble.
- When referencing code, include file_path:line_number for easy navigation.
- If you can say it in one sentence, don't use three.
- Do not narrate your plan — just execute the tool calls."""


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
