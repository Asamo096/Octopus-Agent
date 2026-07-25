"""CLI runtime — async helpers that wire the agent loop to the CLI.

This module bridges the synchronous Typer CLI with the async agent loop.
Handles conversation context persistence, auto-compaction, and styled UI
matching claude-code's terminal patterns.
"""

from __future__ import annotations

import copy
import json
import os
import time
import uuid
from pathlib import Path
from typing import Any

from rich.live import Live

from octopus.cli_ui import (
    COLOR_PRESETS,
    SLASH_COMMANDS,
    TurnStats,
    console,
    display_banner,
    print_assistant_markdown,
    print_assistant_text_stream,
    print_background_message,
    print_context_grid,
    print_error,
    print_help,
    print_info,
    print_prompt_arrow,
    print_separator,
    print_status,
    print_status_line,
    print_stream_newline,
    print_success,
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
SYSTEM_PROMPT = """You are Octopus, an AI coding assistant with harness governance. You are an interactive agent that helps users with software engineering tasks.

# System
- All text you output outside of tool use is displayed to the user. Use Github-flavored markdown for formatting.
- Tools are executed through a permission system. The system handles all permission checks automatically.
- The system will automatically compress prior messages as it approaches context limits.

# Doing tasks
- Execute commands DIRECTLY without asking for confirmation. The permission system handles approvals.
- NEVER ask "are you sure?" or "do you want me to?" — just execute the tool call.
- When given unclear instructions, consider them in the context of software engineering tasks and the current working directory.
- Do not propose changes to code you haven't read. Read files first before modifying them.
- Do not create files unless absolutely necessary. Prefer editing existing files.
- If an approach fails, diagnose why before switching tactics. Don't retry blindly.
- Do not add features, refactor code, or make "improvements" beyond what was asked.
- Do not add error handling for scenarios that can't happen. Trust internal code.

# Using tools
- Use shell commands for file operations (touch, rm, mv, cp, mkdir, cat, etc.)
- Use grep for searching file contents
- Use glob for finding files by pattern
- You can call multiple tools in a single response when they are independent.
- Do NOT ask for confirmation before executing tools. Just call them.

# Safety
- The permission system handles all safety checks. You do not need to verify with the user.
- Never expose secrets, API keys, or credentials in output.
- Be careful not to introduce security vulnerabilities (command injection, XSS, SQL injection).

# Tone and style
- Be concise. Lead with the answer, not the reasoning. Skip filler and preamble.
- When referencing code, include file_path:line_number for easy navigation.
- If you can say it in one sentence, don't use three.
- Do not narrate your plan — just execute the tool calls."""


def _has_markdown(text: str) -> bool:
    """Check if text likely contains markdown formatting."""
    indicators = ["```", "## ", "### ", "- ", "* ", "1. ", "**", "__", "> ", "| "]
    return any(ind in text for ind in indicators)


def _resolve_model(model_arg: str | None) -> str:
    """Resolve model from argument, then config, then None.

    For custom providers with base_url, prefixes model with 'openai/'
    so litellm routes to the OpenAI-compatible API.
    """
    if model_arg:
        return _prefix_model_for_litellm(model_arg)
    config = load_config()
    if config.model:
        return _prefix_model_for_litellm(config.model)
    return ""


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
        "accept_edits": PermissionMode.ACCEPT_EDITS,
        "full_auto": PermissionMode.FULL_AUTO,
    }
    return mapping.get(mode_str, PermissionMode.DEFAULT)


async def _setup_runtime(
    *,
    model: str | None = None,
    permission_mode: str = "default",
    workspace: Path | None = None,
    permission_prompt: Any = None,
) -> tuple[Kernel, ToolRegistry, LiteLLMProvider, Context]:
    """Set up kernel, registry, provider, and context."""
    ws = workspace or Path.cwd()
    db_path = _get_db_path()
    pm = _resolve_permission_mode(permission_mode)

    kernel = Kernel(db_path=db_path, workspace=ws, permission_mode=pm)
    if permission_prompt is not None:
        kernel._permission_prompt = permission_prompt
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

        # Show thinking spinner while waiting for first token
        _first_content_arrived = False
        with Live(
            console.status("[dim]Thinking...[/]", spinner="dots"),
            console=console,
            refresh_per_second=8,
            transient=True,
        ) as live:
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
                # Stop spinner on first content event
                if not _first_content_arrived and event.type in (
                    StreamEventType.TEXT,
                    StreamEventType.TOOL_CALL,
                ):
                    _first_content_arrived = True
                    live.stop()

                if event.type == StreamEventType.TEXT:
                    collected_text.append(event.text or "")
                    print_assistant_text_stream(event.text or "")
                elif event.type == StreamEventType.TOOL_CALL:
                    tc = event.tool_call
                    if tc:
                        tool_call_count += 1
                        print_tool_call_start(tc.name, tc.arguments)
                elif event.type == StreamEventType.STATUS:
                    if not _first_content_arrived:
                        live.stop()
                        _first_content_arrived = True
                    print_status(event.text or "")
                elif event.type == StreamEventType.ERROR:
                    live.stop()
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


def _display_loaded_messages(conversation: ConversationContext) -> None:
    """Display loaded conversation messages after session resume."""
    from octopus.cli_ui import print_assistant_markdown

    # Skip system message
    messages = [m for m in conversation.messages if m.role.value != "system"]

    if not messages:
        return

    console.print()
    console.print("[dim]--- Previous conversation ---[/]")
    console.print()

    for msg in messages:
        if msg.role.value == "user":
            console.print(f"[bold]>[/] {msg.content}")
            console.print()
        elif msg.role.value == "assistant":
            if msg.content:
                # Strip XML artifacts before displaying
                import re

                text = msg.content
                text = re.sub(r"<tool_call>.*?</tool_call>", "", text, flags=re.DOTALL)
                text = re.sub(r"<function=.*?>.*?</function>", "", text, flags=re.DOTALL)
                text = re.sub(r"<thinking>.*?</thinking>", "", text, flags=re.DOTALL)
                text = re.sub(r"<tool_result>.*?</tool_result>", "", text, flags=re.DOTALL)
                text = text.strip()
                if text:
                    print_assistant_markdown(text)
                    console.print()
        elif msg.role.value == "tool":
            # Skip tool results in display
            pass

    console.print("[dim]--- End of previous conversation ---[/]")
    console.print()


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

    async def _permission_prompt(tool_name: str, args: dict, reason: str) -> bool:
        """Prompt user for tool execution approval."""
        from prompt_toolkit import PromptSession
        from prompt_toolkit.formatted_text import HTML

        # Show what the tool wants to do
        if tool_name == "shell":
            cmd = args.get("command", "")
            console.print(f"\n[yellow]Permission required:[/yellow] {reason}")
            console.print(f"[dim]Command: {cmd}[/dim]")
        elif tool_name in ("write_file", "edit_file"):
            path = args.get("path", "")
            console.print(f"\n[yellow]Permission required:[/yellow] {reason}")
            console.print(f"[dim]File: {path}[/dim]")
        else:
            console.print(f"\n[yellow]Permission required:[/yellow] {reason}")

        pt: PromptSession[str] = PromptSession()
        try:
            response = await pt.prompt_async(
                HTML("<prompt>Allow? (y/n): </prompt>"),
            )
            return response.strip().lower() in ("y", "yes", "")
        except (EOFError, KeyboardInterrupt):
            return False

    kernel, registry, provider, ctx = await _setup_runtime(
        model=model,
        permission_mode=permission_mode,
        permission_prompt=_permission_prompt,
    )

    compaction = CompactionEngine()

    try:
        # Load or create conversation context
        conversation: ConversationContext | None = None
        if resume_session:
            conversation = await ConversationContext.load(resume_session, kernel.state)
            if conversation:
                conversation.sanitize()
                print_info(
                    f"Resumed session {resume_session[:8]} ({len(conversation.messages)} messages)"
                )
                # Display loaded messages
                _display_loaded_messages(conversation)
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
        from prompt_toolkit.key_binding import KeyBindings
        from prompt_toolkit.styles import Style

        prompt_style = Style.from_dict({"prompt": "bold #00afff"})

        # Permission mode cycling with shift+tab
        _MODE_CYCLE = ["default", "accept_edits", "full_auto", "plan"]
        _current_mode_index = (
            _MODE_CYCLE.index(permission_mode) if permission_mode in _MODE_CYCLE else 0
        )

        kb = KeyBindings()

        # Interrupt flag — set by Escape, checked during streaming
        _interrupt_requested = False

        @kb.add("s-tab")  # Shift+Tab
        def _cycle_mode(event: object) -> None:
            """Cycle through permission modes: default -> accept_edits -> full_auto -> plan."""
            nonlocal _current_mode_index, permission_mode
            _current_mode_index = (_current_mode_index + 1) % len(_MODE_CYCLE)
            permission_mode = _MODE_CYCLE[_current_mode_index]
            # Update kernel's permission mode
            pm = _resolve_permission_mode(permission_mode)
            kernel.set_permission_mode(pm)

        @kb.add("escape")  # Escape
        def _request_interrupt(event: object) -> None:
            """Request interruption of current generation."""
            nonlocal _interrupt_requested
            _interrupt_requested = True

        # Set up slash command completer
        from prompt_toolkit.completion import Completer, Completion

        class SlashCompleter(Completer):
            """Custom completer for slash commands that filters as user types."""

            def get_completions(self, document: object, complete_event: object) -> list:
                text = document.text  # type: ignore
                # Only complete if input starts with /
                if not text.startswith("/"):
                    return []
                completions = []
                for cmd in SLASH_COMMANDS:
                    name = cmd["name"]
                    desc = cmd["description"]
                    # Match if command starts with typed text
                    if name.startswith(text) or text in desc.lower():
                        completions.append(
                            Completion(
                                name,
                                start_position=-len(text),
                                display_meta=desc,
                            )
                        )
                return completions

        # Status bar as persistent bottom toolbar

        def _get_bottom_toolbar() -> list[tuple[str, str]]:
            """Return bottom toolbar that stays fixed at terminal bottom."""
            from octopus.cli_ui import get_status_bar_style, get_status_bar_text

            text = get_status_bar_text(permission_mode)
            style = get_status_bar_style(permission_mode)
            return [(style, text)]

        pt_session: PromptSession[str] = PromptSession(
            key_bindings=kb,
            completer=SlashCompleter(),
            complete_while_typing=True,
            bottom_toolbar=_get_bottom_toolbar,
        )

        # Session cost tracking
        session_cost = 0.0
        session_tokens_in = 0
        session_tokens_out = 0
        session_tool_calls = 0

        # Additional working directories for this session
        _additional_dirs: list[Path] = []
        # Color preset index for /color cycling
        _color_index = 0

        async def _handle_slash_command(
            command: str,
            conversation: ConversationContext,
        ) -> tuple[bool, ConversationContext]:
            """Handle slash commands. Returns (should_exit, conversation).

            The conversation reference may change on /clear and /branch.
            """
            nonlocal _color_index, prompt_style, session_cost, session_tokens_in
            nonlocal session_tokens_out, session_tool_calls

            parts = command.strip().split()
            cmd = parts[0].lower()
            args = " ".join(parts[1:]) if len(parts) > 1 else ""

            # /exit, /quit, /q
            if cmd in ("/exit", "/quit", "/q"):
                console.print("[dim]Goodbye![/]")
                return True, conversation

            # /help
            if cmd == "/help":
                print_help()
                return False, conversation

            # /init -- generate OCTOPUS.md
            if cmd == "/init":
                await _handle_init_command(conversation)
                return False, conversation

            # /add-dir <path>
            if cmd == "/add-dir":
                _handle_add_dir_command(args, _additional_dirs)
                return False, conversation

            # /background
            if cmd == "/background":
                print_background_message()
                return False, conversation

            # /branch
            if cmd == "/branch":
                conversation = await _handle_branch_command(
                    conversation, kernel, ctx
                )
                return False, conversation

            # /btw <question>
            if cmd == "/btw":
                await _handle_btw_command(args, conversation, provider, kernel, ctx)
                return False, conversation

            # /cd <path>
            if cmd == "/cd":
                _handle_cd_command(args, kernel)
                return False, conversation

            # /clear
            if cmd == "/clear":
                conversation = await _handle_clear_command(
                    conversation, kernel, ctx, model
                )
                # Reset session counters
                session_cost = 0.0
                session_tokens_in = 0
                session_tokens_out = 0
                session_tool_calls = 0
                return False, conversation

            # /color
            if cmd == "/color":
                _color_index, prompt_style = _handle_color_command(
                    args, _color_index
                )
                return False, conversation

            # /compact
            if cmd == "/compact":
                await _handle_compact_command(
                    conversation, compaction, kernel
                )
                return False, conversation

            # /config
            if cmd == "/config":
                _handle_config_command(command)
                return False, conversation

            # /context
            if cmd == "/context":
                _handle_context_command(conversation, compaction)
                return False, conversation

            # /model
            if cmd == "/model":
                await _handle_model_command(conversation)
                return False, conversation

            # /tokens
            if cmd == "/tokens":
                tokens = conversation.estimate_tokens()
                console.print(f"[tokens]Estimated tokens: {tokens:,}[/]")
                return False, conversation

            # /reset
            if cmd == "/reset":
                conversation.clear()
                conversation.ensure_system_message()
                print_info("Conversation reset.")
                return False, conversation

            print_error(f"Unknown command: {command}")
            return False, conversation

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
                should_exit, conversation = await _handle_slash_command(
                    user_input.strip(),
                    conversation,
                )
                if should_exit:
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

            # Reset interrupt flag at start of each turn
            _interrupt_requested = False

            # Show thinking spinner while waiting for first token
            _first_content_arrived = False
            with Live(
                console.status("[dim]Thinking...[/]", spinner="dots"),
                console=console,
                refresh_per_second=8,
                transient=True,
            ) as live:
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
                    # Check for interrupt request (Escape key)
                    if _interrupt_requested:
                        live.stop()
                        console.print("\n[dim]Interrupted.[/]")
                        break

                    # Stop spinner on first content event
                    if not _first_content_arrived and event.type in (
                        StreamEventType.TEXT,
                        StreamEventType.TOOL_CALL,
                    ):
                        _first_content_arrived = True
                        live.stop()

                    if event.type == StreamEventType.TEXT:
                        collected_text.append(event.text or "")

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
                        if not _first_content_arrived:
                            live.stop()
                            _first_content_arrived = True
                        print_status(event.text or "")

                    elif event.type == StreamEventType.ERROR:
                        live.stop()
                        print_error(event.error or "Unknown error")

                    elif event.type == StreamEventType.DONE:
                        pass

            # Close any unclosed tool
            if current_tool is not None:
                print_tool_call_result(current_tool, "")

            # Render response as markdown (strip XML tool calls first)
            if collected_text:
                full_text = "".join(collected_text)
                # Strip XML tool calls and model artifacts
                import re

                full_text = re.sub(
                    r"<tool_call>.*?</tool_call>", "", full_text, flags=re.DOTALL
                )
                full_text = re.sub(
                    r"<function=.*?>.*?</function>", "", full_text, flags=re.DOTALL
                )
                full_text = re.sub(
                    r"<thinking>.*?</thinking>", "", full_text, flags=re.DOTALL
                )
                full_text = re.sub(
                    r"<tool_result>.*?</tool_result>", "", full_text, flags=re.DOTALL
                )
                full_text = re.sub(r"<\|.*?\|>", "", full_text)
                full_text = full_text.strip()
                if full_text:
                    console.print()
                    print_assistant_markdown(full_text)

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




async def _handle_model_command(conversation: ConversationContext) -> None:
    """Handle /model — fetch models from provider and list for selection.

    For providers with base_url: GET /v1/models
    For litellm-native providers: use known model list
    """
    import httpx

    config = load_config()
    provider = config.provider_config
    model_provider = config.model_provider

    models: list[dict[str, str]] = []

    # Try fetching from provider API if base_url is set
    if provider and provider.base_url:
        base_url = provider.base_url.rstrip("/")
        models_url = f"{base_url}/models"

        auth = load_auth()
        headers: dict[str, str] = {"Content-Type": "application/json"}
        if auth.openai_api_key:
            headers["Authorization"] = f"Bearer {auth.openai_api_key}"

        print_info(f"Fetching models from {models_url} ...")
        try:
            with httpx.Client(timeout=15) as client:
                resp = client.get(models_url, headers=headers)
                resp.raise_for_status()
                data = resp.json()

            # Parse model list
            raw_list = data.get("data", data) if isinstance(data, dict) else data
            if isinstance(raw_list, list):
                for item in raw_list:
                    if isinstance(item, dict) and "id" in item:
                        models.append(
                            {"id": item["id"], "owned_by": item.get("owned_by", "")}
                        )
        except Exception as e:
            print_warning(f"Could not fetch models: {e}")

    # Fallback: use known models for litellm-native providers
    if not models and model_provider:
        known_models = _get_known_models(model_provider)
        if known_models:
            models = [{"id": m, "owned_by": model_provider} for m in known_models]
        else:
            # Let user type model name manually
            print_info(f"No model list available for provider '{model_provider}'.")
            print_info(
                "You can set a model directly with: /config set model <model-name>"
            )
            return

    if not models:
        print_warning("No models found. Configure provider first:")
        print_info("  /config set provider <name>")
        print_info(
            "  /config set base_url <url>  (optional for litellm-native providers)"
        )
        print_info("  /config set api_key <key>")
        return

    # Sort by id
    models.sort(key=lambda m: m["id"])

    # Build selection options
    current_model = config.model
    model_ids = [m["id"] for m in models]

    # Find initial selection index
    initial_index = 0
    if current_model and current_model in model_ids:
        initial_index = model_ids.index(current_model)

    # Use arrow key selection
    from octopus.cli_ui import select_option

    selected_model = select_option(
        model_ids,
        title=f"Available Models ({model_provider or 'unknown'})",
        initial_index=initial_index,
    )

    if not selected_model:
        return

    # Save to config
    config.model = selected_model
    save_config(config)
    conversation.model = selected_model
    print_success(f"Model set to: {selected_model}")


def _get_known_models(provider: str) -> list[str]:
    """Get known models for litellm-native providers."""
    known: dict[str, list[str]] = {
        "xiaomi_mimo": [
            "mimo-v2.5",
            "mimo-v2.5-asr",
            "mimo-v2.5-pro",
            "mimo-v2.5-tts",
            "mimo-v2.5-tts-voiceclone",
            "mimo-v2.5-tts-voicedesign",
        ],
        "openai": [
            "gpt-4o",
            "gpt-4o-mini",
            "gpt-4-turbo",
            "o1",
            "o1-mini",
            "o3-mini",
        ],
        "anthropic": [
            "claude-sonnet-4-20250514",
            "claude-opus-4-20250514",
            "claude-haiku-4-5-20251001",
        ],
        "deepseek": [
            "deepseek-chat",
            "deepseek-reasoner",
        ],
    }
    return known.get(provider, [])


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
        console.print(
            f"  API_KEY: [{'green' if has_key else 'red'}]{'set' if has_key else 'not set'}[/]"
        )
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


# ---------------------------------------------------------------------------
# /init handler
# ---------------------------------------------------------------------------


async def _handle_init_command(conversation: ConversationContext) -> None:
    """Generate OCTOPUS.md with project overview, structure, and conventions.

    Scans the workspace directory, detects project type, and generates
    a comprehensive OCTOPUS.md file.
    """
    workspace = Path.cwd()

    # Scan for project indicators
    indicators: dict[str, Path] = {}
    manifest_files = [
        "pyproject.toml",
        "package.json",
        "Cargo.toml",
        "go.mod",
        "pom.xml",
        "build.gradle",
        "Makefile",
        "CMakeLists.txt",
        ".git",
    ]
    for fname in manifest_files:
        p = workspace / fname
        if p.exists():
            indicators[fname] = p

    # Detect project type
    project_type = "unknown"
    languages: list[str] = []
    build_commands: list[str] = []
    test_commands: list[str] = []
    lint_commands: list[str] = []

    if "pyproject.toml" in indicators:
        project_type = "Python"
        languages.append("Python")
        try:
            content = (workspace / "pyproject.toml").read_text()
            if "hatchling" in content:
                build_commands.append("pip install -e .")
            if "pytest" in content:
                test_commands.append("pytest")
            if "ruff" in content:
                lint_commands.append("ruff check .")
                lint_commands.append("ruff format --check .")
            if "mypy" in content:
                lint_commands.append("mypy src/")
        except Exception:
            pass
    if "package.json" in indicators:
        project_type = "Node.js/TypeScript"
        languages.append("TypeScript")
        languages.append("JavaScript")
        try:
            import json as _json

            pkg = _json.loads((workspace / "package.json").read_text())
            scripts = pkg.get("scripts", {})
            if "build" in scripts:
                build_commands.append("npm run build")
            if "test" in scripts:
                test_commands.append("npm test")
            if "lint" in scripts:
                lint_commands.append("npm run lint")
        except Exception:
            pass
    if "Cargo.toml" in indicators:
        project_type = "Rust"
        languages.append("Rust")
        build_commands.append("cargo build")
        test_commands.append("cargo test")
        lint_commands.append("cargo clippy")
    if "go.mod" in indicators:
        project_type = "Go"
        languages.append("Go")
        build_commands.append("go build ./...")
        test_commands.append("go test ./...")
        lint_commands.append("golangci-lint run")

    # Collect top-level directory structure
    dir_entries: list[str] = []
    try:
        for entry in sorted(workspace.iterdir()):
            name = entry.name
            if name.startswith(".") and name not in (".github", ".gitignore"):
                continue
            if name in ("__pycache__", "node_modules", ".venv", "venv", "dist", "build", "target"):
                continue
            if entry.is_dir():
                dir_entries.append(f"  {name}/")
            else:
                dir_entries.append(f"  {name}")
    except PermissionError:
        pass

    # Check for existing conventions files
    conventions: list[str] = []
    for conv_file in (".editorconfig", ".prettierrc", ".eslintrc", "ruff.toml", ".ruff.toml"):
        if (workspace / conv_file).exists():
            conventions.append(conv_file)
    if (workspace / ".github" / "workflows").exists():
        conventions.append(".github/workflows/ (CI)")

    # Build OCTOPUS.md content
    lines: list[str] = []
    lines.append("# OCTOPUS.md")
    lines.append("")
    lines.append("This file provides guidance to Octopus Agent when working in this repository.")
    lines.append("")

    # Project overview
    lines.append("## Project Overview")
    lines.append("")
    lines.append(f"- **Type**: {project_type}")
    if languages:
        lines.append(f"- **Languages**: {', '.join(languages)}")
    lines.append(f"- **Root**: `{workspace}`")
    lines.append("")

    # Build / Test / Lint
    if build_commands or test_commands or lint_commands:
        lines.append("## Common Commands")
        lines.append("")
        if build_commands:
            lines.append("**Build:**")
            for cmd in build_commands:
                lines.append(f"```bash\n{cmd}\n```")
            lines.append("")
        if test_commands:
            lines.append("**Test:**")
            for cmd in test_commands:
                lines.append(f"```bash\n{cmd}\n```")
            lines.append("")
        if lint_commands:
            lines.append("**Lint:**")
            for cmd in lint_commands:
                lines.append(f"```bash\n{cmd}\n```")
            lines.append("")

    # Directory structure
    if dir_entries:
        lines.append("## Directory Structure")
        lines.append("")
        lines.append("```")
        lines.extend(dir_entries[:40])  # Cap at 40 entries
        lines.append("```")
        lines.append("")

    # Conventions
    if conventions:
        lines.append("## Conventions")
        lines.append("")
        for conv in conventions:
            lines.append(f"- `{conv}`")
        lines.append("")

    # Write the file
    octopus_md = workspace / "OCTOPUS.md"
    if octopus_md.exists():
        print_warning(f"OCTOPUS.md already exists at {octopus_md}")
        print_info("To regenerate, delete the existing file first.")
        return

    octopus_md.write_text("\n".join(lines))
    print_success(f"Generated {octopus_md}")
    print_info(f"  {project_type} project with {len(dir_entries)} top-level entries")

    # Add the init prompt as a user message to trigger the LLM to refine
    init_prompt = (
        "I just generated an initial OCTOPUS.md for this project. "
        "Please review it and suggest improvements. The file is at the project root."
    )
    conversation.add_message(Message(role=Role.USER, content=init_prompt))
    print_info("Added init review prompt to conversation.")


# ---------------------------------------------------------------------------
# /add-dir handler
# ---------------------------------------------------------------------------


def _handle_add_dir_command(
    args: str, additional_dirs: list[Path]
) -> None:
    """Add a directory to the session's working directories."""
    if not args.strip():
        print_error("Usage: /add-dir <path>")
        print_info("Example: /add-dir ../other-project")
        return

    target = Path(args.strip()).resolve()

    if not target.exists():
        print_error(f"Directory does not exist: {target}")
        return

    if not target.is_dir():
        print_error(f"Not a directory: {target}")
        return

    if target in additional_dirs:
        print_warning(f"Directory already added: {target}")
        return

    additional_dirs.append(target)
    os.environ["OCTOPUS_WORKSPACE"] = str(target)
    print_success(f"Added working directory: {target}")
    print_info(f"  Total additional directories: {len(additional_dirs)}")


# ---------------------------------------------------------------------------
# /branch handler
# ---------------------------------------------------------------------------


async def _handle_branch_command(
    conversation: ConversationContext,
    kernel: Any,
    ctx: Any,
) -> ConversationContext:
    """Save current conversation state and start a new branch.

    Clones the current ConversationContext with a new session_id,
    saves both, and returns the new context.
    """
    # Save current conversation
    await conversation.save(kernel.state)

    # Clone with new session_id
    new_ctx = ConversationContext(
        session_id=str(uuid.uuid4()),
        system_prompt=conversation.system_prompt,
        model=conversation.model,
        max_tokens=conversation.max_tokens,
        messages=copy.deepcopy(conversation.messages),
    )

    # Create the new session in the state manager
    await kernel.state.create_session(
        new_ctx.session_id,
        workspace=str(ctx.workspace) if ctx.workspace else None,
    )
    await new_ctx.save(kernel.state)

    print_success(f"Branched to new session: {new_ctx.session_id[:8]}")
    print_info(f"  Previous session: {conversation.session_id[:8]}")
    print_info(f"  Messages carried over: {len(new_ctx.messages)}")

    return new_ctx


# ---------------------------------------------------------------------------
# /btw handler
# ---------------------------------------------------------------------------


async def _handle_btw_command(
    args: str,
    conversation: ConversationContext,
    provider: Any,
    kernel: Any,
    ctx: Any,
) -> None:
    """Ask a side question without interrupting the main conversation.

    Sends a separate query to the LLM with a minimal context (just the
    question), displays the answer, and does NOT add it to the main
    conversation history.
    """
    question = args.strip()
    if not question:
        print_error("Usage: /btw <your question>")
        return

    from octopus.loop.models import Role as R
    from octopus.loop.models import StreamEventType

    console.print()
    console.print(f"[warning]/btw[/] [dim]{question}[/]")
    console.print()

    # Build a minimal conversation for the side question
    side_ctx = ConversationContext(
        session_id=str(uuid.uuid4()),
        system_prompt=(
            "You are a helpful assistant answering a quick side question. "
            "Be concise. Answer in 1-3 sentences unless more detail is needed."
        ),
        model=conversation.model,
    )
    side_ctx.ensure_system_message()
    side_ctx.add_message(Message(role=R.USER, content=question))

    collected: list[str] = []

    try:
        async for event in provider.stream(
            side_ctx.messages,
            [],
            conversation.model,
            max_tokens=1024,
        ):
            if event.type == StreamEventType.TEXT:
                collected.append(event.text or "")
            elif event.type == StreamEventType.ERROR:
                print_error(event.error or "Unknown error")
                return
    except Exception as e:
        print_error(f"Side question failed: {e}")
        return

    if collected:
        answer = "".join(collected).strip()
        console.print()
        print_assistant_markdown(answer)
        console.print()
        print_info("(Not added to main conversation)")
    else:
        print_warning("No response received.")


# ---------------------------------------------------------------------------
# /cd handler
# ---------------------------------------------------------------------------


def _handle_cd_command(args: str, kernel: Any) -> None:
    """Change the working directory."""
    if not args.strip():
        # Go to home directory
        target = Path.home()
    else:
        target = Path(args.strip()).expanduser()

    if not target.exists():
        print_error(f"Directory does not exist: {target}")
        return

    if not target.is_dir():
        print_error(f"Not a directory: {target}")
        return

    target = target.resolve()
    try:
        os.chdir(target)
    except PermissionError:
        print_error(f"Permission denied: {target}")
        return

    # Update kernel workspace
    kernel.workspace = target
    print_success(f"Changed directory to: {target}")


# ---------------------------------------------------------------------------
# /clear handler
# ---------------------------------------------------------------------------


async def _handle_clear_command(
    conversation: ConversationContext,
    kernel: Any,
    ctx: Any,
    model: str | None,
) -> ConversationContext:
    """Save current conversation and start a new session."""
    # Save current conversation before clearing
    await conversation.save(kernel.state)
    print_info(f"Previous session saved: {conversation.session_id[:8]}")

    # Create a new conversation context
    new_session_id = str(uuid.uuid4())
    new_conversation = ConversationContext(
        session_id=new_session_id,
        system_prompt=SYSTEM_PROMPT,
        model=_resolve_model(model),
    )
    new_conversation.ensure_system_message()

    # Create new session in state manager
    await kernel.state.create_session(
        new_session_id,
        workspace=str(ctx.workspace) if ctx.workspace else None,
    )
    await new_conversation.save(kernel.state)

    console.clear()
    print_success(f"New session started: {new_session_id[:8]}")

    return new_conversation


# ---------------------------------------------------------------------------
# /color handler
# ---------------------------------------------------------------------------


def _handle_color_command(
    args: str, current_index: int
) -> tuple[int, Any]:
    """Change the prompt bar color.

    Usage:
        /color          — cycle to next color
        /color blue     — set specific color
        /color list     — show available colors
        /color default  — reset to default (blue)

    Returns (new_color_index, new_prompt_style).
    """
    from prompt_toolkit.styles import Style

    if args.strip() == "list":
        console.print("[accent]Available colors:[/]")
        for i, preset in enumerate(COLOR_PRESETS):
            marker = " <-- current" if i == current_index else ""
            console.print(f"  [{preset['style']}]{preset['name']}[/] - {preset['label']}{marker}")
        return current_index, Style.from_dict({"prompt": COLOR_PRESETS[current_index]["style"]})

    if args.strip() in ("default", "reset"):
        return 0, Style.from_dict({"prompt": COLOR_PRESETS[0]["style"]})

    # Try to find by name
    if args.strip():
        target = args.strip().lower()
        for i, preset in enumerate(COLOR_PRESETS):
            if preset["name"] == target:
                console.print(f"[{preset['style']}]Color set to: {preset['name']}[/]")
                return i, Style.from_dict({"prompt": preset["style"]})
        print_error(f"Unknown color: {args.strip()}")
        _names = ", ".join(p["name"] for p in COLOR_PRESETS)
        print_info(f"Available: {_names}, default")
        return current_index, Style.from_dict({"prompt": COLOR_PRESETS[current_index]["style"]})

    # Cycle to next color
    new_index = (current_index + 1) % len(COLOR_PRESETS)
    preset = COLOR_PRESETS[new_index]
    console.print(f"[{preset['style']}]Color: {preset['name']}[/]")
    return new_index, Style.from_dict({"prompt": preset["style"]})


# ---------------------------------------------------------------------------
# /compact handler
# ---------------------------------------------------------------------------


async def _handle_compact_command(
    conversation: ConversationContext,
    compaction: Any,
    kernel: Any,
) -> None:
    """Force conversation compaction using the CompactionEngine."""
    tokens_before = conversation.estimate_tokens()
    print_info(f"Context before compaction: {tokens_before:,} tokens")

    result = compaction.auto_compact(conversation)

    if not result.compacted:
        print_info("Conversation is within limits, no compaction needed.")
        return

    tokens_after = conversation.estimate_tokens()
    print_success(
        f"Compacted: {tokens_before:,} -> {tokens_after:,} tokens "
        f"({result.strategy.value if result.strategy else 'unknown'})"
    )

    # Persist the compacted conversation
    await conversation.save(kernel.state)


# ---------------------------------------------------------------------------
# /context handler
# ---------------------------------------------------------------------------


def _handle_context_command(
    conversation: ConversationContext,
    compaction: Any,
) -> None:
    """Show context usage as a colored grid.

    Breaks down token usage by category: system prompt, messages, tool results.
    """
    messages = conversation.messages

    system_tokens = 0
    message_tokens = 0
    tool_tokens = 0

    for msg in messages:
        content_len = len(msg.content) if msg.content else 0
        tc_len = 0
        if msg.tool_calls:
            for tc in msg.tool_calls:
                tc_len += len(tc.name) + len(tc.arguments)

        # Estimate tokens for this message
        msg_tokens = (content_len + tc_len) // 4  # ~4 chars per token

        if msg.role.value == "system":
            system_tokens += msg_tokens
        elif msg.role.value == "tool":
            tool_tokens += msg_tokens
        else:
            message_tokens += msg_tokens

    total_tokens = system_tokens + message_tokens + tool_tokens

    print_context_grid(
        system_tokens=system_tokens,
        message_tokens=message_tokens,
        tool_tokens=tool_tokens,
        total_tokens=total_tokens,
        max_context=compaction.auto_compact_threshold,
    )


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
