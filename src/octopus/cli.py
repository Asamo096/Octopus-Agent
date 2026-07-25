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
    model: str | None = typer.Option(None, "--model", "-m", help="Model to use"),
    permission_mode: str = typer.Option(
        "full_auto", "--permission-mode", "-p", help="Permission mode"
    ),
) -> None:
    """Code agent subcommands."""
    from octopus.cli_runtime import (
        code_init_async,
        run_single_prompt_async,
        show_audit_logs_async,
    )

    if action == "init":
        _run_async(code_init_async(path or "."))
    elif action == "logs":
        _run_async(show_audit_logs_async())
    elif action == "fix":
        prompt = (
            "Scan the current workspace for bugs, errors, and code quality issues. "
            "Fix any issues found. Report what was fixed."
        )
        _run_async(run_single_prompt_async(prompt, model=model, permission_mode=permission_mode))
    elif action == "test":
        prompt = (
            "Analyze the current workspace and generate comprehensive unit tests. "
            "Run the tests and report results. Use pytest."
        )
        _run_async(run_single_prompt_async(prompt, model=model, permission_mode=permission_mode))
    elif action == "refactor":
        prompt = (
            "Analyze the current workspace for refactoring opportunities. "
            "Improve code structure, naming, and reduce complexity. "
            "Report what was refactored."
        )
        _run_async(run_single_prompt_async(prompt, model=model, permission_mode=permission_mode))
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
    api_key: str | None = typer.Option(None, "--api-key", help="API key"),
    base_url: str | None = typer.Option(None, "--base-url", help="API base URL"),
    model: str | None = typer.Option(None, "--model", help="Default model"),
) -> None:
    """Provider management."""
    from octopus.cli_runtime import _get_db_path
    from octopus.core.state import StateManager

    async def _list() -> None:
        state = StateManager(db_path=_get_db_path())
        try:
            providers = await state.get_value("config.providers", {})
            if not providers:
                console.print("[yellow]No providers configured. Using defaults.[/]")
                console.print("  [cyan]claude[/]  — Anthropic Claude (default)")
                console.print("  [cyan]openai[/]  — OpenAI-compatible")
                return
            for pname, pconfig in providers.items():
                console.print(f"  [cyan]{pname}[/] — {pconfig.get('provider', 'unknown')}")
                if pconfig.get("model"):
                    console.print(f"    model: {pconfig['model']}")
                if pconfig.get("base_url"):
                    console.print(f"    url: {pconfig['base_url']}")
        finally:
            await state.close()

    async def _use() -> None:
        state = StateManager(db_path=_get_db_path())
        try:
            providers = await state.get_value("config.providers", {})
            if name not in providers:
                console.print(f"[red]Provider '{name}' not found. Use 'provider add' first.[/]")
                raise typer.Exit(code=1)
            await state.set_value("config.default_provider", name)
            console.print(f"[green]✓[/] Default provider set to: {name}")
        finally:
            await state.close()

    async def _add() -> None:
        if not name:
            console.print("[red]Provider name is required for 'add'.[/]")
            raise typer.Exit(code=1)
        state = StateManager(db_path=_get_db_path())
        try:
            providers = await state.get_value("config.providers", {})
            providers[name] = {
                "provider": name,
                "api_key": api_key,
                "base_url": base_url,
                "model": model,
            }
            await state.set_value("config.providers", providers)
            console.print(f"[green]✓[/] Added provider: {name}")
        finally:
            await state.close()

    if action == "list":
        _run_async(_list())
    elif action == "use":
        if not name:
            console.print("[red]Provider name is required for 'use'.[/]")
            raise typer.Exit(code=1)
        _run_async(_use())
    elif action == "add":
        _run_async(_add())
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
    model: str | None = typer.Option(None, "--model", "-m", help="Model to use"),
    permission_mode: str = typer.Option(
        "default", "--permission-mode", "-p", help="Permission mode"
    ),
) -> None:
    """Session management."""
    from octopus.cli_runtime import (
        list_sessions_async,
        session_new_async,
        session_resume_async,
    )

    if action == "list":
        _run_async(list_sessions_async())
    elif action == "resume":
        if not session_id:
            console.print("[red]Session ID is required for 'resume'.[/]")
            raise typer.Exit(code=1)
        _run_async(session_resume_async(session_id, model=model, permission_mode=permission_mode))
    elif action == "new":
        _run_async(session_new_async(model=model, permission_mode=permission_mode))
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
    rule_type: str = typer.Option("path", "--type", "-t", help="Rule type: path | command"),
) -> None:
    """Harness permission management."""
    from octopus.cli_runtime import _get_db_path
    from octopus.core.state import StateManager

    async def _list() -> None:
        state = StateManager(db_path=_get_db_path())
        try:
            allowed_paths = await state.get_value("permissions.allowed_paths", [])
            denied_paths = await state.get_value("permissions.denied_paths", [])
            safe_commands = await state.get_value("permissions.safe_commands", [])
            dangerous_commands = await state.get_value("permissions.dangerous_commands", [])

            console.print("[bold]Permission rules:[/]")
            console.print()
            console.print("  [green]Default sensitive paths blocked (always):[/]")
            console.print("    ~/.ssh/*, ~/.aws/*, ~/.gnupg/*, **/.env, **/id_rsa*")
            console.print()
            if allowed_paths:
                console.print("  [green]Additional allowed paths:[/]")
                for p in allowed_paths:
                    console.print(f"    {p}")
            if denied_paths:
                console.print("  [red]Denied paths:[/]")
                for p in denied_paths:
                    console.print(f"    {p}")
            console.print()
            console.print("  [green]Safe commands (auto-allowed):[/]")
            cmds = safe_commands or ["ls", "cat", "grep", "find", "git", "python", "pip"]
            console.print(f"    {', '.join(cmds[:10])}")
            console.print()
            console.print("  [red]Dangerous commands (require approval):[/]")
            dang = dangerous_commands or ["rm -rf", "sudo", "chmod 777", "dd", "mkfs"]
            console.print(f"    {', '.join(dang[:10])}")
        finally:
            await state.close()

    async def _add() -> None:
        if not pattern:
            console.print("[red]Pattern is required for 'add'.[/]")
            raise typer.Exit(code=1)
        state = StateManager(db_path=_get_db_path())
        try:
            if rule_type == "path":
                paths = await state.get_value("permissions.allowed_paths", [])
                if pattern not in paths:
                    paths.append(pattern)
                    await state.set_value("permissions.allowed_paths", paths)
                console.print(f"[green]✓[/] Added allowed path: {pattern}")
            elif rule_type == "command":
                cmds = await state.get_value("permissions.safe_commands", [])
                if pattern not in cmds:
                    cmds.append(pattern)
                    await state.set_value("permissions.safe_commands", cmds)
                console.print(f"[green]✓[/] Added safe command: {pattern}")
            else:
                console.print(f"[red]Unknown rule type: {rule_type}[/]")
                raise typer.Exit(code=1)
        finally:
            await state.close()

    async def _remove() -> None:
        if not pattern:
            console.print("[red]Pattern is required for 'remove'.[/]")
            raise typer.Exit(code=1)
        state = StateManager(db_path=_get_db_path())
        try:
            if rule_type == "path":
                paths = await state.get_value("permissions.allowed_paths", [])
                if pattern in paths:
                    paths.remove(pattern)
                    await state.set_value("permissions.allowed_paths", paths)
                console.print(f"[green]✓[/] Removed allowed path: {pattern}")
            elif rule_type == "command":
                cmds = await state.get_value("permissions.safe_commands", [])
                if pattern in cmds:
                    cmds.remove(pattern)
                    await state.set_value("permissions.safe_commands", cmds)
                console.print(f"[green]✓[/] Removed safe command: {pattern}")
            else:
                console.print(f"[red]Unknown rule type: {rule_type}[/]")
                raise typer.Exit(code=1)
        finally:
            await state.close()

    if action == "list":
        _run_async(_list())
    elif action == "add":
        _run_async(_add())
    elif action == "remove":
        _run_async(_remove())
    else:
        console.print(f"[red]Unknown action:[/] {action}")
        raise typer.Exit(code=1)


if __name__ == "__main__":
    app()
