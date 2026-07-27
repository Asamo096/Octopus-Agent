"""Chat input widget — multi-line input with inline slash command suggestions.

Enter: submit  |  Shift+Enter: newline  |  /: shows matching commands
Up/Down: navigate suggestions  |  Tab: accept  |  Escape: dismiss
"""

from __future__ import annotations

from typing import Any

from textual import events
from textual.message import Message
from textual.widgets import TextArea


SLASH_COMMANDS = [
    ("/help", "Show available commands"),
    ("/audit", "View audit trail of all agent actions"),
    ("/clear", "Clear conversation, start new session"),
    ("/compact", "Force conversation compaction"),
    ("/config", "Show current configuration"),
    ("/context", "Show context usage breakdown"),
    ("/theme", "Switch theme: dark / light / contrast"),
    ("/effort", "Set reasoning effort: low / medium / high / max"),
    ("/model", "Fetch and select model from provider"),
    ("/tokens", "Show estimated token count"),
    ("/reset", "Reset conversation history"),
    ("/cd", "Change working directory"),
    ("/exit", "Quit Octopus"),
]


class ChatInput(TextArea):
    """Multi-line text input with inline slash command suggestions.

    Suggestions appear in a sibling #suggestions widget that sits
    above the input in the layout — no popup, no overlay.
    """

    class Submitted(Message):
        def __init__(self, text: str) -> None:
            super().__init__()
            self.text = text

    class Cancelled(Message):
        pass

    class SuggestionsChanged(Message):
        """Emitted when suggestions should be shown/hidden/updated."""

        def __init__(self, text: str = "") -> None:
            super().__init__()
            self.text = text

    def __init__(self, **kwargs: object) -> None:
        super().__init__(language=None, show_line_numbers=False, **kwargs)
        self._history: list[str] = []
        self._history_index = -1
        self._suggestion_index = 0
        self._debounce_timer: Any = None
        self._last_sent_text = ""

    @property
    def suggestion_index(self) -> int:
        return self._suggestion_index

    @suggestion_index.setter
    def suggestion_index(self, val: int) -> None:
        self._suggestion_index = val

    # ---- key handling ---------------------------------------------------

    def on_key(self, event: events.Key) -> None:
        text = self.text.strip()

        # Slash mode: up/down navigate suggestions, tab/enter accept
        if text.startswith("/"):
            if event.key in ("up", "down"):
                matches = self._get_matches(text)
                if matches:
                    if event.key == "up":
                        self._suggestion_index = (
                            self._suggestion_index - 1
                        ) % len(matches)
                    else:
                        self._suggestion_index = (
                            self._suggestion_index + 1
                        ) % len(matches)
                    self.post_message(
                        self.SuggestionsChanged(text)
                    )
                event.prevent_default()
                event.stop()
                return

            if event.key == "tab":
                matches = self._get_matches(text)
                if matches and self._suggestion_index < len(matches):
                    cmd = matches[self._suggestion_index][0]
                    self.text = cmd + " "
                    self.action_cursor_line_end()
                    self._suggestion_index = 0
                    self.post_message(self.SuggestionsChanged(""))
                event.prevent_default()
                event.stop()
                return

            if event.key == "escape":
                self._suggestion_index = 0
                self.post_message(self.SuggestionsChanged(""))
                event.prevent_default()
                event.stop()
                return

        # Enter: submit (slash or normal)
        if event.key == "enter":
            self._suggestion_index = 0
            self.post_message(self.SuggestionsChanged(""))
            text_val = self.text.strip()
            if text_val:
                self._history.append(text_val)
                self._history_index = len(self._history)
                self.clear()
                self.post_message(self.Submitted(text_val))
            event.prevent_default()
            event.stop()
            return

        # Escape: cancel
        if event.key == "escape":
            self.post_message(self.Cancelled())
            event.prevent_default()
            event.stop()
            return

        # History navigation (empty input)
        if event.key == "up" and len(self.text) == 0:
            if self._history and self._history_index > 0:
                self._history_index -= 1
                self.text = self._history[self._history_index]
            event.prevent_default()
            event.stop()
            return
        if event.key == "down" and len(self.text) == 0:
            if self._history_index < len(self._history) - 1:
                self._history_index += 1
                self.text = self._history[self._history_index]
            event.prevent_default()
            event.stop()
            return

    # ---- text change → debounced suggestions --------------------------

    def on_text_area_changed(self, event: TextArea.Changed) -> None:
        if self._debounce_timer is not None:
            self._debounce_timer.stop()
        self._debounce_timer = self.set_timer(0.08, self._send_suggestions)

    def _send_suggestions(self) -> None:
        text = self.text.strip()
        if text == self._last_sent_text:
            return
        self._last_sent_text = text
        if text.startswith("/"):
            self._suggestion_index = 0
            self.post_message(self.SuggestionsChanged(text))
        elif not text.startswith("/"):
            self.post_message(self.SuggestionsChanged(""))

    # ---- matching ------------------------------------------------------

    def _get_matches(self, prefix: str) -> list[tuple[str, str]]:
        prefix_lower = prefix.lower()
        return [
            (cmd, desc)
            for cmd, desc in SLASH_COMMANDS
            if cmd.lower().startswith(prefix_lower)
        ][:8]


# -----------------------------------------------------------------------
# Inline suggestion display helper (called from app)
# -----------------------------------------------------------------------


def build_suggestions_text(
    input_text: str, suggestion_index: int
) -> str:
    """Build the Rich markup text for inline suggestions.

    Returns empty string if no suggestions to show.
    """
    if not input_text.startswith("/"):
        return ""
    prefix_lower = input_text.lower()
    matches = [
        (cmd, desc)
        for cmd, desc in SLASH_COMMANDS
        if cmd.lower().startswith(prefix_lower)
    ][:8]
    if not matches:
        return ""

    parts = []
    for i, (cmd, desc) in enumerate(matches):
        if i == suggestion_index:
            parts.append(f"[bold #00afff]> {cmd}[/]  [dim]{desc}[/]")
        else:
            parts.append(f"[dim]  {cmd}  {desc}[/]")
    return "\n".join(parts)
