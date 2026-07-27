"""Status bar widget — permission mode, tokens, shortcuts."""

from __future__ import annotations

from textual.widgets import Static


class StatusBar(Static):
    """Bottom status bar showing mode, token usage, and shortcuts."""

    _MODE_INFO = {
        "default": ("manual", "yellow"),
        "plan": ("plan", "blue"),
        "full_auto": ("auto", "green"),
        "accept_edits": ("accept edits", "cyan"),
    }

    def __init__(self, **kwargs: object) -> None:
        super().__init__("", **kwargs)
        self._mode = "default"
        self._tokens = 0

    def update_mode(self, mode: str) -> None:
        self._mode = mode
        self._refresh()

    def update_tokens(self, count: int) -> None:
        self._tokens = count
        self._refresh()

    @staticmethod
    def _fmt(n: int) -> str:
        if n >= 1_000_000:
            return f"{n / 1_000_000:.1f}m"
        if n >= 1_000:
            return f"{n / 1_000:.0f}k"
        return str(n)

    def _refresh(self) -> None:
        label, color = self._MODE_INFO.get(self._mode, ("manual", "yellow"))
        parts = [f" [{color} bold]{label}[/]"]
        if self._tokens > 0:
            parts.append(f"[dim]tk:{self._fmt(self._tokens)}[/]")
        parts.append("[dim]ctrl+p mode  ctrl+t theme  esc interrupt  ctrl+c quit[/]")
        self.update("".join(parts))
