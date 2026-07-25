"""CLI runtime — async helpers that wire the agent loop to the CLI.

This module bridges the synchronous Typer CLI with the async agent loop.
Handles conversation context persistence, auto-compaction, and styled UI
matching claude-code's terminal patterns.
"""

from __future__ import annotations

import json
import time
import uuid
from pathlib import Path

from octopus.cli_ui import (
    ToolCallDisplay,
    TurnStats,
    console,
    display_banner,
    print_assistant_text_stream,
    print_error,
    print_help,
    print_info,
    print_prompt_arrow,
    print_separator,
    print_status,
    print_status_line,
    print_stream_newline,
    print_success,
    print_tool_call_output,
    print_tool_call_result,
    print_tool_call_start,
    print_warning,
)
from octopus.config.manager import (
    load_auth,
    load_config,
    save_auth,
    save_config,
)
from octopus.core.kernel import Context, Kernel, PermissionMode
from octopus.loop.compaction import CompactionEngine
from octopus.loop.context import ConversationContext
from octopus.loop.engine import run_query
from octopus.loop.models import Message, Role, StreamEventType
from octopus.providers.litellm_adapter import LiteLLMProvider
from octopus.tools.base import ToolRegistry
from octopus.tools.diff import register_diff_tools
from octopus.tools.filesystem import register_filesystem_tools
from octopus.tools.git import register_git_tool
from octopus.tools.search import register_search_tools
from octopus.tools.shell import register_shell_tool

# System prompt
SYSTEM_PROMPT = (
    "You are Octopus, an AI coding assistant with harness governance. "
    "You help users with coding tasks, file operations, and shell commands. "
    "Be concise, accurate, and helpful. When writing code, follow best practices."
)


def _resolve_model(model_arg: str | None) -> str | None:
    """Resolve model from argument, then config, then None.

    For custom providers with base_url, prefixes model with 'openai/'
    so litellm routes to the OpenAI-compatible API.
    """
    if model_arg:
        return _prefix_model_for_litellm(model_arg)
    config = load_config()
    if config.model:
        return _prefix_model_for_litellm(config.model)
    return None


def _prefix_model_for_litellm(model: str) -> str:
    """Prefix model name for litellm routing.

    MODEL_PROVIDER is the litellm standard prefix (e.g., 'openai',
    'anthropic', 'deepseek'). Model becomes '{MODEL_PROVIDER}/{model}'.
    """
    if "/" in model:
        return model

    config = load_config()
    if config.model_provider:
        return f"{config.model_provider}/{model}"
    return model


def _get_db_path() -> Path:
    """Get the path to the Octopus database."""
    db_dir = Path.home() / ".octopus"
    db_dir.mkdir(parents=True, exist_ok=True)
    return db_dir / "octopus.db"


def _resolve_permission_mode(mode_str: str) -> PermissionMode:
    """Convert string to PermissionMode."""
    mapping = {
        "default": PermissionMode.DEFAULT,
        "plan": PermissionMode.PLAN,
        "full_auto": PermissionMode.FULL_AUTO,
    }
    return mapping.get(mode_str, PermissionMode.DEFAULT)


async def _setup_runtime(
    *,
    model: str | None = None,
    permission_mode: str = "default",
    workspace: Path | None = None,
) -> tuple[Kernel, ToolRegistry, LiteLLMProvider, Context]:
    """Set up kernel, registry, provider, and context."""
    ws = workspace or Path.cwd()
    db_path = _get_db_path()
    pm = _resolve_permission_mode(permission_mode)

    kernel = Kernel(db_path=db_path, workspace=ws, permission_mode=pm)
    await kernel.initialize()

    registry = ToolRegistry()
    register_filesystem_tools(registry, kernel)
    register_shell_tool(registry, kernel)
    register_git_tool(registry, kernel)
    register_diff_tools(registry, kernel)
    register_search_tools(registry, kernel)

    # Load provider config from auth.json + config.toml
    import os

    config = load_config()
    auth = load_auth()

    # Set provider-specific API key env vars for litellm
    # litellm uses env vars like XIAOMI_MIMO_API_KEY, OPENAI_API_KEY, etc.
    api_key = auth.openai_api_key
    if api_key and config.model_provider:
        env_key = f"{config.model_provider.upper()}_API_KEY"
        os.environ[env_key] = api_key

    # Find base_url from provider config (for custom/unrecognized providers)
    base_url: str | None = None
    for p in config.model_providers.values():
        if p.base_url:
            base_url = p.base_url
            break

    provider = LiteLLMProvider(api_key=api_key, base_url=base_url)

    ctx = Context(
        session_id=str(uuid.uuid4()),
        kernel=kernel,
        workspace=ws,
        permission_mode=pm,
    )

    return kernel, registry, provider, ctx


async def run_single_prompt_async(
    prompt: str,
    *,
    model: str | None = None,
    permission_mode: str = "default",
) -> None:
    """Run a single prompt and print the response (non-interactive mode)."""
    kernel, registry, provider, ctx = await _setup_runtime(
        model=model,
        permission_mode=permission_mode,
    )

    try:
        conversation = ConversationContext(
            session_id=ctx.session_id,
            system_prompt=SYSTEM_PROMPT,
            model=_resolve_model(model),
        )
        conversation.ensure_system_message()
        conversation.add_message(Message(role=Role.USER, content=prompt))

        compaction = CompactionEngine()

        # Track turn stats
        turn_start = time.monotonic()
        tool_call_count = 0
        collected_text: list[str] = []

        async for event in run_query(
            conversation.messages,
            provider,
            kernel,
            registry,
            ctx,
            model=_resolve_model(model),
            conversation=conversation,
            compaction=compaction,
        ):
            if event.type == StreamEventType.TEXT:
                collected_text.append(event.text or "")
                print_assistant_text_stream(event.text or "")
            elif event.type == StreamEventType.TOOL_CALL:
                tc = event.tool_call
                if tc:
                    tool_call_count += 1
                    print_tool_call_start(tc.name, tc.arguments)
            elif event.type == StreamEventType.STATUS:
                print_status(event.text or "")
            elif event.type == StreamEventType.ERROR:
                print_error(event.error or "Unknown error")
            elif event.type == StreamEventType.DONE:
                pass

        if collected_text:
            print_stream_newline()

        # Print status line
        duration_ms = int((time.monotonic() - turn_start) * 1000)
        stats = TurnStats(
            duration_ms=duration_ms,
            model=_resolve_model(model),
            tool_calls=tool_call_count,
        )
        print_status_line(stats)

        # Persist conversation
        await conversation.save(kernel.state)

    finally:
        await kernel.shutdown()


async def run_interactive_async(
    *,
    model: str | None = None,
    permission_mode: str = "default",
    resume_session: str | None = None,
) -> None:
    """Run the interactive chat loop.

    If resume_session is provided, loads that session's conversation history.
    Otherwise starts a new session.
    """
    kernel, registry, provider, ctx = await _setup_runtime(
        model=model,
        permission_mode=permission_mode,
    )

    compaction = CompactionEngine()

    try:
        # Load or create conversation context
        conversation: ConversationContext | None = None
        if resume_session:
            conversation = await ConversationContext.load(resume_session, kernel.state)
            if conversation:
                conversation.sanitize()
                print_info(f"Resumed session {resume_session[:8]} ({len(conversation.messages)} messages)")
            else:
                print_warning(f"Session {resume_session} not found, starting new.")

        if conversation is None:
            conversation = ConversationContext(
                session_id=ctx.session_id,
                system_prompt=SYSTEM_PROMPT,
                model=_resolve_model(model),
            )
            conversation.ensure_system_message()
            await kernel.state.create_session(
                ctx.session_id,
                workspace=str(ctx.workspace) if ctx.workspace else None,
            )

        # Display banner — show resumed session ID if resuming
        display_session_id = resume_session if resume_session else ctx.session_id
        display_banner(
            model=_resolve_model(model),
            workspace=str(ctx.workspace),
            session_id=display_session_id,
            permission_mode=permission_mode,
        )

        # prompt_toolkit session for styled input with proper cursor positioning
        from prompt_toolkit import PromptSession
        from prompt_toolkit.formatted_text import HTML
        from prompt_toolkit.styles import Style

        prompt_style = Style.from_dict({"prompt": "bold #00afff"})
        pt_session: PromptSession[str] = PromptSession()

        # Session cost tracking
        session_cost = 0.0
        session_tokens_in = 0
        session_tokens_out = 0
        session_tool_calls = 0

        while True:
            print_separator()
            try:
                user_input = await pt_session.prompt_async(
                    HTML("<prompt>❯ </prompt>"),
                    style=prompt_style,
                )
            except (EOFError, KeyboardInterrupt):
                console.print("\n[dim]Goodbye![/]")
                console.print(f"[dim]octopus cli -c {display_session_id}[/]")
                break
            print_separator()

            if not user_input.strip():
                continue

            # Handle slash commands
            if user_input.strip().startswith("/"):
                if await _handle_slash_command(
                    user_input.strip(),
                    conversation,
                    session_cost=session_cost,
                    session_tokens_in=session_tokens_in,
                    session_tokens_out=session_tokens_out,
                ):
                    break
                continue

            # Add user message
            conversation.add_message(Message(role=Role.USER, content=user_input))
            console.print()

            # Print assistant response arrow
            print_prompt_arrow()

            # Track turn stats
            turn_start = time.monotonic()
            turn_tool_calls = 0
            collected_text: list[str] = []

            # Track tool calls for display
            current_tool = None

            async for event in run_query(
                conversation.messages,
                provider,
                kernel,
                registry,
                ctx,
                model=_resolve_model(model),
                conversation=conversation,
                compaction=compaction,
            ):
                if event.type == StreamEventType.TEXT:
                    collected_text.append(event.text or "")
                    print_assistant_text_stream(event.text or "")

                elif event.type == StreamEventType.TOOL_CALL:
                    tc = event.tool_call
                    if tc:
                        turn_tool_calls += 1
                        session_tool_calls += 1
                        # Finish previous tool if still open
                        if current_tool is not None:
                            print_tool_call_result(current_tool, "")
                        # Print new tool with newline prefix
                        console.print()
                        current_tool = print_tool_call_start(tc.name, tc.arguments)

                elif event.type == StreamEventType.STATUS:
                    print_status(event.text or "")

                elif event.type == StreamEventType.ERROR:
                    print_error(event.error or "Unknown error")

                elif event.type == StreamEventType.DONE:
                    pass

            # Close any unclosed tool
            if current_tool is not None:
                print_tool_call_result(current_tool, "")

            if collected_text:
                print_stream_newline()

            # Print turn status line
            duration_ms = int((time.monotonic() - turn_start) * 1000)
            stats = TurnStats(
                duration_ms=duration_ms,
                model=_resolve_model(model),
                tool_calls=turn_tool_calls,
            )
            print_status_line(stats)
            console.print()  # Blank line between turns

            # Persist conversation after each turn
            await conversation.save(kernel.state)

    finally:
        await kernel.shutdown()


async def _handle_slash_command(
    command: str,
    conversation: ConversationContext,
    *,
    session_cost: float = 0.0,
    session_tokens_in: int = 0,
    session_tokens_out: int = 0,
) -> bool:
    """Handle slash commands. Returns True if should exit."""
    cmd = command.lower().split()[0]  # Get first word

    if cmd in ("/exit", "/quit", "/q"):
        console.print("[dim]Goodbye![/]")
        return True

    if cmd == "/clear":
        console.clear()
        return False

    if cmd == "/reset":
        conversation.clear()
        conversation.ensure_system_message()
        print_info("Conversation reset.")
        return False

    if cmd == "/tokens":
        tokens = conversation.estimate_tokens()
        console.print(f"[tokens]Estimated tokens: {tokens:,}[/]")
        return False

    if cmd == "/cost":
        console.print(f"[cost]Session cost: ${session_cost:.4f}[/]")
        console.print(f"[tokens]Tokens: {session_tokens_in:,} in / {session_tokens_out:,} out[/]")
        return False

    if cmd == "/compact":
        print_info("Compaction not yet implemented in this session.")
        return False

    if cmd == "/model":
        await _handle_model_command(conversation)
        return False

    if cmd == "/config":
        _handle_config_command(command)
        return False

    if cmd == "/help":
        print_help()
        return False

    print_error(f"Unknown command: {command}")
    return False


async def _handle_model_command(conversation: ConversationContext) -> None:
    """Handle /model — fetch models from provider and list for selection.

    GET /v1/models from the configured provider base_url.
    """
    import httpx

    config = load_config()
    provider = config.provider_config

    if not provider or not provider.base_url:
        print_warning("No provider configured. Set base_url first:")
        print_info("  /config set provider <name>")
        print_info("  /config set base_url <url>")
        print_info("  /config set api_key <key>")
        return

    # Build models endpoint URL
    base_url = provider.base_url.rstrip("/")
    models_url = f"{base_url}/models"

    # Prepare auth headers
    auth = load_auth()
    headers: dict[str, str] = {"Content-Type": "application/json"}
    if auth.openai_api_key:
        headers["Authorization"] = f"Bearer {auth.openai_api_key}"

    # Fetch models
    print_info(f"Fetching models from {models_url} ...")
    try:
        with httpx.Client(timeout=15) as client:
            resp = client.get(models_url, headers=headers)
            resp.raise_for_status()
            data = resp.json()
    except httpx.HTTPStatusError as e:
        print_error(f"HTTP {e.response.status_code}: {e.response.text[:200]}")
        return
    except Exception as e:
        print_error(f"Failed to fetch models: {e}")
        return

    # Parse model list — handle both {"data": [...]} and plain [...]
    models: list[dict[str, str]] = []
    if isinstance(data, dict) and "data" in data:
        raw_list = data["data"]
    elif isinstance(data, list):
        raw_list = data
    else:
        print_error("Unexpected response format")
        return

    for item in raw_list:
        if isinstance(item, dict) and "id" in item:
            models.append({"id": item["id"], "owned_by": item.get("owned_by", "")})

    if not models:
        print_warning("No models found.")
        return

    # Sort by id
    models.sort(key=lambda m: m["id"])

    # Display models
    from rich.table import Table

    table = Table(title=f"Available Models ({provider.name or config.model_provider})")
    table.add_column("#", style="dim", width=4)
    table.add_column("Model", style="info")
    table.add_column("Owner", style="dim")

    current_model = config.model
    for i, m in enumerate(models, 1):
        marker = " *" if m["id"] == current_model else ""
        table.add_row(str(i), f"{m['id']}{marker}", m.get("owned_by", ""))

    console.print(table)
    console.print()

    if current_model:
        console.print(f"[dim]Current: {current_model} (* = selected)[/]")
    console.print()

    # Prompt for selection
    from prompt_toolkit import PromptSession

    pt_session: PromptSession[str] = PromptSession()
    try:
        selection = await pt_session.prompt_async(
            "Select model (number or name, Enter to cancel): ",
        )
    except (EOFError, KeyboardInterrupt):
        return

    selection = selection.strip()
    if not selection:
        return

    # Resolve selection
    selected_model: str | None = None
    if selection.isdigit():
        idx = int(selection) - 1
        if 0 <= idx < len(models):
            selected_model = models[idx]["id"]
        else:
            print_error(f"Invalid number: {selection}")
            return
    else:
        # Match by name (exact or prefix)
        matches = [m for m in models if m["id"] == selection or m["id"].startswith(selection)]
        if len(matches) == 1:
            selected_model = matches[0]["id"]
        elif len(matches) > 1:
            print_warning(f"Ambiguous: {', '.join(m['id'] for m in matches[:5])}")
            return
        else:
            # Use as-is (user typed exact model name)
            selected_model = selection

    # Save to config
    config.model = selected_model
    save_config(config)
    conversation.model = selected_model
    print_success(f"Model set to: {selected_model}")


def _handle_config_command(command: str) -> None:
    """Handle /config subcommands.

    Usage:
        /config show              — show current config
        /config set model <m>     — set model name
        /config set provider <p>  — set provider name
        /config set base_url <u>  — set provider base URL
        /config set api_key <key> — set OPENAI_API_KEY (stored in auth.json)
    """
    parts = command.split(maxsplit=3)
    config = load_config()
    auth = load_auth()

    if len(parts) < 2 or parts[1] == "show":
        # Show current config
        console.print("[accent]Configuration[/]")
        console.print(f"  MODEL_PROVIDER: [info]{config.model_provider or '(none)'}[/]")
        console.print(f"  MODEL: [info]{config.model or '(none)'}[/]")
        console.print(f"  REASONING_EFFORT: [info]{config.model_reasoning_effort}[/]")

        provider = config.provider_config
        if provider:
            console.print(f"  BASE_URL: [dim]{provider.base_url}[/]")
            console.print(f"  WIRE_API: [dim]{provider.wire_api}[/]")

        # Show key status (not the actual key)
        has_key = bool(auth.openai_api_key)
        console.print(f"  API_KEY: [{'green' if has_key else 'red'}]{'set' if has_key else 'not set'}[/]")
        return

    if parts[1] == "set" and len(parts) >= 4:
        key = parts[2]
        value = parts[3]

        if key == "model":
            config.model = value
            save_config(config)
            print_success(f"Model set to: {value}")

        elif key == "provider":
            config.model_provider = value
            # Create provider entry if it doesn't exist
            if value not in config.model_providers:
                from octopus.config.manager import ProviderConfig
                config.model_providers[value] = ProviderConfig(name=value)
            save_config(config)
            print_success(f"Provider set to: {value}")

        elif key == "base_url":
            # Set base URL for the current provider
            if not config.model_provider:
                print_error("Set provider first: /config set provider <name>")
                return
            if config.model_provider not in config.model_providers:
                from octopus.config.manager import ProviderConfig
                config.model_providers[config.model_provider] = ProviderConfig(
                    name=config.model_provider
                )
            config.model_providers[config.model_provider].base_url = value
            save_config(config)
            print_success(f"Base URL set to: {value}")

        elif key in ("key", "api_key"):
            auth.keys["OPENAI_API_KEY"] = value
            save_auth(auth)
            print_success("API key saved to auth.json")

        else:
            print_error(f"Unknown config key: {key}")
            print_info("Valid keys: model, provider, base_url, key")
        return

    # Show usage
    console.print("[accent]Config commands:[/]")
    console.print("  /config show              — show current config")
    console.print("  /config set model <m>     — set model name")
    console.print("  /config set provider <p>  — set provider name")
    console.print("  /config set base_url <u>  — set provider base URL")
    console.print("  /config set api_key <key> — set OPENAI_API_KEY")


async def session_resume_async(
    session_id: str,
    *,
    model: str | None = None,
    permission_mode: str = "default",
) -> None:
    """Resume a previous session by ID."""
    db_path = _get_db_path()
    if not db_path.exists():
        print_error("No database found. Run `octopus cli` first.")
        return

    await run_interactive_async(
        model=model,
        permission_mode=permission_mode,
        resume_session=session_id,
    )


async def session_new_async(
    *,
    model: str | None = None,
    permission_mode: str = "default",
) -> None:
    """Start a new session (same as interactive mode, explicitly new)."""
    await run_interactive_async(
        model=model,
        permission_mode=permission_mode,
    )


async def show_audit_logs_async(
    limit: int = 20,
    tool: str | None = None,
) -> None:
    """Display recent audit logs."""
    from octopus.core.audit import AuditFilters, AuditLogger

    db_path = _get_db_path()
    if not db_path.exists():
        print_warning("No audit logs found.")
        return

    audit = AuditLogger(db_path=db_path)
    try:
        filters = AuditFilters(limit=limit, tool=tool)
        events = await audit.query(filters)

        if not events:
            print_warning("No audit events found.")
            return

        from rich.table import Table

        table = Table(title="Audit Log", show_lines=True)
        table.add_column("Time", style="dim", width=20)
        table.add_column("Tool", style="cyan", width=15)
        table.add_column("Decision", width=15)
        table.add_column("Duration", width=10)
        table.add_column("Args", max_width=40)

        for e in events:
            time_str = e.timestamp.strftime("%Y-%m-%d %H:%M:%S")
            decision_style = "green" if e.permission_decision == "ALLOWED" else "red"
            args_str = json.dumps(e.args)
            if len(args_str) > 40:
                args_str = args_str[:37] + "..."
            table.add_row(
                time_str,
                e.tool,
                f"[{decision_style}]{e.permission_decision}[/]",
                f"{e.duration:.3f}s",
                args_str,
            )

        console.print(table)
    finally:
        await audit.close()


async def list_sessions_async() -> None:
    """List all sessions with message counts."""
    from octopus.core.state import StateManager

    db_path = _get_db_path()
    if not db_path.exists():
        print_warning("No sessions found.")
        return

    state = StateManager(db_path=db_path)
    try:
        sessions = await state.list_sessions()
        if not sessions:
            print_warning("No sessions found.")
            return

        from rich.table import Table

        table = Table(title="Sessions")
        table.add_column("ID", style="cyan")
        table.add_column("Name")
        table.add_column("Messages", justify="right")
        table.add_column("Created")
        table.add_column("Last Active")

        for s in sessions:
            created = s.start_time.strftime("%Y-%m-%d %H:%M") if s.start_time else "---"
            last = (
                s.last_activity.strftime("%Y-%m-%d %H:%M") if s.last_activity else "---"
            )
            msg_count = len(s.context.get("messages", []))
            table.add_row(
                s.session_id[:8],
                s.name or "(unnamed)",
                str(msg_count),
                created,
                last,
            )

        console.print(table)
    finally:
        await state.close()


async def code_init_async(path: str) -> None:
    """Initialize a workspace -- create .octopus/ config directory."""
    ws = Path(path).resolve()
    octopus_dir = ws / ".octopus"
    octopus_dir.mkdir(parents=True, exist_ok=True)

    config_path = octopus_dir / "config.yaml"
    if not config_path.exists():
        config_path.write_text(
            "# Octopus Agent workspace configuration\n"
            "permissions:\n"
            "  mode: default\n"
            "  allowed_paths:\n"
            f"    - {ws}/**\n"
            "sandbox:\n"
            "  enabled: true\n"
            f"  allowed_paths:\n"
            f"    - {ws}/**\n"
        )
        print_success(f"Created {config_path}")
    else:
        print_info(f"Config already exists at {config_path}")

    db_path = _get_db_path()
    print_success(f"Workspace initialized at {ws}")
    print_info(f"Database: {db_path}")
