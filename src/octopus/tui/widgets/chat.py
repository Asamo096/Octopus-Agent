"""Chat message list widget — displays conversation with markdown rendering."""

from __future__ import annotations

from textual.containers import VerticalScroll
from textual.widgets import Static


class ChatLog(VerticalScroll):
    """Scrollable chat message display area.

    Messages are appended as Static widgets with role-specific styling.
    """

    def __init__(self, **kwargs: object) -> None:
        super().__init__(**kwargs)
        self._message_count = 0

    def add_user_message(self, text: str) -> None:
        """Add a user message to the chat log."""
        self._message_count += 1
        msg = Static(
            f"[bold #00afff]>[/] {text}",
            id=f"msg-{self._message_count}",
        )
        msg.add_class("user-message")
        self.mount(msg)
        self.scroll_end(animate=False)

    def add_assistant_message(self, text: str) -> None:
        """Add an assistant message (markdown rendered)."""
        self._message_count += 1
        msg = Static(
            text,
            id=f"msg-{self._message_count}",
        )
        msg.add_class("assistant-message")
        self.mount(msg)
        self.scroll_end(animate=False)

    def add_system_message(self, text: str) -> None:
        """Add a system/info message to the chat log."""
        self._message_count += 1
        msg = Static(
            f"[dim italic]{text}[/]",
            id=f"msg-{self._message_count}",
        )
        msg.add_class("system-message")
        self.mount(msg)
        self.scroll_end(animate=False)

    def add_tool_message(self, tool_name: str, args_str: str, result: str = "") -> None:
        """Add a tool call result to the chat log."""
        self._message_count += 1
        lines = [f"[bold cyan]{tool_name}[/] [dim]({args_str[:80]})[/]"]
        if result:
            preview = result.strip()[:300]
            if len(result.strip()) > 300:
                preview += f"\n[dim]... ({len(result.splitlines())} lines total)[/]"
            lines.append(f"[dim green]{preview}[/]")
        msg = Static("\n".join(lines), id=f"msg-{self._message_count}")
        msg.add_class("tool-message")
        self.mount(msg)
        self.scroll_end(animate=False)

    def add_error_message(self, text: str) -> None:
        """Add an error message to the chat log."""
        self._message_count += 1
        msg = Static(
            f"[bold red]Error:[/] {text}",
            id=f"msg-{self._message_count}",
        )
        msg.add_class("error-message")
        self.mount(msg)
        self.scroll_end(animate=False)

    def clear_messages(self) -> None:
        """Remove all messages from the log."""
        for child in list(self.children):
            if hasattr(child, "id") and child.id and child.id.startswith("msg-"):
                child.remove()
        self._message_count = 0
