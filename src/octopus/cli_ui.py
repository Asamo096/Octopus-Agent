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
from rich.theme import Theme

if TYPE_CHECKING:
    pass

# Custom theme matching claude-code's color palette
OCTOPUS_THEME = Theme({
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
})

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

    console.print(f"[dim]┌[/] [tool.name]{name}[/]([tool.args]{args_display}[/])", highlight=False)
    return tc


def print_tool_call_result(
    tc: ToolCallDisplay,
    result: str,
    *,
    is_error: bool = False,
) -> None:
    """Print tool call result.

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
| `/cost` | Show session cost |
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
| `/config set api_key <key>` | Set OPENAI_API_KEY |

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
