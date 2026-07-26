"""Sidebar widget — session list, file tree, agent status."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Static, TabbedContent, TabPane


class Sidebar(Vertical):
    """Collapsible sidebar with tabs for sessions, files, and agents."""

    def __init__(self, **kwargs: object) -> None:
        super().__init__(**kwargs)
        self._model = ""
        self._workspace = ""
        self._session_id = ""
        self._permission_mode = "default"

    def compose(self) -> ComposeResult:
        """Build sidebar content."""
        with TabbedContent():
            with TabPane("Info"):
                yield Static(
                    f"[bold]Octopus Agent[/]\n"
                    f"Model: [dim]{self._model or '(none)'}[/]\n"
                    f"Mode: [dim]{self._permission_mode}[/]\n"
                    f"Path: [dim]{self._workspace}[/]\n"
                    f"Session: [dim]{(self._session_id or 'new')[:12]}[/]",
                    id="sidebar-info",
                )
            with TabPane("Sessions"):
                yield Static("[dim]No saved sessions[/]", id="sidebar-sessions")
            with TabPane("Agents"):
                yield Static("[dim]No active agents[/]", id="sidebar-agents")

    def update_info(
        self,
        model: str = "",
        workspace: str = "",
        session_id: str = "",
        permission_mode: str = "default",
    ) -> None:
        """Update sidebar info display."""
        self._model = model
        self._workspace = workspace
        self._session_id = session_id
        self._permission_mode = permission_mode

        info = self.query_one("#sidebar-info", Static)
        info.update(
            f"[bold]Octopus Agent[/]\n"
            f"Model: [dim]{model or '(none)'}[/]\n"
            f"Mode: [dim]{permission_mode}[/]\n"
            f"Path: [dim]{workspace}[/]\n"
            f"Session: [dim]{(session_id or 'new')[:12]}[/]"
        )

    def update_sessions(self, sessions: list[str]) -> None:
        """Update the sessions tab with a list of sessions."""
        sessions_widget = self.query_one("#sidebar-sessions", Static)
        if not sessions:
            sessions_widget.update("[dim]No saved sessions[/]")
        else:
            sessions_widget.update("\n".join(f"[dim]{s[:12]}...[/]" for s in sessions))

    def update_agents(self, agents: list[dict[str, str]]) -> None:
        """Update the agents tab with active agent status."""
        agents_widget = self.query_one("#sidebar-agents", Static)
        if not agents:
            agents_widget.update("[dim]No active agents[/]")
        else:
            lines = []
            for a in agents:
                status_color = "green" if a.get("status") == "running" else "dim"
                lines.append(f"[{status_color}]{a.get('id', '?')[:8]}[/] {a.get('status', '?')}")
            agents_widget.update("\n".join(lines))
