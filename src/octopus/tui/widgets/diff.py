"""Diff preview widget — colored diff display for file edits."""

from __future__ import annotations

import difflib

from textual.widgets import Static


class DiffPreview(Static):
    """Display a colored unified diff between old and new text."""

    def __init__(
        self,
        old_text: str,
        new_text: str,
        file_path: str = "",
        **kwargs: object,
    ) -> None:
        super().__init__(**kwargs)
        self._old_text = old_text
        self._new_text = new_text
        self._file_path = file_path

    def on_mount(self) -> None:
        """Render the diff on mount."""
        self._render()

    def _render(self) -> None:
        """Generate and display the diff."""
        old_lines = self._old_text.splitlines(keepends=False)
        new_lines = self._new_text.splitlines(keepends=False)

        diff = list(
            difflib.unified_diff(
                old_lines,
                new_lines,
                fromfile=f"a/{self._file_path}",
                tofile=f"b/{self._file_path}",
                lineterm="",
            )
        )

        if not diff:
            self.update("[dim]No changes[/]")
            return

        # Limit to 40 lines
        display_lines: list[str] = []
        for line in diff[:40]:
            if line.startswith("+++") or line.startswith("---"):
                display_lines.append(f"[bold]{line}[/]")
            elif line.startswith("+"):
                display_lines.append(f"[green]{line}[/]")
            elif line.startswith("-"):
                display_lines.append(f"[red]{line}[/]")
            elif line.startswith("@@"):
                display_lines.append(f"[cyan]{line}[/]")
            else:
                display_lines.append(f"[dim]{line}[/]")

        if len(diff) > 40:
            display_lines.append(f"[dim]... +{len(diff) - 40} more lines[/]")

        self.update("\n".join(display_lines))


def render_diff_static(
    old_text: str,
    new_text: str,
    file_path: str,
    max_lines: int = 30,
) -> str:
    """Render a diff as a Rich-markup string for use in Static widgets.

    Args:
        old_text: Original content.
        new_text: New content.
        file_path: Path for display.
        max_lines: Maximum lines to show.

    Returns:
        Rich-markup formatted string.
    """
    old_lines = old_text.splitlines(keepends=False)
    new_lines = new_text.splitlines(keepends=False)

    diff = list(
        difflib.unified_diff(
            old_lines,
            new_lines,
            fromfile=f"a/{file_path}",
            tofile=f"b/{file_path}",
            lineterm="",
        )
    )

    if not diff:
        return "[dim]No changes[/]"

    result: list[str] = [f"[bold]Diff: {file_path}[/]"]
    for line in diff[:max_lines]:
        if line.startswith("+++") or line.startswith("---"):
            result.append(f"[bold]{line}[/]")
        elif line.startswith("+"):
            result.append(f"[green]{line}[/]")
        elif line.startswith("-"):
            result.append(f"[red]{line}[/]")
        elif line.startswith("@@"):
            result.append(f"[cyan]{line}[/]")
        else:
            result.append(f"[dim]{line}[/]")

    if len(diff) > max_lines:
        result.append(f"[dim]... +{len(diff) - max_lines} more lines[/]")

    return "\n".join(result)
