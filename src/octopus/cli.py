"""Octopus Agent CLI — Typer-based command line interface with harness governance."""

from __future__ import annotations

import asyncio

import typer
from rich.console import Console
from rich.panel import Panel

from octopus import __version__

app = typer.Typer(
    name="octopus",
    help="🐙 Octopus Agent — AI coding assistant with harness governance",
    no_args_is_help=True,
)
console = Console()


def _run_async(coro: object) -> None:
    """Run an async function from sync context."""
    asyncio.run(coro)  # type: ignore[arg-type]


def version_callback(value: bool) -> None:
    """Print version and exit."""
    if value:
        console.print(f"[bold green]Octopus Agent[/] v{__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: bool | None = typer.Option(
        None,
        "--version",
        "-v",
        callback=version_callback,
        is_eager=True,
        help="Show version and exit.",
    ),
) -> None:
    """🐙 Octopus Agent — Desktop + CLI dual AI coding assistant with harness governance."""


# ---------------------------------------------------------------------------
# CLI interactive / single-prompt command
# ---------------------------------------------------------------------------
@app.command()
def cli(
    prompt: str | None = typer.Argument(
        None, help="Single prompt (omit for interactive mode)"
    ),
    model: str | None = typer.Option(None, "--model", "-m", help="Model to use"),
    permission_mode: str = typer.Option(
        "default",
        "--permission-mode",
        "-p",
        help="Permission mode: default, plan, full_auto",
    ),
) -> None:
    """Enter CLI interactive mode or run a single prompt."""
    from octopus.cli_runtime import run_interactive_async, run_single_prompt_async

    if prompt:
        console.print(
            Panel(f"[bold]Prompt:[/] {prompt}", title="🐙 Octopus", border_style="blue")
        )
        _run_async(
            run_single_prompt_async(
                prompt, model=model, permission_mode=permission_mode
            )
        )
    else:
        console.print(
            Panel(
                "[bold green]Octopus Interactive Mode[/]\n"
                "Type your message and press Enter.\n"
                "Commands: [cyan]/help[/] [cyan]/clear[/] [cyan]/reset[/] [cyan]/exit[/]",
                title="🐙 Octopus",
                border_style="blue",
            )
        )
        _run_async(run_interactive_async(model=model, permission_mode=permission_mode))


# ---------------------------------------------------------------------------
# Code agent subcommands
# ---------------------------------------------------------------------------
@app.command()
def code(
    action: str = typer.Argument(
        ..., help="Action: init | fix | test | refactor | logs"
    ),
    path: str | None = typer.Option(".", "--path", help="Project path"),
) -> None:
    """Code agent subcommands."""
    from octopus.cli_runtime import code_init_async, show_audit_logs_async

    if action == "init":
        _run_async(code_init_async(path or "."))
    elif action == "logs":
        _run_async(show_audit_logs_async())
    elif action in ("fix", "test", "refactor"):
        console.print(f"[bold]{action.capitalize()}:[/] not yet implemented (Phase 2).")
    else:
        console.print(f"[red]Unknown action:[/] {action}")
        console.print("Available: init, fix, test, refactor, logs")
        raise typer.Exit(code=1)


# ---------------------------------------------------------------------------
# Config management
# ---------------------------------------------------------------------------
@app.command()
def config(
    action: str = typer.Argument(..., help="Action: show | set | list"),
    key: str | None = typer.Argument(None, help="Config key"),
    value: str | None = typer.Argument(None, help="Config value (for set)"),
) -> None:
    """Configuration management."""
    from octopus.cli_runtime import _get_db_path
    from octopus.core.state import StateManager

    async def _show() -> None:
        state = StateManager(db_path=_get_db_path())
        try:
            vals = await state.list_values(prefix="config.")
            if not vals:
                console.print("[yellow]No configuration set yet.[/]")
                return
            for k, v in vals.items():
                console.print(f"  [cyan]{k}[/] = {v}")
        finally:
            await state.close()

    async def _set() -> None:
        state = StateManager(db_path=_get_db_path())
        try:
            await state.set_value(f"config.{key}", value)
            console.print(f"[green]✓[/] {key} = {value}")
        finally:
            await state.close()

    if action == "show":
        _run_async(_show())
    elif action == "set":
        if not key or not value:
            console.print("[red]Both key and value are required for 'set'.[/]")
            raise typer.Exit(code=1)
        _run_async(_set())
    elif action == "list":
        _run_async(_show())
    else:
        console.print(f"[red]Unknown action:[/] {action}")
        raise typer.Exit(code=1)


# ---------------------------------------------------------------------------
# Provider management
# ---------------------------------------------------------------------------
@app.command()
def provider(
    action: str = typer.Argument(..., help="Action: list | use | add"),
    name: str | None = typer.Argument(None, help="Provider name"),
) -> None:
    """Provider management."""
    if action == "list":
        console.print("[bold]Available providers:[/]")
        console.print("  [cyan]claude[/]  — Anthropic Claude (default)")
        console.print("  [cyan]openai[/]  — OpenAI-compatible")
        console.print("  [cyan]ollama[/]  — Local Ollama models")
        console.print("[dim]Full provider management coming in Phase 2.[/]")
    elif action == "use":
        if not name:
            console.print("[red]Provider name is required for 'use'.[/]")
            raise typer.Exit(code=1)
        console.print(f"[bold]Switching to provider:[/] {name}")
        console.print("[dim]Full provider management coming in Phase 2.[/]")
    elif action == "add":
        console.print("[bold]Add new provider:[/]")
        console.print("[dim]Full provider management coming in Phase 2.[/]")
    else:
        console.print(f"[red]Unknown action:[/] {action}")
        raise typer.Exit(code=1)


# ---------------------------------------------------------------------------
# Session management
# ---------------------------------------------------------------------------
@app.command()
def session(
    action: str = typer.Argument(..., help="Action: list | resume | new"),
    session_id: str | None = typer.Argument(None, help="Session ID"),
) -> None:
    """Session management."""
    from octopus.cli_runtime import list_sessions_async

    if action == "list":
        _run_async(list_sessions_async())
    elif action == "resume":
        if not session_id:
            console.print("[red]Session ID is required for 'resume'.[/]")
            raise typer.Exit(code=1)
        console.print(f"[bold]Resuming session:[/] {session_id}")
        console.print("[dim]Session resume coming in Phase 2.[/]")
    elif action == "new":
        console.print("[bold]Creating new session...[/]")
        console.print("[dim]Session management coming in Phase 2.[/]")
    else:
        console.print(f"[red]Unknown action:[/] {action}")
        raise typer.Exit(code=1)


# ---------------------------------------------------------------------------
# Permissions management
# ---------------------------------------------------------------------------
@app.command()
def permissions(
    action: str = typer.Argument(..., help="Action: list | add | remove"),
    pattern: str | None = typer.Argument(None, help="Path/command pattern"),
) -> None:
    """Harness permission management."""
    if action == "list":
        console.print("[bold]Permission rules:[/]")
        console.print("  [green]Default sensitive paths blocked:[/]")
        console.print("    ~/.ssh/*, ~/.aws/*, ~/.gnupg/*, **/.env, **/id_rsa*")
        console.print("  [green]Safe commands:[/]")
        console.print("    ls, cat, grep, find, git status, python, pip")
        console.print("  [red]Dangerous commands (require approval):[/]")
        console.print("    rm -rf, sudo, chmod 777, dd, mkfs")
        console.print("[dim]Full permission management coming in Phase 2.[/]")
    elif action == "add":
        if not pattern:
            console.print("[red]Pattern is required for 'add'.[/]")
            raise typer.Exit(code=1)
        console.print(f"[bold]Adding rule:[/] {pattern}")
        console.print("[dim]Full permission management coming in Phase 2.[/]")
    elif action == "remove":
        if not pattern:
            console.print("[red]Pattern is required for 'remove'.[/]")
            raise typer.Exit(code=1)
        console.print(f"[bold]Removing rule:[/] {pattern}")
        console.print("[dim]Full permission management coming in Phase 2.[/]")
    else:
        console.print(f"[red]Unknown action:[/] {action}")
        raise typer.Exit(code=1)


if __name__ == "__main__":
    app()
