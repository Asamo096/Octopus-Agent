# Phase 4: Gap Analysis — Octopus-Agent vs OpenHarness

> Generated: 2026-07-25
> Updated: 2026-07-25 (decisions locked)
> Reference: ~/OpenHarness (v0.x) vs ~/Octopus-Agent (v0.1.0)

---

## Executive Summary

Octopus-Agent has a solid **harness kernel + agent loop + tools + CLI** foundation (Phase 1-3). Compared to OpenHarness, there are **15 major capability gaps** across 4 priority tiers. This plan addresses each gap with concrete implementation steps.

### Locked Decisions

| # | Decision | Choice | Rationale |
|---|----------|--------|-----------|
| 1 | Compaction | **Hybrid** (microcompact → context collapse → LLM summary) | Gradual degradation, start simple |
| 2 | Memory storage | **Markdown files** (memdir) | Human-readable, git-friendly |
| 3 | Hook types | **All 4 types** (Python + Command + HTTP + Prompt) | Full parity with OpenHarness |
| 4 | Context persistence | **SQLite only** | Consistent with existing architecture |
| 5 | MCP transport | **Both** stdio + HTTP | Low marginal cost, full compatibility |
| 6 | Multi-agent backend | **In-process only** | Simple, covers most use cases |
| 7 | Sandbox | **CubeSandbox** (Tencent Cloud) | Hardware-isolated MicroVMs, sub-60ms cold start |
| 8 | Credentials | **Encrypted file** (Fernet) | Works everywhere, secure |
| 9 | Provider strategy | **litellm only** | 100+ providers, minimal code |
| 10 | GUI framework | **Tauri + React** | Small package, native perf |

**Current coverage vs OpenHarness:**

| Category | OpenHarness | Octopus | Gap |
|----------|------------|---------|-----|
| Core Engine | ✅ Full | ✅ Full | None |
| Permissions | ✅ Full | ✅ Full | Minor |
| Hooks | ✅ 4 types, hot-reload | ⚠️ Stubs only | **Major** |
| Tools | 40+ tools | 12 tools | **Major** |
| Providers | 22+ native | litellm only | Moderate |
| MCP | ✅ stdio+HTTP | ❌ Missing | **Major** |
| Memory | ✅ memdir system | ❌ Missing | **Major** |
| Compaction | ✅ 5 strategies | ❌ Missing | **Major** |
| Multi-Agent | ✅ Swarm+Coordinator | ❌ Empty module | **Major** |
| Channels | 10 platforms | ❌ None | Moderate |
| Auth | ✅ OAuth+keyring | ❌ Missing | Moderate |
| Sandbox | ✅ Docker | ⚠️ Path-only | **Major** |
| Personalization | ✅ Fact extraction | ❌ Missing | Minor |
| GUI | ✅ Full Tauri+React | ⚠️ Scaffold only | **Major** |
| CLI Commands | ✅ All wired | ⚠️ 8 stubs | Moderate |

---

## Tier 1: Critical Gaps (Core Functionality)

### Gap 1: Conversation Compaction

**OpenHarness has:** 5 compaction strategies — microcompact (clear old tool results), context collapse (shrink oversized blocks), session memory (condense to summary), full LLM compaction (model-generated summary), reactive compaction (triggered on "prompt too long"). Auto-compact triggers at token threshold. Preserves task focus, recent files, verified work across compaction boundaries.

**Octopus has:** Nothing. Long conversations will hit context limits and fail.

**Implementation:**

```
src/octopus/loop/compaction.py
```

- `CompactionStrategy` enum: MICROCOMPACT, CONTEXT_COLLAPSE, SESSION_MEMORY, FULL_LLM
- `CompactionEngine` class:
  - `estimate_tokens(messages)` — rough token count (4 chars ≈ 1 token)
  - `microcompact(messages)` — clear tool result content older than N turns
  - `context_collapse(messages, max_chars)` — truncate oversized text blocks
  - `session_memory_compact(messages, provider)` — LLM-generated summary of older messages
  - `full_compact(messages, provider)` — full conversation summary
  - `auto_compact(messages, threshold_tokens)` — pick strategy based on overflow amount
  - `reactive_compact(messages, error)` — handle "prompt too long" errors
- Wire into `engine.py`: check token count before each API call
- Config: `auto_compact_threshold_tokens` in OctopusSettings

**Effort:** ~400 lines | **Priority:** P0 — blocks real usage

---

### Gap 2: Memory System

**OpenHarness has:** Memdir-based persistent memory with markdown files. Schema with metadata (id, name, description, type, scope, category, importance, source, signature, TTL, tags). Memory scanning, relevance scoring, search. Team memory vault with secret detection. Session memory for cross-turn persistence. Durable memory extraction from turns. Auto-dream background consolidation.

**Octopus has:** Nothing. No cross-session knowledge persistence.

**Implementation:**

```
src/octopus/memory/
├── __init__.py
├── manager.py      # MemoryManager: CRUD, search, relevance scoring
├── schema.py       # MemoryEntry Pydantic model
├── scanner.py      # Scan memory directory, index entries
├── extraction.py   # Extract facts from conversation turns
└── paths.py        # Memory directory resolution (~/.octopus/memory/)
```

- `MemoryEntry`: id, name, description, type (user/feedback/project/reference), content, tags, created_at, updated_at, importance (1-5)
- `MemoryManager`:
  - `store(entry)` — write markdown file with YAML frontmatter
  - `recall(query, limit)` — search by keyword + relevance scoring
  - `list_entries(type_filter)` — list all memory entries
  - `delete(id)` — remove memory entry
  - `extract_from_turn(messages)` — LLM-based fact extraction
- Memory format: markdown files in `~/.octopus/memory/` with YAML frontmatter
- Config: `memory.enabled`, `memory.auto_extract`, `memory.max_entries`

**Effort:** ~500 lines | **Priority:** P0 — core differentiator for persistent assistant

---

### Gap 3: Hook System Upgrade

**OpenHarness has:** 4 hook types (Command, Prompt, HTTP, Agent), 10 hook events, hot-reload on config change, priority ordering, fnmatch pattern matching, shell env injection (`OPENHARNESS_HOOK_EVENT`, `OPENHARNESS_HOOK_PAYLOAD`), aggregated results with blocking.

**Octopus has:** Hook framework exists but all 3 default hooks are no-op stubs. Only supports Python callback hooks, no command/HTTP/prompt hooks.

**Implementation:**

```
src/octopus/core/hooks.py — upgrade existing
```

- Add `HookType` enum: PYTHON, COMMAND, HTTP, PROMPT
- Add `HookDefinition` dataclass: name, type, event, priority, config (type-specific)
- `CommandHookConfig`: command template, timeout, block_on_failure
- `HttpHookConfig`: url, headers, timeout
- `PromptHookConfig`: prompt template, model, timeout
- `HookLoader`: load hooks from config file (`~/.octopus/hooks.json`)
- Hot-reload: watch config file mtime, reload on change
- Wire real default hooks:
  - `permission_check_hook` — delegate to PermissionEngine
  - `audit_log_hook` — delegate to AuditLogger
  - `rollback_checkpoint_hook` — delegate to RollbackEngine
- Config: `hooks` section in settings.yaml

**Effort:** ~350 lines | **Priority:** P0 — hooks are the governance backbone

---

### Gap 4: Conversation Context Management

**OpenHarness has:** `QueryContext` dataclass owning all loop state. `QueryEngine` with message history management, model/system_prompt/effort switching, message loading from disk, pending continuation tracking, sanitize/normalize functions.

**Octopus has:** Context is a minimal dataclass in kernel.py. No message history persistence, no context management, no message sanitization.

**Implementation:**

```
src/octopus/loop/context.py
```

- `ConversationContext` class:
  - `messages: list[Message]` — full conversation history
  - `system_prompt: str` — configurable system prompt
  - `model: str`, `max_tokens: int`, `effort: str`
  - `add_message(msg)`, `get_messages()`, `clear()`
  - `save(session_id)` — persist to SQLite via StateManager
  - `load(session_id)` — restore from SQLite
  - `sanitize()` — normalize restored history, drop empty messages, trim orphan tool_use
  - `estimate_tokens()` — rough token count for compaction decisions
  - `to_provider_format()` — convert to provider-specific message format
- Wire into engine.py: engine owns a ConversationContext instance
- Session resume: `octopus session resume <id>` loads context from DB

**Effort:** ~300 lines | **Priority:** P0 — required for session persistence

---

## Tier 2: Important Gaps (Feature Completeness)

### Gap 5: MCP Client Bridge

**OpenHarness has:** Full MCP client with stdio + HTTP transports, tool listing, resource listing, connection status, reconnection, plugin-contributed MCP configs.

**Octopus has:** `tools/mcp.py` file doesn't exist. No MCP support at all.

**Implementation:**

```
src/octopus/tools/mcp.py
```

- `MCPClient` class:
  - `connect_stdio(command, args)` — spawn MCP server process
  - `connect_http(url)` — connect to HTTP MCP server
  - `list_tools()` — discover available tools
  - `call_tool(name, arguments)` — invoke MCP tool
  - `list_resources()` — list available resources
  - `read_resource(uri)` — read resource content
  - `disconnect()` — cleanup connections
- `MCPToolAdapter`: wraps MCP tool as Octopus Tool for registry
- Config: `mcp_servers` section in settings.yaml
- Depends on: `mcp` Python package (add to pyproject.toml)

**Effort:** ~400 lines | **Priority:** P1 — enables ecosystem tool access

---

### Gap 6: Multi-Agent System

**OpenHarness has:** Full swarm system — team lifecycle, subprocess/in-process/tmux/iTerm2 backends, mailbox messaging, git worktree isolation, permission sync, lockfile coordination. Coordinator mode with 7 built-in agent definitions, XML task notification, worker context injection.

**Octopus has:** `agents/` module is completely empty. No multi-agent capability.

**Implementation:**

```
src/octopus/agents/
├── __init__.py
├── base.py         # BaseAgent protocol
├── llm_agent.py    # LLM-backed agent with own loop
├── coordinator.py  # Multi-agent orchestrator
├── registry.py     # Agent discovery & registration
└── definitions/    # Built-in agent definitions
    ├── general.md
    ├── explorer.md
    ├── planner.md
    └── reviewer.md
```

- `BaseAgent` protocol: name, description, run(task) -> result
- `LLMAgent`: wraps agent loop for autonomous execution
- `Coordinator`:
  - `spawn(agent_def, task)` — create sub-agent
  - `send_message(agent_id, message)` — inter-agent communication
  - `wait(agent_id)` — await completion
  - `list_agents()` — list active agents
- `AgentRegistry`: discover agent definitions from `.octopus/agents/` and plugins
- Agent definition format: markdown with YAML frontmatter (name, model, tools, permissions)
- Tools: `agent` (spawn), `send_message` (communicate)
- Config: `agents` section in settings.yaml

**Effort:** ~600 lines | **Priority:** P1 — core differentiator

---

### Gap 7: CubeSandbox Integration

**OpenHarness has:** Docker-based sandbox with adapter pattern, Docker backend, Docker image builder, path validator, session management. Full process isolation.

**Octopus has:** Path validation only. No process isolation.

**Decision:** Use [CubeSandbox](https://github.com/TencentCloud/CubeSandbox) instead of Docker. CubeSandbox provides hardware-isolated MicroVMs (KVM) with sub-60ms cold start, <5MB memory overhead, and thousands of sandboxes per node. It is E2B SDK compatible and provides stronger isolation than Docker (dedicated kernel per sandbox vs shared kernel namespaces).

**CubeSandbox Python SDK API:**

```python
from cubesandbox import Sandbox, Config

# Create sandbox (context manager auto-kills on exit)
with Sandbox.create(template="tpl-xxx") as sb:
    # Execute code
    result = sb.run_code("1 + 1")
    print(result.text)  # "2"
    print(result.logs.stdout)

    # Shell commands
    cmd = sb.commands.run("ls -la", cwd="/workspace")

    # Filesystem operations
    content = sb.files.read("/workspace/main.py")
    sb.files.write("/workspace/main.py", "print('hello')")
    sb.files.list("/workspace")
    sb.files.exists("/workspace/main.py")

    # Snapshots for rollback
    snap = sb.create_snapshot("before-edit")
    sb.rollback(snap.snapshot_id)
```

**Implementation:**

```
src/octopus/sandbox/
├── __init__.py
├── adapter.py      # SandboxAdapter protocol
├── cube.py         # CubeSandbox backend
└── local.py        # Local backend (current behavior)
```

- `SandboxAdapter` protocol:
  - `create(workspace, template) -> session_id`
  - `execute_command(command, cwd, timeout) -> SandboxResult`
  - `read_file(path) -> str`
  - `write_file(path, content) -> None`
  - `create_snapshot(name) -> snapshot_id`
  - `restore_snapshot(snapshot_id) -> None`
  - `destroy() -> None`
- `CubeBackend` (implements SandboxAdapter):
  - Wraps `cubesandbox.Sandbox` lifecycle
  - `create()` — `Sandbox.create(template=config.template_id, volume_mounts={"/workspace": workspace})`
  - `execute_command()` — `sb.commands.run(cmd, cwd=cwd, timeout=timeout)`
  - `read_file()` / `write_file()` — `sb.files.read()` / `sb.files.write()`
  - `create_snapshot()` — `sb.create_snapshot(name)`
  - `restore_snapshot()` — `sb.rollback(snapshot_id)`
  - `destroy()` — `sb.kill()`
  - Auto-pause on idle (configurable timeout)
  - Network isolation via `allow_internet_access` flag
- `LocalBackend`: current subprocess behavior (no isolation, fallback when CubeSandbox unavailable)
- Wire into kernel's `_sandbox_check()`: if sandbox enabled, route tool execution through CubeSandbox
- Config:
  - `sandbox.backend` (local/cube)
  - `sandbox.cube_api_url` (default: `http://127.0.0.1:3000`)
  - `sandbox.cube_template_id` (required for cube backend)
  - `sandbox.cube_api_key` (optional)
  - `sandbox.auto_pause_timeout` (seconds, default 300)
  - `sandbox.allow_internet` (default true)
- Dependencies: `cubesandbox` package (add to pyproject.toml)
- Env vars: `CUBE_API_URL`, `CUBE_TEMPLATE_ID`, `CUBE_API_KEY` (override config)

**Effort:** ~400 lines | **Priority:** P1 — safety critical

---

### Gap 8: Authentication System

**OpenHarness has:** File-based credential storage (POSIX 600), optional system keyring, external auth bindings for OAuth, AuthManager for provider auth state, Claude/Codex/Copilot OAuth flows.

**Octopus has:** API keys stored in plain config. No credential management.

**Implementation:**

```
src/octopus/auth/
├── __init__.py
├── credentials.py  # CredentialStore: file-based with encryption
├── manager.py      # AuthManager: provider auth state
└── flows.py        # OAuth flows for Claude, OpenAI, etc.
```

- `CredentialStore`:
  - `store(key, value)` — encrypt and save to `~/.octopus/credentials.enc`
  - `retrieve(key)` — decrypt and return
  - `delete(key)` — remove credential
  - File permissions: 0o600
  - Encryption: Fernet (cryptography package) with machine-derived key
- `AuthManager`:
  - `get_provider_auth(provider_name)` — resolve auth for provider
  - `authenticate(provider, flow)` — run OAuth flow
- OAuth flows for Claude API, OpenAI, GitHub Copilot
- Config: `auth.storage` (file/keyring)

**Effort:** ~400 lines | **Priority:** P1 — security requirement

---

### Gap 9: CLI Stub Commands

**OpenHarness has:** All CLI commands fully wired to backend.

**Octopus has:** 8 CLI commands are stubs printing "Phase 2" placeholder:
- `provider list/use/add`
- `permissions add/remove`
- `session resume/new`
- `code fix/test/refactor`

**Implementation:**

Wire each stub to existing backend:

```python
# provider list — iterate OctopusSettings.profiles
# provider use — update default_provider in settings
# provider add — add ProviderProfile to settings, save

# permissions add — PermissionEngine.add_allowed_path() + save config
# permissions remove — remove from config + save

# session resume — StateManager.get_session() + load ConversationContext
# session new — StateManager.create_session() + fresh context

# code fix — agent loop with "scan and fix bugs" system prompt
# code test — agent loop with "generate unit tests" system prompt
# code refactor — agent loop with "refactor codebase" system prompt
```

**Effort:** ~300 lines | **Priority:** P1 — user-facing completeness

---

## Tier 3: Enhancement Gaps (Polish & Ecosystem)

### Gap 10: Provider Native Adapters

**OpenHarness has:** 22+ native provider implementations with auto-detection by API key prefix, base URL, model name. Exponential backoff retry, Retry-After header support.

**Octopus has:** Single litellm adapter. All providers go through litellm.

**Implementation:**

```
src/octopus/providers/
├── anthropic.py    # Direct Anthropic SDK (Claude-specific features)
├── openai.py       # Direct OpenAI SDK
└── local.py        # Ollama / llama.cpp / local models
```

- `AnthropicProvider`: AsyncAnthropic with retry, Claude OAuth, model-specific headers
- `OpenAIProvider`: AsyncOpenAI with retry, compatible with all OpenAI-format APIs
- `LocalProvider`: httpx client for Ollama API, model listing
- Provider registry: auto-detect provider from api_key prefix or base_url
- Config: provider profiles with auto-detection hints

**Effort:** ~500 lines | **Priority:** P2 — litellm covers basics, native adds reliability

---

### Gap 11: Additional Tools

**OpenHarness has 40+ tools. Octopus has 12.** Key missing tools:

| Tool | Description | Priority |
|------|------------|----------|
| `web_fetch` | Fetch URL content (HTML/text) | P1 |
| `notebook_edit` | Edit Jupyter notebooks | P2 |
| `lsp` | Language Server Protocol operations | P2 |
| `ask_user` | Ask user a clarifying question | P1 |
| `agent` | Spawn sub-agent | P1 (with Gap 6) |
| `send_message` | Message running agent | P1 (with Gap 6) |
| `skill` | Load and execute a skill | P2 |
| `todo_write` | Write todo/task items | P2 |
| `image_to_text` | Describe images via vision model | P2 |
| `enter_plan_mode` | Switch to plan mode | P1 |
| `exit_plan_mode` | Exit plan mode | P1 |

**Implementation:** Each tool follows existing pattern in `tools/base.py`. ~50-100 lines each.

**Effort:** ~800 lines total | **Priority:** P1-P2 mix

---

### Gap 12: Skills System

**OpenHarness has:** Skill loading from bundled/user/project directories, registry, SKILL.md format.

**Octopus has:** Nothing.

**Implementation:**

```
src/octopus/skills/
├── __init__.py
├── loader.py       # Discover and load SKILL.md files
├── registry.py     # Skill registry
└── schemas.py      # Skill definition schema
```

- Skill format: `SKILL.md` with YAML frontmatter (name, description, tools, model)
- Discovery: `~/.octopus/skills/`, `<workspace>/.octopus/skills/`, bundled
- `SkillLoader`: parse markdown, extract instructions, register
- `skill` tool: load skill by name, inject instructions into context

**Effort:** ~300 lines | **Priority:** P2

---

### Gap 13: GUI Completion

**OpenHarness has:** Full Tauri+React terminal UI, autopilot dashboard.

**Octopus has:** Scaffold only — ChatPanel (basic), Sidebar (minimal), Terminal (placeholder). Missing: Editor, HarnessPanel, Settings, stores, hooks, streaming, PTY connection.

**Implementation:**

```
frontend/src/
├── components/
│   ├── Editor/         # Monaco editor + diff preview
│   ├── HarnessPanel/   # Permission/audit/rollback controls
│   ├── Settings/       # Model config, provider management
│   └── Chat/           # Upgrade: streaming, tool call rendering
├── stores/
│   ├── chat.ts         # Zustand chat state
│   ├── config.ts       # Settings state
│   └── harness.ts     # Harness state (permissions, audit)
├── hooks/
│   ├── useIPC.ts       # WebSocket IPC hook
│   └── useStream.ts    # Streaming response hook
└── lib/
    ├── ipc.ts          # IPC client
    └── api.ts          # API helpers
```

- Wire Tauri commands to Python sidecar via stdio IPC
- WebSocket streaming for real-time chat
- xterm.js PTY connection to Python shell
- Zustand stores for state management
- Monaco editor for code viewing/editing with diff preview

**Effort:** ~2000 lines (TypeScript) | **Priority:** P2 — CLI works, GUI is enhancement

---

### Gap 14: Textual TUI Fallback

**OpenHarness has:** Full Textual TUI app for headless/SSH environments.

**Octopus has:** Nothing. Only Rich output in CLI.

**Implementation:**

```
src/octopus/tui/
├── __init__.py
├── app.py          # Textual app with chat, sidebar, status
├── screens.py      # Screen definitions
└── widgets.py      # Custom widgets
```

- Textual app with chat panel, tool output panel, status bar
- Keyboard shortcuts for common actions
- Fallback when no GUI available (SSH, headless)

**Effort:** ~500 lines | **Priority:** P3

---

### Gap 15: Utilities & Infrastructure

**OpenHarness has:** File locking, atomic writes, shell helpers, network guard, platform detection.

**Octopus has:** Empty `utils/` module.

**Implementation:**

```
src/octopus/utils/
├── __init__.py
├── files.py        # Atomic file writes, file locking
├── logging.py      # Structured logging with JSON output
├── platform.py     # OS detection, path helpers
└── network.py      # Network access guard
```

- `atomic_write(path, content)` — write to temp file, rename
- `file_lock(path)` — exclusive file locking
- `setup_logging(level, json_format)` — structured logging
- `get_platform()` — OS detection with capabilities

**Effort:** ~200 lines | **Priority:** P3

---

## Implementation Roadmap

### Phase 4A: Core Gaps (Weeks 15-16)
**Goal:** Make Octopus-Agent production-ready for real usage

| Week | Tasks | Effort |
|------|-------|--------|
| 15 | Gap 1 (Compaction) + Gap 4 (Context Management) | ~700 lines |
| 16 | Gap 3 (Hook Upgrade) + Gap 9 (CLI Stubs) | ~650 lines |

**Deliverable:** Long conversations work, sessions persist, hooks enforce governance, all CLI commands functional.

### Phase 4B: Feature Gaps (Weeks 17-18)
**Goal:** Match OpenHarness core feature set

| Week | Tasks | Effort |
|------|-------|--------|
| 17 | Gap 2 (Memory) + Gap 5 (MCP) | ~900 lines |
| 18 | Gap 6 (Multi-Agent) + Gap 8 (Auth) | ~1000 lines |

**Deliverable:** Persistent memory, MCP tools, multi-agent coordination, secure credentials.

### Phase 4C: Infrastructure Gaps (Weeks 19-20)
**Goal:** Production hardening

| Week | Tasks | Effort |
|------|-------|--------|
| 19 | Gap 7 (Docker Sandbox) + Gap 11 (Additional Tools) | ~1300 lines |
| 20 | Gap 10 (Native Providers) + Gap 15 (Utilities) | ~700 lines |

**Deliverable:** Process-isolated execution, full tool suite, reliable providers.

### Phase 4D: Polish (Weeks 21-24)
**Goal:** UX and ecosystem

| Week | Tasks | Effort |
|------|-------|--------|
| 21-22 | Gap 13 (GUI Completion) | ~2000 lines |
| 23 | Gap 12 (Skills) + Gap 14 (TUI) | ~800 lines |
| 24 | Integration testing, documentation, packaging | ~500 lines |

**Deliverable:** Full GUI, skills system, TUI fallback, cross-platform packages.

---

## Effort Summary

| Tier | Gaps | Total Effort | Weeks |
|------|------|-------------|-------|
| Tier 1: Critical | 4 gaps | ~1,550 lines | 2 weeks |
| Tier 2: Important | 5 gaps | ~2,600 lines | 4 weeks |
| Tier 3: Enhancement | 6 gaps | ~4,300 lines | 4 weeks |
| **Total** | **15 gaps** | **~8,450 lines** | **10 weeks** |

---

## Dependencies Between Gaps

```
Gap 4 (Context) ──→ Gap 1 (Compaction) ──→ Gap 2 (Memory)
     │
     └──→ Gap 9 (CLI Stubs: session resume)

Gap 6 (Multi-Agent) ──→ Gap 11 (agent/send_message tools)

Gap 3 (Hooks) ──→ Gap 7 (Docker Sandbox: hook into execution)

Gap 8 (Auth) ──→ Gap 10 (Native Providers: credential resolution)
```

**Recommended order:** 4 → 1 → 3 → 9 → 2 → 5 → 6 → 8 → 7 → 11 → 10 → 12 → 13 → 14 → 15

---

## Success Criteria

After Phase 4, Octopus-Agent should:

1. ✅ Handle conversations of any length (auto-compaction)
2. ✅ Remember facts across sessions (memory system)
3. ✅ Enforce governance via real hooks (not stubs)
4. ✅ Persist and resume sessions (context management)
5. ✅ Connect to MCP servers for ecosystem tools
6. ✅ Coordinate multiple agents for complex tasks
7. ✅ Securely store credentials (encrypted, not plaintext)
8. ✅ Run untrusted code in Docker containers
9. ✅ All CLI commands functional (no stubs)
10. ✅ Full GUI with streaming, editor, harness panel
