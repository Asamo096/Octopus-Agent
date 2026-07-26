"""Status bar widget — permission mode, sandbox state, tokens, cost."""

from __future__ import annotations

from textual.widgets import Static


class StatusBar(Static):
    """Bottom status bar showing mode, sandbox, tokens, cost."""

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
        self._cost = 0.0
        self._tool_calls = 0

    def update_mode(self, mode: str) -> None:
        self._mode = mode
        self._refresh()

    def update_stats(
        self,
        tokens: int = 0,
        cost: float = 0.0,
        tool_calls: int = 0,
    ) -> None:
        self._tokens = tokens
        self._cost = cost
        self._tool_calls = tool_calls
        self._refresh()

    def _refresh(self) -> None:
        label, color = self._MODE_INFO.get(self._mode, ("manual", "yellow"))
        parts = [f"[{color} bold]{label}[/]"]

        if self._tokens > 0:
            parts.append(f"tokens: [dim]{self._tokens:,}[/]")
        if self._cost > 0:
            parts.append(f"cost: [dim]${self._cost:.4f}[/]")
        if self._tool_calls > 0:
            tw = "tool" if self._tool_calls == 1 else "tools"
            parts.append(f"[dim]{self._tool_calls} {tw}[/]")
        parts.append("[dim]ctrl+p mode | esc interrupt | ctrl+c quit[/]")
        self.update("  ".join(parts))
