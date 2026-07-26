"""TUI screen definitions — modal dialogs and overlay screens."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Label, Select, Static


class PermissionDialog(ModalScreen[bool]):
    """Modal dialog for tool permission approval."""

    CSS = """
    PermissionDialog {
        align: center middle;
    }
    #permission-dialog {
        width: 60;
        height: auto;
        background: $panel;
        border: thick $warning;
        padding: 1 2;
    }
    #permission-message {
        margin: 1 0;
    }
    #permission-buttons {
        margin-top: 1;
        align-horizontal: right;
    }
    Button {
        margin-left: 1;
    }
    """

    def __init__(self, tool_name: str, description: str, args_str: str) -> None:
        super().__init__()
        self._tool_name = tool_name
        self._description = description
        self._args_str = args_str

    def compose(self) -> ComposeResult:
        with Vertical(id="permission-dialog"):
            yield Label(f"[bold]Permission Required[/] — {self._tool_name}", id="permission-title")
            yield Static(self._description, id="permission-message")
            if self._args_str:
                yield Static(f"[dim]{self._args_str[:200]}[/]", id="permission-args")
            with Horizontal(id="permission-buttons"):
                yield Button("Allow Once", variant="primary", id="allow-once")
                yield Button("Allow All", variant="default", id="allow-all")
                yield Button("Deny", variant="error", id="deny")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "allow-once":
            self.dismiss(True)
        elif event.button.id == "allow-all":
            self.dismiss(True)
        elif event.button.id == "deny":
            self.dismiss(False)


class ModelPicker(ModalScreen[str | None]):
    """Modal dialog for selecting a model from a list."""

    CSS = """
    ModelPicker {
        align: center middle;
    }
    #model-picker {
        width: 50;
        height: auto;
        max-height: 80%;
        background: $panel;
        border: thick $accent;
        padding: 1 2;
    }
    #model-list {
        margin: 1 0;
        height: auto;
        max-height: 30;
    }
    """

    def __init__(self, models: list[str], current: str = "") -> None:
        super().__init__()
        self._models = models
        self._current = current
        self._selected: str | None = None

    def compose(self) -> ComposeResult:
        with Vertical(id="model-picker"):
            yield Label("[bold]Select Model[/]", id="model-title")
            select_opts = [(m, m) for m in self._models]
            current_idx = 0
            if self._current in self._models:
                current_idx = self._models.index(self._current)
            yield Select(
                select_opts,
                value=self._models[current_idx] if self._models else None,
                id="model-list",
            )
            yield Button("Confirm", variant="primary", id="confirm")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "confirm":
            select = self.query_one("#model-list", Select)
            self.dismiss(str(select.value) if select.value else None)


class HelpDialog(ModalScreen[None]):
    """Modal dialog showing slash command help."""

    CSS = """
    HelpDialog {
        align: center middle;
    }
    #help-dialog {
        width: 70;
        height: auto;
        max-height: 90%;
        background: $panel;
        border: thick $accent;
        padding: 1 2;
    }
    #help-content {
        margin: 1 0;
        height: auto;
    }
    """

    def compose(self) -> ComposeResult:
        with Vertical(id="help-dialog"):
            yield Label("[bold]Octopus Commands[/]", id="help-title")
            yield Static(
                "\n".join([
                    "/help       Show available commands",
                    "/init       Generate OCTOPUS.md with project docs",
                    "/add-dir    Add a working directory to the session",
                    "/branch     Save state and start new branch",
                    "/btw        Ask a side question",
                    "/cd         Change working directory",
                    "/clear      Clear conversation, start new session",
                    "/color      Change prompt bar color",
                    "/compact    Force conversation compaction",
                    "/config     Show or edit configuration",
                    "/context    Show context usage as a colored grid",
                    "/model      Fetch and select model from provider",
                    "/tokens     Show estimated token count",
                    "/reset      Reset conversation history",
                    "/exit       Exit Octopus",
                    "",
                    "Shortcuts:",
                    "Ctrl+P      Cycle permission mode",
                    "Ctrl+S      Focus sidebar",
                    "Ctrl+L      Focus chat input",
                    "Ctrl+/      Slash command mode",
                ]),
                id="help-content",
            )
            yield Button("Close", variant="primary", id="close-help")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(None)
