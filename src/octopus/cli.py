"""Octopus Agent CLI — Typer-based command line interface with harness governance."""

from __future__ import annotations

import sys
from typing import Optional

import typer
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel

from octopus import __version__

app = typer.Typer(
    name="octopus",
    help="🐙 Octopus Agent — AI coding assistant with harness governance",
    no_args_is_help=True,
)
console = Console()


def version_callback(value: bool) -> None:
    """Print version and exit."""
    if value:
        console.print(f"[bold green]Octopus Agent[/] v{__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: Optional[bool] = typer.Option(
        None, "--version", "-v", callback=version_callback, is_eager=True,
        help="Show version and exit.",
    ),
) -> None:
    """🐙 Octopus Agent — Desktop + CLI dual AI coding assistant with harness governance."""


# ---------------------------------------------------------------------------
# CLI interactive / single-prompt command
# ---------------------------------------------------------------------------
@app.command()
def cli(
    prompt: Optional[str] = typer.Argument(None, help="Single prompt (omit for interactive mode)"),
    model: Optional[str] = typer.Option(None, "--model", "-m", help="Model to use"),
    permission_mode: str = typer.Option(
        "default", "--permission-mode", "-p",
        help="Permission mode: default, plan, full_auto",
    ),
) -> None:
    """Enter CLI interactive mode or run a single prompt."""
    if prompt:
        _run_single_prompt(prompt, model, permission_mode)
    else:
        _run_interactive(model, permission_mode)


def _run_single_prompt(prompt: str, model: Optional[str], permission_mode: str) -> None:
    """Run a single prompt and exit."""
    console.print(Panel(f"[bold]Prompt:[/] {prompt}", title="🐙 Octopus", border_style="blue"))
    console.print("[yellow]Agent loop not yet implemented. This is a placeholder.[/]")
    # TODO: Wire up agent loop (Week 3)


def _run_interactive(model: Optional[str], permission_mode: str) -> None:
    """Run interactive chat mode."""
    console.print(
        Panel(
            "[bold green]Octopus Interactive Mode[/]\n"
            "Type your message and press Enter.\n"
            "Commands: [cyan]/help[/] [cyan]/clear[/] [cyan]/exit[/]",
            title="🐙 Octopus",
            border_style="blue",
        )
    )

    while True:
        try:
            user_input = console.input("[bold blue]You>[/] ")
        except (EOFError, KeyboardInterrupt):
            console.print("\n[dim]Goodbye![/]")
            break

        if not user_input.strip():
            continue

        if user_input.strip().startswith("/"):
            if _handle_slash_command(user_input.strip()):
                break
            continue

        # TODO: Wire up agent loop (Week 3)
        console.print("[dim]Agent loop not yet implemented. This is a placeholder.[/]")


def _handle_slash_command(command: str) -> bool:
    """Handle slash commands. Returns True if should exit."""
    cmd = command.lower()
    if cmd in ("/exit", "/quit", "/q"):
        console.print("[dim]Goodbye![/]")
        return True
    if cmd == "/clear":
        console.clear()
        return False
    if cmd == "/help":
        console.print(
            Markdown(
                "### Available Commands\n"
                "- `/help` — Show this help\n"
                "- `/clear` — Clear screen\n"
                "- `/exit` — Exit interactive mode\n"
            )
        )
        return False
    console.print(f"[red]Unknown command:[/] {command}")
    return False


# ---------------------------------------------------------------------------
# Code agent subcommands
# ---------------------------------------------------------------------------
@app.command()
def code(
    action: str = typer.Argument(..., help="Action: init | fix | test | refactor | logs"),
    path: Optional[str] = typer.Option(".", "--path", help="Project path"),
) -> None:
    """Code agent subcommands."""
    actions = {
        "init": _code_init,
        "fix": _code_fix,
        "test": _code_test,
        "refactor": _code_refactor,
        "logs": _code_logs,
    }
    if action not in actions:
        console.print(f"[red]Unknown action:[/] {action}")
        console.print(f"Available: {', '.join(actions.keys())}")
        raise typer.Exit(code=1)
    actions[action](path)


def _code_init(path: str) -> None:
    console.print(f"[bold]Initializing workspace at[/] {path}")
    console.print("[yellow]Not yet implemented.[/]")


def _code_fix(path: str) -> None:
    console.print(f"[bold]Scanning for bugs in[/] {path}")
    console.print("[yellow]Not yet implemented.[/]")


def _code_test(path: str) -> None:
    console.print(f"[bold]Generating tests for[/] {path}")
    console.print("[yellow]Not yet implemented.[/]")


def _code_refactor(path: str) -> None:
    console.print(f"[bold]Refactoring code in[/] {path}")
    console.print("[yellow]Not yet implemented.[/]")


def _code_logs(path: str) -> None:
    console.print("[bold]Audit logs:[/]")
    console.print("[yellow]Not yet implemented.[/]")


# ---------------------------------------------------------------------------
# Config management
# ---------------------------------------------------------------------------
@app.command()
def config(
    action: str = typer.Argument(..., help="Action: show | set | list"),
    key: Optional[str] = typer.Argument(None, help="Config key"),
    value: Optional[str] = typer.Argument(None, help="Config value (for set)"),
) -> None:
    """Configuration management."""
    if action == "show":
        console.print("[bold]Current configuration:[/]")
        console.print("[yellow]Not yet implemented.[/]")
    elif action == "set":
        if not key or not value:
            console.print("[red]Both key and value are required for 'set'.[/]")
            raise typer.Exit(code=1)
        console.print(f"[bold]Setting[/] {key} = {value}")
        console.print("[yellow]Not yet implemented.[/]")
    elif action == "list":
        console.print("[bold]All configuration keys:[/]")
        console.print("[yellow]Not yet implemented.[/]")
    else:
        console.print(f"[red]Unknown action:[/] {action}")
        raise typer.Exit(code=1)


# ---------------------------------------------------------------------------
# Provider management
# ---------------------------------------------------------------------------
@app.command()
def provider(
    action: str = typer.Argument(..., help="Action: list | use | add"),
    name: Optional[str] = typer.Argument(None, help="Provider name"),
) -> None:
    """Provider management."""
    if action == "list":
        console.print("[bold]Available providers:[/]")
        console.print("[yellow]Not yet implemented.[/]")
    elif action == "use":
        if not name:
            console.print("[red]Provider name is required for 'use'.[/]")
            raise typer.Exit(code=1)
        console.print(f"[bold]Switching to provider:[/] {name}")
        console.print("[yellow]Not yet implemented.[/]")
    elif action == "add":
        console.print("[bold]Add new provider:[/]")
        console.print("[yellow]Not yet implemented.[/]")
    else:
        console.print(f"[red]Unknown action:[/] {action}")
        raise typer.Exit(code=1)


# ---------------------------------------------------------------------------
# Session management
# ---------------------------------------------------------------------------
@app.command()
def session(
    action: str = typer.Argument(..., help="Action: list | resume | new"),
    session_id: Optional[str] = typer.Argument(None, help="Session ID"),
) -> None:
    """Session management."""
    if action == "list":
        console.print("[bold]Sessions:[/]")
        console.print("[yellow]Not yet implemented.[/]")
    elif action == "resume":
        if not session_id:
            console.print("[red]Session ID is required for 'resume'.[/]")
            raise typer.Exit(code=1)
        console.print(f"[bold]Resuming session:[/] {session_id}")
        console.print("[yellow]Not yet implemented.[/]")
    elif action == "new":
        console.print("[bold]Creating new session...[/]")
        console.print("[yellow]Not yet implemented.[/]")
    else:
        console.print(f"[red]Unknown action:[/] {action}")
        raise typer.Exit(code=1)


# ---------------------------------------------------------------------------
# Permissions management
# ---------------------------------------------------------------------------
@app.command()
def permissions(
    action: str = typer.Argument(..., help="Action: list | add | remove"),
    pattern: Optional[str] = typer.Argument(None, help="Path/command pattern"),
) -> None:
    """Harness permission management."""
    if action == "list":
        console.print("[bold]Permission rules:[/]")
        console.print("[yellow]Not yet implemented.[/]")
    elif action == "add":
        if not pattern:
            console.print("[red]Pattern is required for 'add'.[/]")
            raise typer.Exit(code=1)
        console.print(f"[bold]Adding rule:[/] {pattern}")
        console.print("[yellow]Not yet implemented.[/]")
    elif action == "remove":
        if not pattern:
            console.print("[red]Pattern is required for 'remove'.[/]")
            raise typer.Exit(code=1)
        console.print(f"[bold]Removing rule:[/] {pattern}")
        console.print("[yellow]Not yet implemented.[/]")
    else:
        console.print(f"[red]Unknown action:[/] {action}")
        raise typer.Exit(code=1)


if __name__ == "__main__":
    app()
