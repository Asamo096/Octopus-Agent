"""CLI UI rendering — styled output matching claude-code patterns.

Provides consistent, clean terminal output with:
- Codex-style banner with system info
- Separator-based prompt with cursor positioning
- Tool call rendering with box drawing
- Status line with cost/tokens/model
- Markdown rendering for assistant responses
- Spinner for processing states
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.theme import Theme

if TYPE_CHECKING:
    pass

# Custom theme matching claude-code's color palette
OCTOPUS_THEME = Theme(
    {
        "info": "cyan",
        "warning": "yellow",
        "error": "bold red",
        "success": "green",
        "dim": "dim white",
        "accent": "bold #00afff",
        "tool.name": "bold cyan",
        "tool.args": "dim white",
        "tool.result": "dim green",
        "separator": "dim #444444",
        "prompt.arrow": "bold #00afff",
        "cost": "dim #888888",
        "model": "dim #666666",
        "tokens": "dim #888888",
    }
)

console = Console(theme=OCTOPUS_THEME)


# ---------------------------------------------------------------------------
# Banner
# ---------------------------------------------------------------------------


def display_banner(
    *,
    model: str = "claude-sonnet-4-20250514",
    workspace: str | None = None,
    session_id: str | None = None,
    session_title: str | None = None,
    permission_mode: str = "default",
) -> None:
    """Display the Octopus startup banner with ASCII art logo.

    Args:
        model: Model name to display (shortened automatically).
        workspace: Current working directory.
        session_id: Unique session identifier.
        session_title: Human-readable session title (generated from first message).
        permission_mode: Active permission mode label.
    """
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
        console.print(f"[accent]{line}[/]")

    # Info line — MODEL | PERMISSION
    model_display = _shorten_model(model) if model else "(none)"
    info_parts = [
        f"MODEL: [info]{model_display}[/]",
        f"PERMISSION: [info]{permission_mode}[/]",
    ]
    console.print(" | ".join(info_parts))

    # PATH
    if workspace:
        console.print(f"PATH: [dim]{workspace}[/]")

    # SESSION — show title if available, otherwise ID
    if session_title:
        console.print(f"SESSION: [dim]{session_title}[/]")
    elif session_id:
        console.print(f"SESSION: [dim]{session_id}[/]")

    console.print()


def _shorten_model(model: str) -> str:
    """Shorten model name for display."""
    # claude-sonnet-4-20250514 -> claude-sonnet-4
    # gpt-4o-2024-08-06 -> gpt-4o
    for suffix in ("-20250514", "-2024-08-06", "-2024-06-20", "-latest"):
        if model.endswith(suffix):
            return model[: -len(suffix)]
    return model


# ---------------------------------------------------------------------------
# Arrow Key Selection Menu
# ---------------------------------------------------------------------------


def select_option(
    options: list[str],
    *,
    title: str | None = None,
    initial_index: int = 0,
) -> str | None:
    """Display a selection menu with arrow key navigation.

    Uses prompt_toolkit for proper terminal handling (no leaked keypresses).

    Args:
        options: List of string options to select from
        title: Optional title to display above options
        initial_index: Index of initially selected option

    Returns:
        Selected option string, or None if cancelled
    """
    from prompt_toolkit.key_binding import KeyBindings

    if not options:
        return None

    selected_index = initial_index
    result: str | None = None
    cancelled = False

    kb = KeyBindings()

    @kb.add("up")
    def _move_up(event: object) -> None:
        nonlocal selected_index
        selected_index = (selected_index - 1) % len(options)

    @kb.add("down")
    def _move_down(event: object) -> None:
        nonlocal selected_index
        selected_index = (selected_index + 1) % len(options)

    @kb.add("enter")
    def _confirm(event: object) -> None:
        nonlocal result
        result = options[selected_index]
        event.app.exit(result=result)  # type: ignore

    @kb.add("escape")
    def _cancel(event: object) -> None:
        nonlocal cancelled
        cancelled = True
        event.app.exit(result=None)  # type: ignore

    @kb.add("c-c")
    def _cancel_ctrl_c(event: object) -> None:
        nonlocal cancelled
        cancelled = True
        event.app.exit(result=None)  # type: ignore

    # Build the menu display
    def _build_menu_text() -> str:
        lines = []
        if title:
            lines.append(f"  {title}")
            lines.append("")
        for i, opt in enumerate(options):
            if i == selected_index:
                lines.append(f"  > {opt}")
            else:
                lines.append(f"    {opt}")
        lines.append("")
        lines.append("  [up/down] Navigate  [enter] Confirm  [esc] Cancel")
        return "\n".join(lines)

    # Use Application for proper terminal handling
    from prompt_toolkit.application import Application
    from prompt_toolkit.layout import Layout
    from prompt_toolkit.layout.containers import HSplit, Window
    from prompt_toolkit.layout.controls import FormattedTextControl

    # Create a control that renders our menu
    class MenuControl(FormattedTextControl):
        def __init__(self) -> None:
            super().__init__(self._get_text)

        def _get_text(self) -> str:
            return _build_menu_text()

    # Create application
    layout = Layout(
        HSplit(
            [
                Window(content=MenuControl()),
            ]
        )
    )

    app: Application = Application(
        layout=layout,
        key_bindings=kb,
        full_screen=False,
        erase_when_done=True,
    )

    # Run the application — handle both sync and async contexts
    import asyncio
    try:
        asyncio.get_running_loop()
        # Inside running event loop — delegate to a new thread
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(1) as pool:
            future = pool.submit(app.run)
            future.result()
    except RuntimeError:
        # No running event loop — sync run
        app.run()

    return result


# ---------------------------------------------------------------------------
# Slash Command Autocomplete
# ---------------------------------------------------------------------------

# Available slash commands with descriptions
SLASH_COMMANDS: list[dict[str, str]] = [
    {"name": "/help", "description": "Show available commands"},
    {"name": "/init", "description": "Generate OCTOPUS.md with project docs"},
    {"name": "/add-dir", "description": "Add a working directory to the session"},
    {"name": "/background", "description": "Background task info"},
    {"name": "/branch", "description": "Save state and start new branch"},
    {"name": "/btw", "description": "Ask a side question"},
    {"name": "/cd", "description": "Change working directory"},
    {"name": "/clear", "description": "Clear conversation, start new session"},
    {"name": "/color", "description": "Change prompt bar color"},
    {"name": "/compact", "description": "Force conversation compaction"},
    {"name": "/config", "description": "Show or edit configuration"},
    {"name": "/config show", "description": "Show current configuration"},
    {"name": "/config set model", "description": "Set model name"},
    {"name": "/config set provider", "description": "Set provider name"},
    {"name": "/config set base_url", "description": "Set provider base URL"},
    {"name": "/config set api_key", "description": "Set API key"},
    {"name": "/context", "description": "Show context usage as a colored grid"},
    {"name": "/model", "description": "Fetch and select model from provider"},
    {"name": "/tokens", "description": "Show estimated token count"},
    {"name": "/reset", "description": "Reset conversation history"},
    {"name": "/exit", "description": "Exit interactive mode"},
]


# Color presets for the prompt bar (cycled by /color)
COLOR_PRESETS: list[dict[str, str]] = [
    {"name": "blue", "style": "bold #00afff", "label": "Blue (default)"},
    {"name": "green", "style": "bold #00d75f", "label": "Green"},
    {"name": "purple", "style": "bold #af5fff", "label": "Purple"},
    {"name": "orange", "style": "bold #ff8700", "label": "Orange"},
    {"name": "red", "style": "bold #ff5555", "label": "Red"},
    {"name": "cyan", "style": "bold #00d7d7", "label": "Cyan"},
    {"name": "white", "style": "bold #ffffff", "label": "White"},
    {"name": "gray", "style": "bold #808080", "label": "Gray"},
]


class SlashCommandCompleter:
    """Prompt-toolkit completer for slash commands."""

    def __init__(self) -> None:
        self.commands = SLASH_COMMANDS

    def get_completions(self, document: object, complete_event: object) -> list:
        """Return completions for the current input."""
        from prompt_toolkit.completion import Completion

        text = document.text  # type: ignore
        completions = []
        for cmd in self.commands:
            if cmd["name"].startswith(text) or text in cmd["description"].lower():
                completions.append(
                    Completion(
                        cmd["name"],
                        start_position=-len(text),
                        display_meta=cmd["description"],
                    )
                )
        return completions


# ---------------------------------------------------------------------------
# Separator & Prompt
# ---------------------------------------------------------------------------


def print_separator() -> None:
    """Print a full-width separator line."""
    console.print("─" * console.width, style="separator")


def print_prompt_arrow() -> None:
    """Print the assistant response arrow (not the user input prompt)."""
    console.print("[prompt.arrow]❯[/] ", end="", highlight=False)


# ---------------------------------------------------------------------------
# Tool Call Rendering
# ---------------------------------------------------------------------------


@dataclass
class ToolCallDisplay:
    """Tracks a tool call for display purposes."""

    name: str
    arguments: str
    start_time: float = field(default_factory=time.monotonic)
    result: str | None = None
    error: str | None = None
    end_time: float | None = None

    @property
    def duration(self) -> float | None:
        if self.end_time is not None:
            return self.end_time - self.start_time
        return None

    @property
    def duration_str(self) -> str:
        d = self.duration
        if d is None:
            return ""
        if d < 1.0:
            return f"{d * 1000:.0f}ms"
        return f"{d:.1f}s"


def print_tool_call_start(name: str, arguments: str) -> ToolCallDisplay:
    """Print tool call start indicator.

    Format:
    ┌ tool_name(arg1, arg2, ...)
    """
    tc = ToolCallDisplay(name=name, arguments=arguments)

    # Format arguments for display
    args_display = _format_tool_args(arguments)

    console.print(
        f"[dim]┌[/] [tool.name]{name}[/]([tool.args]{args_display}[/])", highlight=False
    )
    return tc


def print_tool_call_result(
    tc: ToolCallDisplay,
    result: str,
    *,
    is_error: bool = False,
    tool_name: str | None = None,
    args: str | None = None,
    tool_data: dict[str, object] | None = None,
) -> None:
    """Print tool call result with per-tool-type rendering.

    Format:
    └ OK (123ms)
    └ Error: message (45ms)
    """
    tc.end_time = time.monotonic()
    tc.result = result
    tc.error = result if is_error else None

    duration_str = tc.duration_str

    if is_error:
        console.print(
            f"[dim]└[/] [red]Error[/] [dim]({duration_str})[/]",
            highlight=False,
        )
        # Show truncated error
        error_preview = result[:200] + "..." if len(result) > 200 else result
        console.print(f"  [dim]{error_preview}[/]", highlight=False)
    else:
        console.print(
            f"[dim]└[/] [green]OK[/] [dim]({duration_str})[/]",
            highlight=False,
        )
        # Render output with per-tool-type styling
        if result and result.strip():
            _render_tool_output(
                tool_name or tc.name,
                result,
                args or tc.arguments,
                tool_data=tool_data,
            )


def _render_tool_output(
    tool_name: str,
    output: str,
    args: str | None = None,
    tool_data: dict[str, object] | None = None,
) -> None:
    """Render tool output with per-tool-type styling.

    - bash/shell: dim panel with command as title
    - read/file_read: syntax-highlighted if extension recognized
    - grep/search: cyan panel
    - edit/file_edit: green panel, diff preview if old/new content available
    - default: dim text, truncated to 15 lines
    """
    name_lower = tool_name.lower()
    max_lines = 15

    def _truncate(text: str, limit: int) -> str:
        lines = text.strip().splitlines()
        if len(lines) <= limit:
            return text.strip()
        return "\n".join(lines[:limit]) + f"\n... +{len(lines) - limit} more lines"

    # Extract file path from args if available
    file_path = None
    if args:
        try:
            import json as _json

            parsed = _json.loads(args)
            file_path = parsed.get("path") or parsed.get("file")
        except (ValueError, TypeError):
            pass

    # Also check tool_data for file_path
    if not file_path and tool_data:
        file_path = str(tool_data.get("file_path", ""))

    # bash / shell commands
    if name_lower in ("shell", "bash", "execute_command", "run_command"):
        cmd_title = None
        if args:
            try:
                import json as _json

                parsed = _json.loads(args)
                cmd_title = parsed.get("command", "")
                if cmd_title and len(cmd_title) > 60:
                    cmd_title = cmd_title[:57] + "..."
            except (ValueError, TypeError):
                pass
        truncated = _truncate(output, max_lines)
        console.print(
            Panel(
                truncated,
                title=cmd_title or "shell",
                border_style="dim",
                expand=False,
            ),
            highlight=False,
        )

    # read / file_read
    elif name_lower in ("read", "read_file", "file_read"):
        if file_path:
            ext = file_path.rsplit(".", 1)[-1].lower() if "." in file_path else ""
            if ext in (
                "py",
                "python",
                "js",
                "ts",
                "jsx",
                "tsx",
                "rs",
                "go",
                "rb",
                "java",
                "c",
                "cpp",
                "h",
                "hpp",
                "css",
                "html",
                "json",
                "yaml",
                "yml",
                "toml",
                "sh",
                "bash",
                "zsh",
                "sql",
                "md",
                "xml",
                "swift",
                "kt",
                "scala",
                "lua",
                "r",
            ):
                try:
                    from rich.syntax import Syntax

                    syntax = Syntax(
                        output.strip(),
                        ext,
                        theme="monokai",
                        line_numbers=True,
                    )
                    console.print(syntax, highlight=False)
                    return
                except Exception:
                    pass
        # Fallback: dim panel
        truncated = _truncate(output, max_lines)
        console.print(
            Panel(
                truncated, title=file_path or "read", border_style="dim", expand=False
            ),
            highlight=False,
        )

    # grep / search
    elif name_lower in ("grep", "search", "search_files", "find_files"):
        truncated = _truncate(output, max_lines)
        console.print(
            Panel(truncated, title="Search results", border_style="cyan", expand=False),
            highlight=False,
        )

    # write_file
    elif name_lower in ("write", "write_file", "file_write"):
        truncated = _truncate(output, max_lines)
        console.print(
            Panel(
                truncated,
                title=file_path or "write",
                border_style="green",
                expand=False,
            ),
            highlight=False,
        )

    # edit / file_edit — try to show diff if metadata has old/new strings
    elif name_lower in ("edit", "edit_file", "file_edit"):
        old_content = None
        new_content = None
        if tool_data:
            old_content = str(tool_data.get("old_string", ""))
            new_content = str(tool_data.get("new_string", ""))
            file_path = str(tool_data.get("file_path", file_path or ""))

        if old_content and new_content and file_path:
            render_diff(old_content, new_content, file_path)
        else:
            truncated = _truncate(output, max_lines)
            console.print(
                Panel(
                    truncated,
                    title=file_path or "edit",
                    border_style="green",
                    expand=False,
                ),
                highlight=False,
            )

    # default: dim text with truncation
    else:
        truncated = _truncate(output, max_lines)
        console.print(f"  [dim]{truncated}[/]", highlight=False)


def print_tool_call_output(output: str, *, max_lines: int = 10) -> None:
    """Print tool output, truncated to max_lines."""
    lines = output.strip().split("\n")
    if not lines or (len(lines) == 1 and not lines[0].strip()):
        return

    truncated = len(lines) > max_lines
    display_lines = lines[:max_lines]

    for line in display_lines:
        console.print(f"  [dim]{line}[/]", highlight=False)

    if truncated:
        remaining = len(lines) - max_lines
        console.print(f"  [dim]... +{remaining} more lines[/]", highlight=False)


def _format_tool_args(arguments: str, max_len: int = 60) -> str:
    """Format tool arguments for display."""
    if not arguments:
        return ""

    # Remove JSON braces for cleaner display
    args = arguments.strip()
    if args.startswith("{") and args.endswith("}"):
        args = args[1:-1].strip()

    # Truncate
    if len(args) > max_len:
        args = args[: max_len - 3] + "..."

    return args


# ---------------------------------------------------------------------------
# Message Rendering
# ---------------------------------------------------------------------------


def print_assistant_text(text: str) -> None:
    """Print assistant response text with markdown rendering."""
    if not text.strip():
        return

    # Render as markdown for rich formatting
    md = Markdown(text)
    console.print(md)


def print_assistant_text_stream(text: str) -> None:
    """Print a streaming chunk of assistant text (no markdown, raw)."""
    console.print(text, end="", highlight=False)


def print_assistant_markdown(text: str) -> None:
    """Re-render full assistant response as markdown after streaming.

    This follows the OpenHarness pattern: stream raw tokens first for
    responsiveness, then re-render with proper markdown formatting.
    """
    if not text.strip():
        return

    # Clear the streamed raw text by moving cursor up and re-rendering
    # Rich's Markdown handles code blocks, headers, lists, tables, etc.
    md = Markdown(text)
    console.print(md)


def print_stream_newline() -> None:
    """Print a newline after streaming completes."""
    console.print()


def print_error(message: str) -> None:
    """Print an error message."""
    console.print(f"[error]Error:[/] {message}")


def print_warning(message: str) -> None:
    """Print a warning message."""
    console.print(f"[warning]Warning:[/] {message}")


def print_info(message: str) -> None:
    """Print an info message."""
    console.print(f"[dim]{message}[/]")


def print_success(message: str) -> None:
    """Print a success message."""
    console.print(f"[success]OK[/] {message}")


def print_status(message: str) -> None:
    """Print a status/compaction message."""
    console.print(f"\n[dim]{message}[/]", highlight=False)


# ---------------------------------------------------------------------------
# Status Line (post-turn)
# ---------------------------------------------------------------------------


@dataclass
class TurnStats:
    """Statistics for a single turn."""

    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cost_usd: float = 0.0
    duration_ms: int = 0
    model: str = ""
    tool_calls: int = 0


def print_status_line(stats: TurnStats) -> None:
    """Print the status line after a turn.

    Format:
    tokens: 1.2k in / 345 out | cost: $0.0042 | 2.3s | 3 tools
    """
    parts = []

    # Tokens
    if stats.input_tokens > 0 or stats.output_tokens > 0:
        in_str = _format_token_count(stats.input_tokens)
        out_str = _format_token_count(stats.output_tokens)
        token_parts = [f"{in_str} in", f"{out_str} out"]
        if stats.cache_read_tokens > 0:
            cache_str = _format_token_count(stats.cache_read_tokens)
            token_parts.append(f"{cache_str} cache")
        parts.append(f"tokens: {' / '.join(token_parts)}")

    # Cost
    if stats.cost_usd > 0:
        parts.append(f"cost: ${stats.cost_usd:.4f}")

    # Duration
    if stats.duration_ms > 0:
        if stats.duration_ms < 1000:
            parts.append(f"{stats.duration_ms}ms")
        else:
            parts.append(f"{stats.duration_ms / 1000:.1f}s")

    # Tool calls
    if stats.tool_calls > 0:
        tool_word = "tool" if stats.tool_calls == 1 else "tools"
        parts.append(f"{stats.tool_calls} {tool_word}")

    if parts:
        console.print(f"[cost]{' | '.join(parts)}[/]", highlight=False)


def _format_token_count(count: int) -> str:
    """Format token count for display."""
    if count >= 1_000_000:
        return f"{count / 1_000_000:.1f}m"
    if count >= 10_000:
        return f"{count / 1_000:.0f}k"
    if count >= 1_000:
        return f"{count / 1_000:.1f}k"
    return str(count)


# ---------------------------------------------------------------------------
# Slash Command Help
# ---------------------------------------------------------------------------


def print_help() -> None:
    """Print help text for slash commands."""
    help_text = """### Commands

| Command | Description |
|---------|-------------|
| `/help` | Show this help |
| `/init` | Generate OCTOPUS.md with project docs |
| `/add-dir <path>` | Add a working directory to the session |
| `/background` | Info about background mode (not available in CLI) |
| `/branch` | Save state and start a new conversation branch |
| `/btw <question>` | Ask a side question without interrupting main flow |
| `/cd <path>` | Change working directory |
| `/clear` | Clear conversation and start a new session |
| `/color <name/cycle>` | Change prompt bar color |
| `/compact` | Force conversation compaction |
| `/config` | Show/edit configuration |
| `/context` | Show context usage as a colored grid |
| `/model` | Fetch & select model from provider |
| `/tokens` | Show token estimate |
| `/reset` | Reset conversation |
| `/exit` | Exit |

### Config

| Command | Description |
|---------|-------------|
| `/config show` | Show current config |
| `/config set model <m>` | Set model name |
| `/config set provider <p>` | Set provider name |
| `/config set base_url <u>` | Set provider base URL |
| `/config set api_key <key>` | Set API_KEY |

### Shortcuts

| Key | Action |
|-----|--------|
| `Shift+Tab` | Cycle permission mode |
| `Ctrl+C` | Cancel / Exit |
| `Ctrl+D` | Exit |
"""
    console.print(Markdown(help_text))


# ---------------------------------------------------------------------------
# Context Grid Visualization
# ---------------------------------------------------------------------------


def print_context_grid(
    *,
    system_tokens: int,
    message_tokens: int,
    tool_tokens: int,
    total_tokens: int,
    max_context: int = 128_000,
) -> None:
    """Display context usage as a colored grid.

    Renders a visual bar showing how much of the context window is used,
    broken down by category (system, messages, tools).
    """
    from rich.table import Table

    # Calculate percentages
    usage_pct = min(total_tokens / max_context, 1.0) if max_context > 0 else 0.0
    system_pct = system_tokens / max_context if max_context > 0 else 0
    message_pct = message_tokens / max_context if max_context > 0 else 0
    tool_pct = tool_tokens / max_context if max_context > 0 else 0

    # Build the bar
    bar_width = 50
    filled = int(usage_pct * bar_width)
    system_end = int(system_pct * bar_width)
    message_end = system_end + int(message_pct * bar_width)
    tool_end = message_end + int(tool_pct * bar_width)

    bar_chars: list[str] = []
    for i in range(bar_width):
        if i >= filled:
            bar_chars.append("[dim]#[/]")
        elif i < system_end:
            bar_chars.append("[cyan]#[/]")
        elif i < message_end:
            bar_chars.append("[green]#[/]")
        elif i < tool_end:
            bar_chars.append("[yellow]#[/]")
        else:
            bar_chars.append("[dim]#[/]")

    bar = "".join(bar_chars)

    # Color the percentage based on usage
    if usage_pct < 0.5:
        pct_style = "green"
    elif usage_pct < 0.8:
        pct_style = "yellow"
    else:
        pct_style = "red"

    console.print()
    console.print(f"[accent]Context Usage[/] [{pct_style}]{usage_pct:.0%}[/]")
    console.print(f"  [{bar}]")
    console.print()

    # Breakdown table
    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column("Category", style="dim")
    table.add_column("Tokens", justify="right")
    table.add_column("Percent", justify="right")
    table.add_column("Bar", min_width=20)

    def _make_mini_bar(pct: float, color: str) -> str:
        w = 20
        f = int(pct * w)
        return f"[{color}]" + "#" * f + "[/][dim]" + "." * (w - f) + "[/]"

    table.add_row(
        "System prompt",
        f"{system_tokens:,}",
        f"{system_pct:.1%}",
        _make_mini_bar(system_pct, "cyan"),
    )
    table.add_row(
        "Messages",
        f"{message_tokens:,}",
        f"{message_pct:.1%}",
        _make_mini_bar(message_pct, "green"),
    )
    table.add_row(
        "Tool results",
        f"{tool_tokens:,}",
        f"{tool_pct:.1%}",
        _make_mini_bar(tool_pct, "yellow"),
    )
    table.add_row(
        "Total",
        f"{total_tokens:,}",
        f"{usage_pct:.1%}",
        "",
    )
    table.add_row(
        "Remaining",
        f"{max_context - total_tokens:,}",
        f"{1 - usage_pct:.1%}",
        "",
    )

    console.print(table)
    console.print()


# ---------------------------------------------------------------------------
# Background / btw Helpers
# ---------------------------------------------------------------------------


def print_background_message() -> None:
    """Print message explaining that background mode is not feasible in CLI."""
    console.print()
    console.print("[warning]Background mode is not available in the CLI.[/]")
    console.print()
    console.print(
        "[dim]The Octopus CLI runs in the foreground as an interactive session.[/]"
    )
    console.print("[dim]To run tasks in the background, consider:[/]")
    console.print()
    console.print(
        "  [info]1.[/] Use the Octopus Desktop GUI (Tauri app) for background tasks"
    )
    console.print(
        '  [info]2.[/] Run `octopus cli "your prompt"` for one-shot non-interactive mode'
    )
    console.print('  [info]3.[/] Use shell job control: [dim]octopus cli "task" &[/]')
    console.print()


# ---------------------------------------------------------------------------
# Spinner with animated frames and activity description
# ---------------------------------------------------------------------------


class ThinkingSpinner:
    """Animated spinner with activity description for processing states.

    Usage:
        spinner = ThinkingSpinner("Thinking")
        with spinner as s:
            s.update_activity("Reading src/main.py")
            # ... do work, calling s.tick() periodically ...
    """

    _FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]

    def __init__(self, message: str = "Thinking") -> None:
        self.message = message
        self._start_time = 0.0
        self._current_activity: str | None = None
        self._frame_index = 0

    def update_activity(self, activity: str) -> None:
        """Update the activity description (e.g., 'Reading src/main.py')."""
        self._current_activity = activity
        self._frame_index = 0

    def tick(self) -> None:
        """Advance spinner frame and redraw."""
        frame = self._FRAMES[self._frame_index % len(self._FRAMES)]
        self._frame_index += 1
        desc = self._current_activity or self.message
        # Truncate to fit terminal width
        max_desc = console.width - 4 if console.width else 60
        if len(desc) > max_desc:
            desc = desc[:max_desc - 3] + "..."
        console.print(
            f"\r{frame} [dim]{desc}[/]", end="", highlight=False
        )

    def __enter__(self) -> ThinkingSpinner:
        self._start_time = time.monotonic()
        self.tick()
        return self

    def __exit__(self, *args: object) -> None:
        # Clear spinner line
        console.print("\r" + " " * (console.width or 80) + "\r", end="", highlight=False)


# ---------------------------------------------------------------------------
# Diff preview for file edits
# ---------------------------------------------------------------------------


def render_diff(
    old_text: str,
    new_text: str,
    file_path: str,
    *,
    max_lines: int = 30,
) -> None:
    """Render a colored diff between old and new text.

    Args:
        old_text: Original file content before edit.
        new_text: New file content after edit.
        file_path: Path of the file being edited (for display).
        max_lines: Maximum number of diff lines to show.
    """
    import difflib

    if not old_text or not new_text:
        return

    # Use difflib. Differ for a cleaner line-by-line view
    d = difflib.Differ()
    old_lines = old_text.splitlines(keepends=True)
    new_lines = new_text.splitlines(keepends=True)

    # Calculate differences
    diff_lines = list(d.compare(
        [line.rstrip("\n") for line in old_lines],
        [line.rstrip("\n") for line in new_lines],
    ))

    if not diff_lines:
        return

    # Limit to max_lines with a buffer around changes
    changed_lines: list[int] = []
    for i, line in enumerate(diff_lines):
        if line.startswith(("+ ", "- ", "? ")):
            changed_lines.append(i)

    # If no changes detected, show nothing
    if not changed_lines:
        return

    # Create a windowed view around changes (show context + changes)
    context_padding = 3
    to_show: set[int] = set()
    for idx in changed_lines:
        start = max(0, idx - context_padding)
        end = min(len(diff_lines), idx + context_padding + 1)
        to_show.update(range(start, end))

    console.print(f"[bold]Diff: {file_path}[/]")
    shown = 0
    last_shown = -2
    for i in sorted(to_show):
        if shown >= max_lines:
            break
        # Print separator when skipping lines
        if i > last_shown + 1 and last_shown >= 0:
            console.print(f"[dim]  ... ({i - last_shown - 1} lines skipped)[/]")
        line = diff_lines[i]
        if line.startswith("+ "):
            console.print(f"[green]{line}[/]")
        elif line.startswith("- "):
            console.print(f"[red]{line}[/]")
        elif line.startswith("? "):
            console.print(f"[yellow]{line}[/]")
        elif line.startswith("  "):
            console.print(f"[dim]{line}[/]")
        else:
            console.print(f"[cyan]{line}[/]")
        shown += 1
        last_shown = i

    if shown >= max_lines and len(to_show) > max_lines:
        console.print(f"[dim]  ... (diff truncated, {len(to_show) - shown} more changes)[/]")


# ---------------------------------------------------------------------------
# Compact summary display
# ---------------------------------------------------------------------------


def print_compact_summary(
    messages_before: int,
    messages_after: int,
    tokens_before: int,
    tokens_after: int,
    strategy: str,
    preserved_context: str | None = None,
) -> None:
    """Display compact summary after conversation compaction.

    Shows what was saved and which strategy was applied.
    """
    saved = tokens_before - tokens_after
    pct = int((saved / tokens_before) * 100) if tokens_before > 0 else 0

    console.print()
    console.print("[accent]Conversation compacted[/]")
    console.print(f"  Messages: {messages_before} -> {messages_after}")
    console.print(
        f"  Tokens: {_format_token_count(tokens_before)} -> "
        f"{_format_token_count(tokens_after)} ({pct}% saved)"
    )
    console.print(f"  Strategy: {strategy}")

    if preserved_context:
        console.print(f'  Context: "{preserved_context}"')
    console.print()


# ---------------------------------------------------------------------------
# Session title generation
# ---------------------------------------------------------------------------


def generate_session_title(first_message: str, max_len: int = 50) -> str:
    """Generate a session title from the first user message.

    Strips markdown formatting, takes the first line, and truncates.
    """
    # Take first line, strip markdown formatting
    title = first_message.split("\n")[0].strip()
    # Remove common markdown characters
    title = title.replace("*", "").replace("_", "").replace("`", "").replace("#", "")
    # Remove leading/trailing whitespace from stripped markdown
    title = title.strip()
    # Truncate
    if len(title) > max_len:
        title = title[:max_len - 3] + "..."
    return title or "New session"


# ---------------------------------------------------------------------------
# Tool use summary (collapsed)
# ---------------------------------------------------------------------------


def print_tool_summary(tool_calls: list[ToolCallDisplay]) -> None:
    """Print a collapsed summary of multiple tool calls.

    Groups by tool name: "3 tool uses (2 read, 1 grep)"
    """
    if len(tool_calls) <= 1:
        return

    # Group by tool name
    counts: dict[str, int] = {}
    for tc in tool_calls:
        counts[tc.name] = counts.get(tc.name, 0) + 1

    # Format: "3 tool uses (2 read, 1 grep)"
    total = len(tool_calls)
    parts = [f"{count} {name}" for name, count in sorted(counts.items())]
    summary = f"{total} tool uses ({', '.join(parts)})"

    console.print(f"[dim]{summary}[/dim]")


# ---------------------------------------------------------------------------
# Effort / thinking indicator
# ---------------------------------------------------------------------------


def print_effort_indicator(effort: str) -> None:
    """Display the thinking effort level when configured.

    Shows: [thinking: high] with color-coded effort level.
    """
    effort_colors = {
        "low": "dim",
        "medium": "yellow",
        "high": "cyan",
        "max": "magenta",
    }
    color = effort_colors.get(effort, "dim")
    console.print(f"[{color}][thinking: {effort}][/{color}]", end=" ")


# ---------------------------------------------------------------------------
# Status Bar (bottom of terminal)
# ---------------------------------------------------------------------------

_MODE_DISPLAY = {
    "default": {
        "icon": "⏸",
        "label": "manual mode",
        "color": "yellow",
        "hint": "esc to interrupt",
    },
    "plan": {
        "icon": "⏸",
        "label": "plan mode",
        "color": "blue",
        "hint": "shift+tab to cycle · esc to interrupt",
    },
    "full_auto": {
        "icon": "⏵⏵",
        "label": "auto mode on",
        "color": "green",
        "hint": "shift+tab to cycle · esc to interrupt",
    },
    "accept_edits": {
        "icon": "⏵⏵",
        "label": "accept edits on",
        "color": "cyan",
        "hint": "shift+tab to cycle",
    },
}


def get_status_bar_text(permission_mode: str = "default") -> str:
    """Get status bar text for prompt_toolkit bottom_toolbar."""
    mode_info = _MODE_DISPLAY.get(permission_mode, _MODE_DISPLAY["default"])
    icon = mode_info["icon"]
    label = mode_info["label"]
    hint = mode_info["hint"]
    return f" {icon} {label} · {hint} · ← for agents "


def get_status_bar_style(permission_mode: str = "default") -> str:
    """Get prompt_toolkit style string for status bar."""
    mode_info = _MODE_DISPLAY.get(permission_mode, _MODE_DISPLAY["default"])
    color = mode_info["color"]
    color_map = {
        "yellow": "#ffff00",
        "blue": "#5f87ff",
        "green": "#5faf5f",
        "cyan": "#00afd7",
    }
    fg = color_map.get(color, "#ffffff")
    return f"bg:#303030 {fg} bold"


def print_status_bar(permission_mode: str = "default") -> None:
    """Print the bottom status bar (fallback for non-prompt-toolkit contexts)."""
    text = get_status_bar_text(permission_mode)
    mode_info = _MODE_DISPLAY.get(permission_mode, _MODE_DISPLAY["default"])
    color = mode_info["color"]
    console.print(f"\n[{color}]{text}[/]", highlight=False)
