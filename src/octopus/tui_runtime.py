"""TUI runtime — wires the Textual TUI to the Octopus agent loop.

Bridges the Textual UI with the agent loop kernel, handling:
- Message passing between UI and agent
- Streaming response display
- Tool execution with status updates
- Slash command dispatch
- Session persistence
- Permission mode management
"""

from __future__ import annotations

import asyncio
import re
import uuid
from pathlib import Path
from typing import Any, TYPE_CHECKING

from octopus.runtime import (
    SYSTEM_PROMPT,
    _get_db_path,
    _resolve_model,
    _resolve_permission_mode,
    _strip_xml_artifacts,
)
from octopus.config.manager import load_auth, load_config
from octopus.core.kernel import Context, Kernel
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

if TYPE_CHECKING:
    from octopus.tui.app import OctopusTUI


async def run_tui_async(
    *,
    model: str | None = None,
    permission_mode: str = "default",
    resume_session: str | None = None,
) -> None:
    """Launch the Textual TUI application.

    Sets up kernel, provider, tools, conversation context, then runs
    the Textual app with the agent loop wired to the chat interface.
    """
    from octopus.tui.app import OctopusTUI

    # ---- Setup runtime ----
    ws = Path.cwd()
    db_path = _get_db_path()
    pm = _resolve_permission_mode(permission_mode)

    kernel = Kernel(db_path=db_path, workspace=ws, permission_mode=pm)
    await kernel.initialize()

    # Register tools
    registry = ToolRegistry()
    for register_fn in [
        register_filesystem_tools,
        register_shell_tool,
        register_git_tool,
        register_diff_tools,
        register_search_tools,
    ]:
        register_fn(registry, kernel)

    # Provider setup
    config = load_config()
    auth = load_auth()
    api_key = auth.openai_api_key
    if api_key and config.model_provider:
        import os
        os.environ[f"{config.model_provider.upper()}_API_KEY"] = api_key

    base_url: str | None = None
    for p in config.model_providers.values():
        if p.base_url:
            base_url = p.base_url
            break

    provider = LiteLLMProvider(api_key=api_key, base_url=base_url)
    resolved_model = _resolve_model(model)
    session_id = resume_session or str(uuid.uuid4())

    ctx = Context(
        session_id=session_id,
        kernel=kernel,
        workspace=ws,
        permission_mode=pm,
    )

    compaction = CompactionEngine()

    # ---- Load or create conversation ----
    conversation: ConversationContext
    if resume_session:
        loaded = await ConversationContext.load(resume_session, kernel.state)
        if loaded:
            loaded.sanitize()
            conversation = loaded
        else:
            conversation = _new_conversation(session_id, model)
    else:
        conversation = _new_conversation(session_id, model)
        # Inject working directory so model knows its environment
        import platform
        import os as _os
        conversation.add_message(Message(
            role=Role.SYSTEM,
            content=(
                f"Working directory: {ws}\n"
                f"OS: {platform.system()} {platform.release()}\n"
                f"Shell: {_os.environ.get('SHELL', 'bash')}\n"
                f"Use absolute or relative paths as needed. The workspace is {ws}."
            ),
        ))

    await kernel.state.create_session(session_id, workspace=str(ws))

    # ---- Create TUI app ----
    app = OctopusTUI(
        model=resolved_model,
        permission_mode=permission_mode,
        workspace=str(ws),
        session_id=session_id,
        kernel=kernel,
        provider=provider,
        tool_registry=registry,
        ctx=ctx,
        conversation=conversation,
    )

    # ---- Input handler ----
    # Use a queue-based approach: the TUI input widget pushes to a queue,
    # and an asyncio task processes messages through the agent loop.
    input_queue: asyncio.Queue[str] = asyncio.Queue()
    app._input_queue = input_queue  # type: ignore[attr-defined]
    app._interrupt_requested = False  # type: ignore[attr-defined]

    async def _process_messages() -> None:
        """Background task: process input from queue through agent loop."""
        while True:
            text = await input_queue.get()

            if text.startswith("/"):
                await _handle_slash_command(text, app, conversation, kernel, compaction)
                continue

            # User message
            conversation.add_message(Message(role=Role.USER, content=text))
            app.add_user_message(text)

            # Run agent loop with streaming + tool cards
            turn_tool_calls = 0
            streaming_started = False
            first_token = False
            raw_text: list[str] = []
            active_cards: dict[str, Any] = {}  # tool_call_id → card widget

            # Show Thinking... immediately, yield to let Textual render it
            app.show_thinking()
            await asyncio.sleep(0)

            try:
                async for event in run_query(
                    conversation.messages,
                    provider,
                    kernel,
                    registry,
                    ctx,
                    model=resolved_model,
                    conversation=conversation,
                    compaction=compaction,
                ):
                    if getattr(app, "_interrupt_requested", False):
                        app._interrupt_requested = False  # type: ignore
                        app.hide_thinking()
                        app.add_system_message("[Interrupted]")
                        break

                    if event.type == StreamEventType.TEXT:
                        chunk = event.text or ""
                        raw_text.append(chunk)

                        # Separate thinking from real content
                        think_match = re.search(r"<thinking>(.*?)</thinking>", chunk, re.DOTALL)
                        if think_match:
                            think_text = think_match.group(1)
                            if not hasattr(app, "_thinking_streaming"):
                                app._thinking_streaming = True
                                app.begin_thinking_stream()
                            app.append_thinking(think_text)
                            chunk = re.sub(r"<thinking>.*?</thinking>", "", chunk, flags=re.DOTALL)

                        # Suppress display of XML tool call blocks that span multiple chunks.
                        # Buffer incomplete blocks until closing tag arrives.
                        if not hasattr(app, "_xml_buffer"):
                            app._xml_buffer = ""
                        app._xml_buffer += chunk
                        # If we have a complete tool_call block (or no tool_call at all),
                        # extract display text and keep the rest buffered
                        if "</tool_call>" in app._xml_buffer or "<tool_call>" not in app._xml_buffer:
                            chunk = app._xml_buffer
                            app._xml_buffer = ""
                        else:
                            # Block is incomplete — suppress display until we get closing tag
                            chunk = ""

                        # Real content: hide thinking, show stream
                        if chunk.strip():
                            if not first_token:
                                first_token = True
                                app.hide_thinking()
                                app.finish_thinking()
                                app._thinking_streaming = False
                            chunk = _strip_xml_artifacts(chunk)
                            if chunk.strip():
                                if not streaming_started:
                                    app.begin_streaming()
                                    streaming_started = True
                                app.append_stream(chunk)

                    elif event.type == StreamEventType.TOOL_CALL:
                        if not first_token:
                            first_token = True
                            app.hide_thinking()
                        tc = event.tool_call
                        if tc:
                            turn_tool_calls += 1
                            # Cache file content before write/edit for diff
                            _cache_file_before_write(app, tc)
                            card = app.add_tool_card(tc.name, tc.arguments)
                            active_cards[tc.id or str(turn_tool_calls)] = card

                    elif event.type == StreamEventType.STATUS:
                        if event.tool_data and event.tool_data.get("tool_call_id"):
                            tid = event.tool_data["tool_call_id"]
                            if tid in active_cards:
                                result_text = event.text or ""
                                tool_name = event.tool_data.get("tool_name", "")
                                old_content, new_content, file_path = (
                                    _get_diff_content(app, event.tool_data)
                                )
                                app.update_tool_card(
                                    active_cards[tid], tool_name, result_text,
                                    old_content=old_content, new_content=new_content,
                                    file_path=file_path,
                                )
                                # Also show diff in sidebar panel
                                if file_path and (old_content or new_content):
                                    app.show_diff(old_content, new_content, file_path)

                    elif event.type == StreamEventType.ERROR:
                        app.add_error_message(event.error or "Unknown error")
                    elif event.type == StreamEventType.DONE:
                        pass

                # Finalize streaming
                if raw_text:
                    full = "".join(raw_text)
                    full = _strip_xml_artifacts(full)
                    if full.strip():
                        if streaming_started:
                            app.finish_streaming(full.strip())
                        else:
                            app.add_assistant_message(full.strip())

                # Update token display after turn
                tokens = conversation.estimate_tokens()
                status = app.query_one("#status-bar")
                status.update_tokens(tokens)
                await conversation.save(kernel.state)

            except Exception as e:
                app.hide_thinking()
                msg = str(e).lower()
                if "connect" in msg or "name or service not known" in msg:
                    app.add_error_message(
                        "Cannot reach API. Check network and base_url in /config."
                    )
                elif "401" in msg or "unauthorized" in msg:
                    app.add_error_message(
                        "Auth failed. Check API key in ~/.octopus/auth.json"
                    )
                elif "429" in msg or "rate limit" in msg:
                    app.add_error_message(
                        "Rate limited. Wait a moment and try again."
                    )
                elif "timeout" in msg:
                    app.add_error_message(
                        "Request timed out. Provider may be slow."
                    )
                else:
                    app.add_error_message(f"[dim]{str(e)}[/]")

    # Start the message processor
    _task = asyncio.create_task(_process_messages())

    # on_chat_input_submitted is defined on OctopusTUI class -
    # it pushes to app._input_queue, then _process_messages dispatches.

    # ---- Run the TUI ----
    try:
        await app.run_async()
    finally:
        _task.cancel()
        try:
            await _task
        except asyncio.CancelledError:
            pass
        await kernel.shutdown()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _new_conversation(session_id: str, model: str | None) -> ConversationContext:
    ctx = ConversationContext(
        session_id=session_id,
        system_prompt=SYSTEM_PROMPT,
        model=_resolve_model(model),
    )
    ctx.ensure_system_message()
    return ctx


# ---------------------------------------------------------------------------
# Slash command dispatch
# ---------------------------------------------------------------------------


async def _handle_slash_command(
    command: str,
    app: "OctopusTUI",
    conversation: ConversationContext,
    kernel: Kernel,
    compaction: CompactionEngine,
) -> None:
    """Dispatch a slash command in the TUI."""
    parts = command.strip().split()
    cmd = parts[0].lower()
    args = " ".join(parts[1:]) if len(parts) > 1 else ""

    if cmd in ("/exit", "/quit", "/q"):
        app.add_system_message("Goodbye!")
        app.exit()
        return

    if cmd == "/help":
        _show_help(app)
        return

    if cmd == "/clear":
        await conversation.save(kernel.state)
        new_id = str(uuid.uuid4())
        conversation.session_id = new_id
        conversation.clear()
        conversation.ensure_system_message()
        await kernel.state.create_session(new_id, workspace=str(kernel.workspace))
        app.clear_chat()
        app.add_system_message(f"New session: {new_id[:8]}")
        return

    if cmd == "/audit":
        await _handle_audit(app, kernel, args)
        return

    if cmd == "/compact":
        before = conversation.estimate_tokens()
        result = compaction.auto_compact(conversation)
        after = conversation.estimate_tokens()
        if result.compacted:
            app.add_system_message(
                f"Compacted: {before:,} -> {after:,} tokens"
            )
        else:
            app.add_system_message("Context within limits.")
        await conversation.save(kernel.state)
        return

    if cmd == "/config":
        _show_config(app, args)
        return

    if cmd == "/context":
        total = conversation.estimate_tokens()
        app.add_system_message(
            f"Context: {total:,} tokens, "
            f"{len(conversation.messages)} messages, "
            f"threshold: {compaction.auto_compact_threshold:,}"
        )
        return

    if cmd == "/theme":
        if args:
            _handle_theme(app, args)
        else:
            _list_themes(app)
        return

    if cmd == "/effort":
        _handle_effort(app, args)
        return

    if cmd == "/model":
        await _select_model(app, conversation)
        return

    if cmd == "/tokens":
        app.add_system_message(f"Estimated tokens: {conversation.estimate_tokens():,}")
        return

    if cmd == "/reset":
        conversation.clear()
        conversation.ensure_system_message()
        app.clear_chat()
        app.add_system_message("Conversation reset.")
        return

    if cmd == "/cd":
        target = Path(args).expanduser() if args else Path.home()
        if target.exists() and target.is_dir():
            import os
            os.chdir(target)
            kernel.workspace = target
            app.add_system_message(f"Changed to: {target}")
        else:
            app.add_error_message(f"Directory not found: {target}")
        return

    # Bare / — show available commands
    if cmd == "/":
        _show_help(app)
        return

    # Unknown
    app.add_system_message(
        f"Unknown: {cmd}. Try /help for commands."
    )


def _show_help(app: "OctopusTUI") -> None:
    app.add_system_message(
        "Commands:\n"
        "/help        Show this help\n"
        "/audit       View audit trail of all actions\n"
        "/clear       New session\n"
        "/compact     Force compaction\n"
        "/config      Show config\n"
        "/context     Show context usage\n"
        "/model       Select model\n"
        "/theme       Switch theme (dark / light / contrast)\n"
        "/effort      Set reasoning effort (low/medium/high/max)\n"
        "/tokens      Token estimate\n"
        "/reset       Reset conversation\n"
        "/cd <path>   Change directory\n"
        "/exit        Quit\n"
        "\nShortcuts: Ctrl+P mode, Ctrl+L input, Ctrl+C quit"
    )


def _show_config(app: "OctopusTUI", args: str) -> None:
    config = load_config()
    auth = load_auth()
    lines = [
        f"MODEL_PROVIDER: {config.model_provider or '(none)'}",
        f"MODEL: {config.model or '(none)'}",
        f"REASONING: {config.model_reasoning_effort}",
        f"API_KEY: {'set' if auth.openai_api_key else 'not set'}",
    ]
    for pname, pcfg in config.model_providers.items():
        if pcfg.base_url:
            lines.append(f"BASE_URL ({pname}): {pcfg.base_url}")
    app.add_system_message("\n".join(lines))


async def _handle_audit(app: "OctopusTUI", kernel: Kernel, args: str) -> None:
    """Show recent audit log entries with color-coded decisions."""
    limit = 20
    tool_filter = None
    if args:
        for part in args.split():
            if part.isdigit():
                limit = min(int(part), 100)
            else:
                tool_filter = part

    events = await kernel.audit.query()
    if tool_filter:
        events = [e for e in events if e.tool == tool_filter]
    events = events[-limit:]

    if not events:
        app.add_system_message("No audit events found.")
        return

    lines = ["[bold]Audit Trail[/]\n"]
    for e in reversed(events):
        ts = e.timestamp.strftime("%H:%M:%S")
        if e.permission_decision == "ALLOWED":
            color = "#7ee787"
        elif e.permission_decision == "DENIED":
            color = "#f85149"
        elif e.permission_decision == "USER_DENIED":
            color = "#d29922"
        else:
            color = "#8b949e"

        args_str = str(e.args)[:60]
        dur = f"{e.duration:.0f}ms" if e.duration < 1 else f"{e.duration:.1f}s"
        lines.append(
            f"[dim]{ts}[/]  [{color}]{e.tool}[/]  "
            f"[dim]{args_str}[/]  [{color}]{e.permission_decision}[/]  "
            f"[dim]{dur}[/]"
        )
    lines.append(f"\n[dim]{len(events)} events. /audit <n> <tool> to filter.[/]")
    app.add_system_message("\n".join(lines))


def _list_themes(app: "OctopusTUI") -> None:
    """Show all available themes."""
    current = app._theme_name
    lines = ["[bold]Available Themes[/]\n"]
    for name in THEMES_KEYS:
        marker = " [green]*[/]" if name == current else ""
        lines.append(f"  {name}{marker}")
    lines.append(f"\n[dim]Use /theme <name> or Ctrl+T to switch.[/]")
    app.add_system_message("\n".join(lines))


def _handle_theme(app: "OctopusTUI", name: str) -> None:
    """Set a specific theme by name."""
    if name in THEMES_KEYS:
        app._theme_name = name
        from octopus.tui.app import C, THEMES
        C.update(THEMES[name])
        app._apply_theme()
        app.add_system_message(f"Theme: [bold]{name}[/]")
    else:
        _list_themes(app)


THEMES_KEYS = [
    "dracula", "monokai", "nord", "gruvbox",
    "catppuccin-mocha", "solarized-dark", "tokyo-night",
    "rose-pine", "github-dark",
]


def _cache_file_before_write(app: "OctopusTUI", tc: Any) -> None:
    """Read file content before write/edit for later diff generation."""
    import json as _json
    try:
        args = _json.loads(tc.arguments) if tc.arguments else {}
    except Exception:
        return
    path = args.get("path") or args.get("file_path", "")
    if not path or tc.name not in ("write_file", "edit_file", "write", "edit"):
        return
    try:
        from pathlib import Path as _Path
        p = _Path(path).expanduser().resolve()
        if p.exists():
            app._file_cache[str(p)] = p.read_text(encoding="utf-8", errors="replace")
    except Exception:
        pass


def _get_diff_content(
    app: "OctopusTUI", tool_data: dict[str, Any]
) -> tuple[str, str, str]:
    """Get old/new content and file path for diff display."""
    tool_name = str(tool_data.get("tool_name", ""))
    if tool_name not in ("write_file", "edit_file", "write", "edit"):
        return "", "", ""

    path = str(tool_data.get("file_path", ""))
    if not path:
        return "", "", ""

    old = app._file_cache.pop(path, "")
    new = ""
    try:
        from pathlib import Path as _Path
        p = _Path(path).expanduser().resolve()
        if p.exists():
            new = p.read_text(encoding="utf-8", errors="replace")
            if len(new) > 5000:
                new = new[:5000] + "\n... [truncated]"
    except Exception:
        pass

    return old, new, path


def _handle_effort(app: "OctopusTUI", args: str) -> None:
    """Handle /effort command — cycle or set reasoning effort."""
    levels = ["low", "medium", "high", "max"]
    current = getattr(app, "_effort", "high")

    if args in levels:
        current = args
    else:
        try:
            idx = levels.index(current)
        except ValueError:
            idx = 2  # default to high
        current = levels[(idx + 1) % len(levels)]

    app.set_effort(current)
    app.add_system_message(f"Reasoning effort: [bold]{current}[/]")


async def _select_model(app: "OctopusTUI", conversation: ConversationContext) -> None:
    """Fetch available models from the configured provider API and let user select.

    For providers with base_url: GET /v1/models
    For litellm-native providers without base_url: use known model list
    """
    import httpx

    config = load_config()
    auth = load_auth()
    provider_name = config.model_provider or ""
    provider = config.provider_config

    models: list[dict[str, str]] = []

    # Try fetching from provider API if base_url is set
    if provider and provider.base_url:
        base_url = provider.base_url.rstrip("/")
        models_url = f"{base_url}/models"

        headers: dict[str, str] = {"Content-Type": "application/json"}
        api_key = auth.openai_api_key
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        app.add_system_message(f"Fetching models from {models_url} ...")
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(models_url, headers=headers)
                resp.raise_for_status()
                data = resp.json()

            raw_list = data.get("data", data) if isinstance(data, dict) else data
            if isinstance(raw_list, list):
                for item in raw_list:
                    if isinstance(item, dict) and "id" in item:
                        models.append({
                            "id": item["id"],
                            "owned_by": item.get("owned_by", ""),
                        })
        except Exception as e:
            app.add_error_message(f"Could not fetch models: {e}")

    # Fallback: known models for major providers
    if not models:
        known: dict[str, list[str]] = {
            "openai": ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "o1", "o1-mini", "o3-mini"],
            "anthropic": ["claude-sonnet-4-20250514", "claude-opus-4-20250514", "claude-haiku-4-5-20251001"],
            "deepseek": ["deepseek-chat", "deepseek-reasoner"],
            "xiaomi_mimo": [
                "mimo-v2.5", "mimo-v2.5-pro", "mimo-v2.5-asr",
                "mimo-v2.5-tts", "mimo-v2.5-tts-voiceclone",
                "mimo-v2.5-tts-voicedesign",
            ],
        }
        fallback = known.get(provider_name, [])
        if fallback:
            models = [{"id": m, "owned_by": provider_name} for m in fallback]

    if not models:
        app.add_system_message(
            "No models found. The provider API at {} did not return a model list. "
            "Set model manually: /config set model <name>".format(
                provider.base_url if provider else "unknown"
            )
        )
        return

    # Sort and display as selectable list
    models.sort(key=lambda m: m["id"])
    current_model = config.model or ""

    lines = [f"[bold]Available Models ({provider_name or 'unknown'}):[/]"]
    for i, m in enumerate(models):
        mid = m["id"]
        marker = " [green]*[/]" if mid == current_model else f"  {i+1}."
        lines.append(f"{marker} {mid}")

    app.add_system_message("\n".join(lines))

    # Cycle to next model on each /model call
    model_ids = [m["id"] for m in models]
    try:
        idx = model_ids.index(current_model) if current_model in model_ids else -1
    except ValueError:
        idx = -1
    selected = model_ids[(idx + 1) % len(model_ids)]

    config.model = selected
    from octopus.config.manager import save_config
    save_config(config)
    conversation.model = selected
    app.update_info(model=selected)
    app.add_system_message(f"[bold green]Model set to:[/] {selected}")
