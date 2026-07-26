"""Tool output rendering widget — per-tool-type display."""

from __future__ import annotations

from textual.widgets import Static


def format_tool_output(
    tool_name: str,
    output: str,
    file_path: str | None = None,
    max_lines: int = 20,
) -> str:
    """Format a tool's output for display in the TUI.

    Returns a Rich-markup string appropriate for Static widget content.

    Args:
        tool_name: Name of the tool (shell, read_file, grep, etc.)
        output: Raw tool output text.
        file_path: Optional file path for read/write tools.
        max_lines: Maximum lines to display.

    Returns:
        Rich-markup formatted string.
    """
    if not output or not output.strip():
        return "[dim](empty output)[/]"

    name_lower = tool_name.lower()
    lines = output.strip().splitlines()
    truncated = len(lines) > max_lines
    display = "\n".join(lines[:max_lines])

    if name_lower in ("shell", "bash", "execute_command"):
        header = f"[bold cyan]Shell Output[/]"
        trailer = f"\n[dim]... +{len(lines) - max_lines} lines[/]" if truncated else ""
        return f"{header}\n[dim green]{display}[/]{trailer}"

    if name_lower in ("read", "read_file", "file_read"):
        header = f"[bold cyan]File: {file_path or 'unknown'}[/]"
        trailer = f"\n[dim]... +{len(lines) - max_lines} lines[/]" if truncated else ""
        return f"{header}\n[dim]{display}[/]{trailer}"

    if name_lower in ("grep", "search"):
        header = f"[bold cyan]Search Results[/]"
        trailer = f"\n[dim]... +{len(lines) - max_lines} lines[/]" if truncated else ""
        return f"{header}\n[dim]{display}[/]{trailer}"

    if name_lower in ("write", "write_file", "file_write"):
        header = f"[bold green]Written: {file_path or 'unknown'}[/]"
        return header

    if name_lower in ("edit", "edit_file", "file_edit"):
        header = f"[bold green]Edited: {file_path or 'unknown'}[/]"
        return header

    if name_lower in ("git",):
        header = f"[bold cyan]Git[/]"
        trailer = f"\n[dim]... +{len(lines) - max_lines} lines[/]" if truncated else ""
        return f"{header}\n[dim]{display}[/]{trailer}"

    # Default
    trailer = f"\n[dim]... +{len(lines) - max_lines} lines[/]" if truncated else ""
    return f"[dim]{display}[/]{trailer}"


class ToolOutput(Static):
    """Widget displaying a formatted tool execution result."""

    def __init__(
        self,
        tool_name: str,
        output: str,
        file_path: str | None = None,
        **kwargs: object,
    ) -> None:
        super().__init__(**kwargs)
        self._tool_name = tool_name
        self._output = output
        self._file_path = file_path

    def on_mount(self) -> None:
        """Render the tool output on mount."""
        formatted = format_tool_output(
            self._tool_name, self._output, self._file_path
        )
        self.update(formatted)
