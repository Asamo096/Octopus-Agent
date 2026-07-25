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
    {"name": "/model", "description": "Fetch and select model from provider"},
    {"name": "/config", "description": "Show or edit configuration"},
    {"name": "/config show", "description": "Show current configuration"},
    {"name": "/config set model", "description": "Set model name"},
    {"name": "/config set provider", "description": "Set provider name"},
    {"name": "/config set base_url", "description": "Set provider base URL"},
    {"name": "/config set api_key", "description": "Set API key"},
    {"name": "/tokens", "description": "Show estimated token count"},
    {"name": "/compact", "description": "Force conversation compaction"},
    {"name": "/reset", "description": "Reset conversation history"},
    {"name": "/clear", "description": "Clear screen"},
    {"name": "/exit", "description": "Exit interactive mode"},
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
| `/clear` | Clear screen |
| `/reset` | Reset conversation |
| `/tokens` | Show token estimate |
| `/compact` | Force compaction |
| `/model` | Fetch & select model from provider |
| `/config` | Show/edit configuration |
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
| `Ctrl+C` | Cancel / Exit |
| `Ctrl+D` | Exit |
"""
    console.print(Markdown(help_text))


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
