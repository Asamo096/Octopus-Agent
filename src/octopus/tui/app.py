"""Octopus TUI — Claude Code-inspired terminal interface."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Vertical, VerticalScroll
from textual.widgets import Static

from octopus.tui.widgets.input import ChatInput, build_suggestions_text
from octopus.tui.widgets.status import StatusBar


# Theme definitions — curated from popular terminal/editor themes
THEMES: dict[str, dict[str, str]] = {
    "dracula": {
        "bg": "#282a36", "surface": "#21222c", "border": "#44475a",
        "active": "#6272a4", "text": "#f8f8f2", "dim": "#6272a4",
        "muted": "#44475a", "accent": "#bd93f9", "accent2": "#ff79c6",
        "success": "#50fa7b", "warning": "#ffb86c", "error": "#ff5555",
        "code_fg": "#ff79c6", "input_bg": "#282a36", "status_bg": "#21222c",
    },
    "monokai": {
        "bg": "#272822", "surface": "#1e1f1c", "border": "#49483e",
        "active": "#75715e", "text": "#f8f8f2", "dim": "#75715e",
        "muted": "#49483e", "accent": "#a6e22e", "accent2": "#66d9ef",
        "success": "#a6e22e", "warning": "#e6db74", "error": "#f92672",
        "code_fg": "#ae81ff", "input_bg": "#272822", "status_bg": "#1e1f1c",
    },
    "nord": {
        "bg": "#2e3440", "surface": "#3b4252", "border": "#4c566a",
        "active": "#81a1c1", "text": "#eceff4", "dim": "#81a1c1",
        "muted": "#4c566a", "accent": "#88c0d0", "accent2": "#5e81ac",
        "success": "#a3be8c", "warning": "#ebcb8b", "error": "#bf616a",
        "code_fg": "#b48ead", "input_bg": "#2e3440", "status_bg": "#3b4252",
    },
    "gruvbox": {
        "bg": "#282828", "surface": "#1d2021", "border": "#504945",
        "active": "#bdae93", "text": "#ebdbb2", "dim": "#a89984",
        "muted": "#665c54", "accent": "#fabd2f", "accent2": "#83a598",
        "success": "#b8bb26", "warning": "#fe8019", "error": "#fb4934",
        "code_fg": "#d3869b", "input_bg": "#282828", "status_bg": "#1d2021",
    },
    "catppuccin-mocha": {
        "bg": "#1e1e2e", "surface": "#181825", "border": "#313244",
        "active": "#45475a", "text": "#cdd6f4", "dim": "#6c7086",
        "muted": "#45475a", "accent": "#89b4fa", "accent2": "#cba6f7",
        "success": "#a6e3a1", "warning": "#f9e2af", "error": "#f38ba8",
        "code_fg": "#f5c2e7", "input_bg": "#1e1e2e", "status_bg": "#181825",
    },
    "solarized-dark": {
        "bg": "#002b36", "surface": "#073642", "border": "#586e75",
        "active": "#657b83", "text": "#eee8d5", "dim": "#839496",
        "muted": "#586e75", "accent": "#268bd2", "accent2": "#2aa198",
        "success": "#859900", "warning": "#b58900", "error": "#dc322f",
        "code_fg": "#d33682", "input_bg": "#002b36", "status_bg": "#073642",
    },
    "tokyo-night": {
        "bg": "#1a1b26", "surface": "#16161e", "border": "#2f3346",
        "active": "#565f89", "text": "#c0caf5", "dim": "#565f89",
        "muted": "#2f3346", "accent": "#7aa2f7", "accent2": "#bb9af7",
        "success": "#9ece6a", "warning": "#e0af68", "error": "#f7768e",
        "code_fg": "#bb9af7", "input_bg": "#1a1b26", "status_bg": "#16161e",
    },
    "rose-pine": {
        "bg": "#191724", "surface": "#1f1d2e", "border": "#26233a",
        "active": "#6e6a86", "text": "#e0def4", "dim": "#908caa",
        "muted": "#6e6a86", "accent": "#ebbcba", "accent2": "#c4a7e7",
        "success": "#31748f", "warning": "#f6c177", "error": "#eb6f92",
        "code_fg": "#c4a7e7", "input_bg": "#191724", "status_bg": "#1f1d2e",
    },
    "github-dark": {
        "bg": "#0d1117", "surface": "#161b22", "border": "#21262d",
        "active": "#30363d", "text": "#c9d1d9", "dim": "#8b949e",
        "muted": "#484f58", "accent": "#58a6ff", "accent2": "#00afff",
        "success": "#7ee787", "warning": "#d29922", "error": "#f85149",
        "code_fg": "#d2a8ff", "input_bg": "#0d1117", "status_bg": "#161b22",
    },
}

# Active theme (mutable)
C = dict(THEMES["github-dark"])

ASCII_LOGO = [
    " ██████╗  ██████╗████████╗ ██████╗ ██████╗ ██╗   ██╗███████╗",
    "██╔═══██╗██╔════╝╚══██╔══╝██╔═══██╗██╔══██╗██║   ██║██╔════╝",
    "██║   ██║██║        ██║   ██║   ██║██████╔╝██║   ██║███████╗",
    "██║   ██║██║        ██║   ██║   ██║██╔═══╝ ██║   ██║╚════██║",
    "╚██████╔╝╚██████╗   ██║   ╚██████╔╝██║     ╚██████╔╝███████║",
    " ╚═════╝  ╚═════╝   ╚═╝    ╚═════╝ ╚═╝      ╚═════╝ ╚══════╝",
]


class OctopusTUI(App):
    """Terminal-native interface inspired by Claude Code.

    Shows full ASCII logo on startup, switches to compact banner
    after the first user message.
    """

    CSS = """
    Screen { background: #0d1117; }

    #banner {
        height: auto; padding: 0 2; background: #0d1117;
    }
    .banner-logo { color: #00afff; text-style: bold; }
    .banner-info { color: #8b949e; margin-top: 1; }

    #banner-compact {
        height: auto; padding: 0 2; background: #0d1117;
        color: #00afff; text-style: bold;
    }
    #banner-line { height: 1; color: #21262d; margin: 0 2; }

    #main { height: 1fr; }
    #chat-container {
        height: 1fr; border: round #21262d;
        padding: 1 2; margin: 0 1;
        background: #0d1117;
    }
    #chat-log { height: 1fr; }

    #input-divider {
        height: 1; margin: 0 1; background: #30363d;
    }
    #input-area {
        height: auto; min-height: 4; max-height: 10;
        border: round #21262d; padding: 1; margin: 0 1;
        background: #0d1117;
    }
    #suggestions {
        height: auto; max-height: 10; padding: 0 1;
        color: #8b949e; border-top: solid #21262d;
    }
    #chat-input { height: 1fr; min-height: 2; }

    #status-bar {
        height: 1; dock: bottom;
        background: #161b22; color: #8b949e; padding: 0 1;
    }

    .user-msg { color: #58a6ff; margin: 1 0 0 0; }
    .assistant-msg { color: #c9d1d9; margin: 1 0; }
    .thinking-msg { color: #484f58; margin: 0; }
    .thinking-indicator {
        color: #484f58; margin: 0; text-style: italic;
    }
    .tool-card {
        margin: 1 0; padding: 1 2;
        border: solid #21262d; background: #161b22;
    }
    .tool-card-active {
        margin: 1 0; padding: 1 2;
        border: solid #30363d; background: #161b22;
    }
    .system-msg { color: #484f58; margin: 0; }
    .error-msg { color: #f85149; margin: 1 0; }

    TextArea { background: #0d1117; border: none; color: #c9d1d9; }
    TextArea:focus { border: none; }
    """

    BINDINGS = [
        Binding("ctrl+c", "quit", "Quit", show=False),
        Binding("ctrl+p", "toggle_permission", "Mode", show=False),
        Binding("ctrl+t", "toggle_theme", "Theme", show=False),
        Binding("ctrl+shift+c", "copy_last", "Copy", show=False),
        Binding("escape", "interrupt", "Interrupt", show=False),
    ]

    def __init__(
        self,
        *,
        model: str = "",
        permission_mode: str = "default",
        workspace: str | None = None,
        session_id: str | None = None,
        kernel: Any = None,
        provider: Any = None,
        tool_registry: Any = None,
        ctx: Any = None,
        conversation: Any = None,
    ) -> None:
        super().__init__()
        self.octopus_model = model
        self.octopus_permission_mode = permission_mode
        self.octopus_workspace = workspace or str(Path.cwd())
        self.octopus_session_id = session_id or ""
        self.octopus_kernel = kernel
        self.octopus_provider = provider
        self.octopus_tool_registry = tool_registry
        self.octopus_ctx = ctx
        self.octopus_conversation = conversation
        self._input_queue: Any = None
        self._last_assistant_text = ""
        self._streaming_widget: Static | None = None
        self._streaming_text = ""
        self._streaming_pending = ""
        self._streaming_timer: Any = None
        self._compact_banner_widget: Static | None = None
        self._compact_mode = False
        self._theme_name = "dark"
        self._effort = "high"
        self._thinking_widget: Static | None = None
        self._thinking_timer: Any = None
        self._thinking_frame = 0

    # ---- Compose ----

    def compose(self) -> ComposeResult:
        # Full logo + info for startup
        with Vertical(id="banner"):
            for line in ASCII_LOGO:
                yield Static(line, classes="banner-logo")
            yield Static(self._info(), classes="banner-info")

        # Compact banner (hidden initially)
        yield Static(self._compact_banner(), id="banner-compact")

        yield Static("─" * max(self.size.width, 60), id="banner-line")
        with Vertical(id="main"):
            with Vertical(id="chat-container"):
                yield VerticalScroll(id="chat-log")
            yield Static("", id="input-divider")
            with Vertical(id="input-area"):
                yield ChatInput(id="chat-input")
                yield Static("", id="suggestions")
        yield StatusBar(id="status-bar")

    def on_mount(self) -> None:
        # Hide compact banner on startup
        try:
            cb = self.query_one("#banner-compact", Static)
            cb.display = False
            self._compact_banner_widget = cb
        except Exception:
            pass
        self.query_one("#status-bar", StatusBar).update_mode(
            self.octopus_permission_mode
        )
        self.query_one("#chat-input", ChatInput).focus()

    def _switch_to_compact(self) -> None:
        """Switch from full logo to compact one-line banner."""
        if self._compact_mode:
            return
        self._compact_mode = True
        try:
            # Hide full logo
            self.query_one("#banner", Vertical).display = False
            # Show compact
            if self._compact_banner_widget:
                self._compact_banner_widget.display = True
        except Exception:
            pass

    def _banner(self) -> str:
        return self._info() if self._compact_mode else ""

    def _compact_banner(self) -> str:
        model = self.octopus_model
        if "/" in model:
            model = model.split("/", 1)[1]
        model = self._short(model)
        ws_name = Path(self.octopus_workspace).name
        effort = "" if self._effort == "high" else f"  [dim]effort:{self._effort}[/]"
        return (
            f"[bold #00afff]Octopus[/]  "
            f"[dim]{model}[/]  "
            f"[dim]{self.octopus_permission_mode}[/]  "
            f"[dim]{ws_name}[/]{effort}"
        )

    def _info(self) -> str:
        model = self.octopus_model
        if "/" in model:
            model = model.split("/", 1)[1]
        model = self._short(model)
        ws_name = Path(self.octopus_workspace).name
        effort = "" if self._effort == "high" else f"  |  EFFORT: {self._effort}"
        return f"MODEL: {model}  |  PERM: {self.octopus_permission_mode}  |  PATH: {ws_name}{effort}"

    @staticmethod
    def _short(model: str) -> str:
        for s in ("-20250514", "-2024-08-06", "-2024-06-20", "-latest"):
            if model.endswith(s):
                return model[: -len(s)]
        return model or "(none)"

    # ---- Resize ----

    def on_resize(self, event: Any) -> None:
        self._debounced_resize()

    def _debounced_resize(self) -> None:
        """Debounce resize to avoid jank during rapid terminal resizes."""
        try:
            w = max(self.size.width, 60)
            self.query_one("#banner-line", Static).update("─" * w)
            if self._compact_banner_widget and self._compact_mode:
                self._compact_banner_widget.update(self._compact_banner())
        except Exception:
            pass

    # ---- Message handlers ----

    def on_chat_input_submitted(self, message: ChatInput.Submitted) -> None:
        self._switch_to_compact()
        queue = getattr(self, "_input_queue", None)
        if queue is not None:
            import asyncio
            asyncio.ensure_future(queue.put(message.text))

    def on_chat_input_suggestions_changed(
        self, message: ChatInput.SuggestionsChanged
    ) -> None:
        ci = self.query_one("#chat-input", ChatInput)
        txt = build_suggestions_text(message.text, ci.suggestion_index)
        self.query_one("#suggestions", Static).update(txt)

    def on_chat_input_cancelled(self) -> None:
        self.query_one("#suggestions", Static).update("")

    # ---- Log helpers ----

    def _log(self) -> VerticalScroll:
        return self.query_one("#chat-log", VerticalScroll)

    def add_user_message(self, text: str) -> None:
        self._log().mount(
            Static(f"[bold #58a6ff]❯[/] {text}", classes="user-msg")
        )
        self._log().scroll_end(animate=True, duration=0.2)

    def add_assistant_message(self, text: str) -> None:
        self._log().mount(
            Static(_render(text), classes="assistant-msg")
        )
        self._log().scroll_end(animate=True, duration=0.3)
        self._last_assistant_text = text

    def add_thinking(self, text: str) -> None:
        self._log().mount(
            Static(f"[dim italic #484f58]  Thought: {text}[/]", classes="thinking-msg")
        )
        self._log().scroll_end(animate=True, duration=0.15)

    def add_tool_card(self, name: str, args_str: str) -> Static:
        """Add a tool execution card, returns the card for result updates."""
        body = f"[bold #7ee787]{name}[/] [dim #8b949e]{args_str[:100]}[/]"
        card = Static(body, classes="tool-card-active")
        self._log().mount(card)
        self._log().scroll_end(animate=False)
        return card

    @staticmethod
    def update_tool_card(card: Static, name: str, result: str = "") -> None:
        """Update tool card with result."""
        lines = [f"[bold #7ee787]{name}[/]"]
        if result:
            preview = result.strip()[:400]
            if len(result.strip()) > 400:
                preview += "\n[dim]... truncated[/]"
            lines.append(f"[dim #8b949e]{preview}[/]")
        card.update("\n".join(lines))
        card.set_class(True, "tool-card")

    def add_system_message(self, text: str) -> None:
        self._log().mount(Static(f"[dim #484f58]{text}[/]", classes="system-msg"))
        self._log().scroll_end(animate=False)

    def add_error_message(self, text: str) -> None:
        self._log().mount(
            Static(f"[bold #f85149]Error:[/] {text}", classes="error-msg")
        )
        self._log().scroll_end(animate=False)

    def clear_chat(self) -> None:
        self._log().remove_children()

    # ---- Thinking indicator ----

    _SPINNER = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]

    def show_thinking(self) -> None:
        """Show animated thinking indicator while waiting for model."""
        if self._thinking_widget is not None:
            return
        self._thinking_frame = 0
        ws = Path(self.octopus_workspace).name
        self._thinking_widget = Static("", classes="thinking-indicator")
        self._log().mount(self._thinking_widget)
        self._tick_thinking()

    def _tick_thinking(self) -> None:
        """Update thinking animation frame, schedule next tick."""
        if self._thinking_widget is None:
            return
        spin = self._SPINNER[self._thinking_frame % 10]
        dots = ["", ".", "..", "...", " ..", "  .", "   "][(self._thinking_frame // 2) % 7]
        self._thinking_frame += 1
        ws = Path(self.octopus_workspace).name
        self._thinking_widget.update(
            f"[dim italic #484f58]  {spin} {ws} > Thinking{dots}[/]"
        )
        self._thinking_timer = self.set_timer(0.15, self._tick_thinking)

    def hide_thinking(self) -> None:
        """Remove the thinking indicator and stop animation."""
        if self._thinking_timer is not None:
            self._thinking_timer.stop()
            self._thinking_timer = None
        if self._thinking_widget is not None:
            self._thinking_widget.remove()
            self._thinking_widget = None

    # ---- Streaming ----

    def begin_streaming(self) -> None:
        self._streaming_text = ""
        self._streaming_widget = Static("", classes="assistant-msg")
        self._log().mount(self._streaming_widget)

    def append_stream(self, text: str) -> None:
        """Buffer stream chunks, flush every 50ms to avoid jank."""
        if self._streaming_widget is None:
            return
        self._streaming_text += text
        self._streaming_pending += text
        # Cancel previous timer, set new one
        if self._streaming_timer is not None:
            self._streaming_timer.stop()
        self._streaming_timer = self.set_timer(0.05, self._flush_stream)

    def _flush_stream(self) -> None:
        """Apply buffered stream text to the widget."""
        if self._streaming_widget is not None and self._streaming_pending:
            self._streaming_widget.update(self._streaming_text)
            self._streaming_pending = ""
            self._log().scroll_end(animate=False)

    def finish_streaming(self, raw_text: str) -> None:
        if self._streaming_timer is not None:
            self._streaming_timer.stop()
        self._flush_stream()
        if self._streaming_widget is not None:
            self._streaming_widget.remove()
            self._streaming_widget = None
        self.add_assistant_message(raw_text)
        self._last_assistant_text = raw_text

    # ---- Info update ----

    def update_info(self, model: str = "", permission_mode: str = "") -> None:
        if model:
            self.octopus_model = model
        if permission_mode:
            self.octopus_permission_mode = permission_mode
        try:
            # Update compact banner if visible
            if self._compact_banner_widget and self._compact_mode:
                self._compact_banner_widget.update(self._compact_banner())
            self.query_one("#status-bar", StatusBar).update_mode(
                self.octopus_permission_mode
            )
        except Exception:
            pass

    # ---- Actions ----

    def action_toggle_theme(self) -> None:
        """Cycle through all themes."""
        names = list(THEMES.keys())
        try:
            idx = names.index(self._theme_name)
        except ValueError:
            idx = 0
        self._theme_name = names[(idx + 1) % len(names)]
        C.update(THEMES[self._theme_name])
        self._apply_theme()
        self.add_system_message(
            f"Theme: [bold]{self._theme_name}[/]  [dim](Ctrl+T to cycle, /theme <name> to set)[/]"
        )

    def _apply_theme(self) -> None:
        """Apply current theme colors to all visible widgets."""
        c = C
        self.screen.styles.background = c["bg"]
        for wid, styles in [
            ("#status-bar", {"background": c["status_bg"]}),
            ("#chat-container", {"background": c["bg"], "border": ("round", c["border"])}),
            ("#input-area", {"background": c["bg"], "border": ("round", c["border"])}),
            ("#chat-log", {"background": c["bg"]}),
            ("#banner", {"background": c["bg"]}),
        ]:
            try:
                w = self.query_one(wid)
                for prop, val in styles.items():
                    setattr(w.styles, prop, val)
            except Exception:
                pass
        try:
            ci = self.query_one("#chat-input", ChatInput)
            ci.styles.background = c["input_bg"]
        except Exception:
            pass
        try:
            if self._compact_banner_widget and self._compact_mode:
                self._compact_banner_widget.update(self._compact_banner())
        except Exception:
            pass

    def action_toggle_permission(self) -> None:
        modes = ["default", "accept_edits", "full_auto", "plan"]
        try:
            idx = modes.index(self.octopus_permission_mode)
        except ValueError:
            idx = 0
        self.octopus_permission_mode = modes[(idx + 1) % len(modes)]
        self.update_info(permission_mode=self.octopus_permission_mode)
        if self.octopus_kernel:
            from octopus.core.kernel import PermissionMode as PM
            m = {"default": PM.DEFAULT, "plan": PM.PLAN,
                 "accept_edits": PM.ACCEPT_EDITS, "full_auto": PM.FULL_AUTO}
            self.octopus_kernel.set_permission_mode(m[self.octopus_permission_mode])
        self.add_system_message(f"Mode: {self.octopus_permission_mode}")

    def action_copy_last(self) -> None:
        if not self._last_assistant_text:
            return
        text = self._last_assistant_text
        copied = False
        try:
            import pyperclip
            pyperclip.copy(text)
            copied = True
        except Exception:
            pass
        if not copied:
            import subprocess
            for args in (["xclip", "-selection", "clipboard"], ["wl-copy"], ["pbcopy"]):
                try:
                    subprocess.run(args, input=text, text=True,
                                   capture_output=True, timeout=2)
                    copied = True
                    break
                except Exception:
                    continue
        self.add_system_message("Copied." if copied else "Copy failed. Install xclip/wl-copy.")

    def set_effort(self, level: str) -> None:
        """Set reasoning effort level."""
        self._effort = level
        self.update_info()

    def action_interrupt(self) -> None:
        pass


# -----------------------------------------------------------------------
# Markdown → Textual markup
# -----------------------------------------------------------------------


def _render(text: str) -> str:
    import re
    blocks: list[str] = []

    def _save(m: re.Match) -> str:
        blocks.append(m.group(1))
        return f"\x00C{len(blocks) - 1}\x00"

    text = re.sub(r"```(?:\w+)?\n(.*?)```", _save, text, flags=re.DOTALL)
    text = re.sub(r"`([^`]+)`", r"[bold #d2a8ff]\1[/]", text)
    text = re.sub(r"(?m)^### (.+)$", r"[bold]\1[/]", text)
    text = re.sub(r"(?m)^## (.+)$", r"[bold #58a6ff]\1[/]", text)
    text = re.sub(r"(?m)^# (.+)$", r"[bold #58a6ff]\1[/]", text)
    text = re.sub(r"\*\*\*(.+?)\*\*\*", r"[bold italic]\1[/]", text)
    text = re.sub(r"\*\*(.+?)\*\*", r"[bold]\1[/]", text)
    text = re.sub(r"\*(.+?)\*", r"[italic]\1[/]", text)
    text = re.sub(r"(?m)^(\s*)[*-] (.+)$", r"\1[dim]  -[/] \2", text)
    text = re.sub(r"(?m)^(\s*)\d+\. (.+)$", r"\1[dim]  -[/] \2", text)
    text = re.sub(r"(?m)^> (.+)$", r"[dim #8b949e]| \1[/]", text)

    for i, code in enumerate(blocks):
        lines = code.strip().split("\n")
        if len(lines) > 25:
            code = "\n".join(lines[:25]) + f"\n... +{len(lines) - 25} more lines"
        rendered = "\n".join(
            f"[dim #c9d1d9 on #161b22]  {l}[/]" for l in code.split("\n")
        )
        text = text.replace(f"\x00C{i}\x00", f"\n{rendered}\n")
    return text
