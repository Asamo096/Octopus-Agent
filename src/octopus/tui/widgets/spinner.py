"""Spinner widget — animated activity indicator for tool execution."""

from __future__ import annotations

from textual.widgets import Static


class Spinner(Static):
    """Animated braille spinner showing current activity.

    Usage:
        spinner = Spinner("Thinking...")
        mount(spinner)
        spinner.start()
        spinner.update_activity("Reading src/main.py")
        spinner.stop()
    """

    _FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]

    def __init__(self, message: str = "Thinking...", **kwargs: object) -> None:
        super().__init__(**kwargs)
        self._message = message
        self._activity: str | None = None
        self._frame_index = 0
        self._running = False

    def start(self) -> None:
        """Start the spinner animation."""
        self._running = True
        self._tick()

    def stop(self) -> None:
        """Stop the spinner and clear the display."""
        self._running = False
        self.update("")

    def update_activity(self, activity: str) -> None:
        """Update the activity description."""
        self._activity = activity

    def _tick(self) -> None:
        """Advance spinner frame."""
        if not self._running:
            return
        frame = self._FRAMES[self._frame_index % len(self._FRAMES)]
        self._frame_index += 1
        desc = self._activity or self._message
        max_len = 60
        if len(desc) > max_len:
            desc = desc[: max_len - 3] + "..."
        self.update(f"{frame} [dim]{desc}[/]")
        self.set_timer(0.1, self._tick)
