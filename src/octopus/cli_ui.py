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
    permission_mode: str = "default",
) -> None:
    """Display the Octopus startup banner with ASCII art logo."""
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

    # SESSION
    if session_id:
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

    # Run the application
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
            _render_tool_output(tool_name or tc.name, result, args or tc.arguments)


def _render_tool_output(tool_name: str, output: str, args: str | None = None) -> None:
    """Render tool output with per-tool-type styling.

    - bash/shell: dim panel with command as title
    - read/file_read: syntax-highlighted if extension recognized
    - grep/search: cyan panel
    - edit/file_edit: green panel
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

    # bash / shell commands
    if name_lower in ("shell", "bash", "execute_command", "run_command"):
        # Show command as title if available
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
    elif name_lower in ("read", "file_read", "read_file"):
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
            Panel(truncated, title=tool_name, border_style="cyan", expand=False),
            highlight=False,
        )

    # edit / file_edit
    elif name_lower in ("edit", "file_edit", "edit_file"):
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
    console.print("[dim]The Octopus CLI runs in the foreground as an interactive session.[/]")
    console.print("[dim]To run tasks in the background, consider:[/]")
    console.print()
    console.print("  [info]1.[/] Use the Octopus Desktop GUI (Tauri app) for background tasks")
    console.print("  [info]2.[/] Run `octopus cli \"your prompt\"` for one-shot non-interactive mode")
    console.print("  [info]3.[/] Use shell job control: [dim]octopus cli \"task\" &[/]")
    console.print()


# ---------------------------------------------------------------------------
# Spinner (simple text-based)
# ---------------------------------------------------------------------------


class ThinkingSpinner:
    """Simple thinking indicator for processing states."""

    def __init__(self, message: str = "Thinking") -> None:
        self.message = message
        self._start_time = 0.0

    def __enter__(self) -> ThinkingSpinner:
        self._start_time = time.monotonic()
        console.print(f"[dim]{self.message}...[/]", end="", highlight=False)
        return self

    def __exit__(self, *args: object) -> None:
        # Clear the thinking line
        console.print(f"\r{' ' * (len(self.message) + 10)}\r", end="", highlight=False)


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


def print_status_bar(permission_mode: str = "default") -> None:
    """Print the bottom status bar showing current mode and shortcuts.

    Format (claude-code style):
        ⏸ manual mode on · esc to interrupt · ← for agents
        ⏵⏵ auto mode on (shift+tab to cycle) · esc to interrupt · ← for agents
    """
    mode_info = _MODE_DISPLAY.get(permission_mode, _MODE_DISPLAY["default"])
    icon = mode_info["icon"]
    label = mode_info["label"]
    color = mode_info["color"]
    hint = mode_info["hint"]

    # Print status bar
    console.print(
        f"\n[{color}]{icon}[/{color}] [{color}]{label}[/{color}] [dim]· {hint} · ← for agents[/dim]",
        highlight=False,
    )


# ---------------------------------------------------------------------------
# Terminal Split Screen Manager
# ---------------------------------------------------------------------------


class TerminalSplit:
    """Manages a split terminal with fixed status bar at bottom.

    Uses ANSI escape sequences to create a scroll region above
    a fixed status line at the bottom of the terminal.

    Usage:
        split = TerminalSplit()
        split.setup()           # Initialize split screen
        split.print_status_bar(...)  # Update bottom bar
        split.cleanup()         # Restore terminal on exit
    """

    def __init__(self) -> None:
        self._rows: int = 0
        self._cols: int = 0
        self._active: bool = False

    def _get_terminal_size(self) -> tuple[int, int]:
        """Get terminal rows and columns."""
        import shutil

        size = shutil.get_terminal_size()
        return size.lines, size.columns

    def setup(self) -> None:
        """Set up split terminal with scroll region."""
        import sys

        self._rows, self._cols = self._get_terminal_size()
        if self._rows < 3:
            return

        # Set scroll region: rows 1 to (rows-2), leaving last 2 rows for status
        scroll_bottom = self._rows - 2
        sys.stdout.write(f"\033[1;{scroll_bottom}r")  # Set scroll region
        sys.stdout.write(f"\033[{self._rows};1H")      # Move cursor to bottom
        sys.stdout.write("\033[2K")                      # Clear status line
        sys.stdout.write(f"\033[{self._rows - 1};1H")  # Move to second-to-last
        sys.stdout.write("\033[2K")                      # Clear separator line
        sys.stdout.write("\033[1;1H")                    # Move cursor to top
        sys.stdout.flush()
        self._active = True

    def cleanup(self) -> None:
        """Restore terminal to normal mode."""
        import sys

        if not self._active:
            return

        # Reset scroll region to full screen
        sys.stdout.write(f"\033[1;{self._rows}r")
        sys.stdout.write(f"\033[{self._rows};1H")
        sys.stdout.flush()
        self._active = False

    def update_status(
        self,
        permission_mode: str = "default",
        *,
        model: str = "",
        session_id: str = "",
        extra_info: str = "",
    ) -> None:
        """Update the fixed status bar at the bottom."""
        import sys

        if not self._active:
            return

        mode_info = _MODE_DISPLAY.get(permission_mode, _MODE_DISPLAY["default"])
        icon = mode_info["icon"]
        label = mode_info["label"]
        color = mode_info["color"]
        hint = mode_info["hint"]

        # Build status line
        status_parts = [
            f"{icon} {label}",
            f"· {hint}",
            "· ← for agents",
        ]
        if model:
            status_parts.insert(0, f"model: {model}")
        if session_id:
            status_parts.append(f"· session: {session_id[:8]}")
        if extra_info:
            status_parts.append(f"· {extra_info}")

        status_text = " ".join(status_parts)

        # Save cursor position, move to status line, print, restore
        sys.stdout.write("\0337")                          # Save cursor
        sys.stdout.write(f"\033[{self._rows};1H")          # Move to bottom
        sys.stdout.write("\033[2K")                         # Clear line

        # Apply color based on mode
        color_codes = {
            "yellow": "\033[33m",
            "blue": "\033[34m",
            "green": "\033[32m",
            "cyan": "\033[36m",
        }
        color_code = color_codes.get(color, "\033[37m")
        sys.stdout.write(f"{color_code}{status_text}\033[0m")

        # Print separator line above status
        sys.stdout.write(f"\033[{self._rows - 1};1H")
        sys.stdout.write("\033[2K")
        sys.stdout.write(f"\033[90m{'─' * self._cols}\033[0m")  # Dim separator

        sys.stdout.write("\0338")                          # Restore cursor
        sys.stdout.flush()

    def clear_status(self) -> None:
        """Clear the status bar area."""
        import sys

        if not self._active:
            return

        sys.stdout.write("\0337")                          # Save cursor
        sys.stdout.write(f"\033[{self._rows - 1};1H")      # Move to separator
        sys.stdout.write("\033[2K")                         # Clear separator
        sys.stdout.write(f"\033[{self._rows};1H")          # Move to status
        sys.stdout.write("\033[2K")                         # Clear status
        sys.stdout.write("\0338")                          # Restore cursor
        sys.stdout.flush()
