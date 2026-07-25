# CLAUDE.md — Octopus-Agent Project Requirements

## Project Overview

**Octopus-Agent** is a desktop + CLI dual AI coding & general-purpose agent client, benchmarking Claude Desktop, Claude Code CLI, Codex, and Hermes agent capabilities. Standalone harness-governed intelligent assistant for ordinary users and developers.

**License**: MIT | **Language**: Python + TypeScript | **Entry command**: `octopus`

### Core Differentiator: Harness Governance
All AI outputs, file operations, shell execution, code writing behaviors are intercepted, verified and constrained by the harness layer. Support permission adjustment, safety guard toggle, resource limitation, action rollback and full audit tracking.

### Two Usage Modes (Shared Kernel)
1. **Desktop GUI App** — Tauri + React, for daily users (analogous to Claude Desktop)
2. **CLI Terminal Client** — Typer + Rich + prompt-toolkit, for developers (analogous to Claude Code)

Both share identical core: harness kernel, configuration, conversation records, sandbox environment, agent policies.

---

## Technology Stack

| Layer | Technology | Rationale |
|-------|-----------|-----------|
| **GUI Framework** | Tauri 2.x + React 18 + TypeScript | 25-50MB package, xterm.js terminal, modern UI, native sidecar for Python |
| **CLI Framework** | Typer 0.12+ | Type-annotation-driven, auto-completion, Rich integration |
| **CLI UI** | Rich + prompt-toolkit | Terminal rendering, styled prompts, arrow key selection menus |
| **TUI Fallback** | Textual 0.80+ | Terminal UI for headless/SSH environments |
| **Terminal Embedding** | xterm.js (in Tauri webview) | Industry standard (VS Code, Hyper), full VT100 support |
| **LLM Provider Layer** | litellm + custom abstraction | 100+ providers unified, custom governance hooks on top |
| **Data Models** | Pydantic v2 | Type-safe config, messages, tool inputs, JSON Schema generation |
| **State/Config Sync** | SQLite (WAL mode) + localhost WebSocket | Persistent state + real-time GUI/CLI sync |
| **HTTP Client** | httpx (async) | API calls, web tools, hooks |
| **Build/Packaging** | PyInstaller (Python backend) + Tauri bundler | Cross-platform standalone binaries |
| **Testing** | pytest + pytest-asyncio + ruff + mypy | Async test support, linting, type checking |
| **Python Version** | 3.11+ | Modern async features, match OpenHarness |

---

## Architecture: Layered Design

```
┌─────────────────────────────────────────────────────────┐
│                    Entry: `octopus`                      │
├──────────────────────┬──────────────────────────────────┤
│   CLI Layer (Typer)  │   GUI Layer (Tauri + React)      │
│   - Interactive mode │   - Chat panel                   │
│   - Code commands    │   - Terminal (xterm.js)          │
│   - Session mgmt     │   - Sidebar navigation          │
├──────────────────────┴──────────────────────────────────┤
│              Shared Core: octopus-core                   │
│  ┌─────────┐ ┌──────────┐ ┌───────────┐ ┌───────────┐  │
│  │ Harness │ │  Agent   │ │   Tool    │ │  LLM      │  │
│  │ Kernel  │ │  System  │ │  System   │ │ Providers │  │
│  └─────────┘ └──────────┘ └───────────┘ └───────────┘  │
│  ┌─────────┐ ┌──────────┐ ┌───────────┐ ┌───────────┐  │
│  │Permission│ │  Audit   │ │  Memory   │ │  Sandbox  │  │
│  │ Engine  │ │  Logger  │ │  System   │ │  (Cube)   │  │
│  └─────────┘ └──────────┘ └───────────┘ └───────────┘  │
│  ┌─────────┐ ┌──────────┐ ┌───────────┐ ┌───────────┐  │
│  │  Hook   │ │ Rollback │ │   Auth    │ │  Plugin   │  │
│  │ Manager │ │  Engine  │ │  Store    │ │  System   │  │
│  └─────────┘ └──────────┘ └───────────┘ └───────────┘  │
├─────────────────────────────────────────────────────────┤
│  SQLite (persistent state + audit) + WebSocket (IPC)     │
└─────────────────────────────────────────────────────────┘
```

---

## Project Directory Structure

```
Octopus-Agent/
├── pyproject.toml              # Python build config (hatchling)
├── package.json                # Tauri/React frontend config
├── src-tauri/                  # Tauri Rust shell
│   ├── Cargo.toml
│   ├── tauri.conf.json
│   └── src/
│       └── main.rs             # Tauri entry, sidecar management
├── frontend/                   # React + TypeScript GUI
│   ├── src/
│   │   ├── App.tsx
│   │   ├── components/
│   │   │   ├── Chat/           # Multi-chat session UI
│   │   │   ├── Terminal/       # xterm.js terminal widget
│   │   │   ├── Editor/         # Code editor + diff preview
│   │   │   ├── HarnessPanel/   # Governance control panel
│   │   │   ├── Sidebar/        # File tree, session list
│   │   │   └── Settings/       # Model config, preferences
│   │   ├── hooks/              # React hooks for IPC
│   │   ├── stores/             # State management (Zustand)
│   │   └── lib/                # API clients, utils
│   └── package.json
├── src/
│   └── octopus/
│       ├── __init__.py
│       ├── __main__.py         # `python -m octopus`
│       ├── cli.py              # Typer CLI entry point
│       ├── cli_runtime.py      # Async CLI runtime helpers
│       ├── cli_ui.py           # CLI UI rendering (banner, menus, tool output)
│       ├── core/               # === HARNESS KERNEL ===
│       │   ├── __init__.py
│       │   ├── kernel.py       # Kernel: central orchestrator
│       │   ├── permissions.py  # Permission engine (4 modes)
│       │   ├── audit.py        # Audit logger (all actions tracked)
│       │   ├── sandbox.py      # Filesystem sandbox isolation
│       │   ├── hooks.py        # 4 hook types with hot-reload
│       │   ├── rollback.py     # Task rollback via state checkpoints
│       │   └── state.py        # Global state manager
│       ├── agents/             # === AGENT SYSTEM ===
│       │   ├── __init__.py
│       │   ├── base.py         # BaseAgent protocol + AgentDefinition
│       │   ├── llm_agent.py    # LLM-backed agent
│       │   ├── coordinator.py  # Multi-agent coordinator + WorkerAgent
│       │   └── registry.py     # Agent discovery & registration
│       ├── loop/               # === AGENT LOOP ===
│       │   ├── __init__.py
│       │   ├── engine.py       # Query loop (think-act-observe)
│       │   ├── context.py      # Conversation context management
│       │   ├── compaction.py   # Hybrid compaction strategies
│       │   └── models.py       # Message, StreamEvent, Role
│       ├── tools/              # === TOOL SYSTEM ===
│       │   ├── __init__.py
│       │   ├── base.py         # Tool protocol & registry
│       │   ├── filesystem.py   # Read/write/edit/glob/grep
│       │   ├── shell.py        # Shell command execution (governed)
│       │   ├── search.py       # Web search, code search
│       │   ├── git.py          # Git operations
│       │   ├── diff.py         # Diff generation for GUI preview
│       │   └── mcp.py          # MCP client tool bridge
│       ├── providers/          # === LLM PROVIDERS ===
│       │   ├── __init__.py
│       │   ├── base.py         # Provider protocol
│       │   └── litellm_adapter.py  # litellm unified adapter
│       ├── skills/             # === SKILLS SYSTEM ===
│       │   ├── __init__.py
│       │   ├── schema.py       # SkillDefinition with YAML frontmatter
│       │   ├── loader.py       # Skill discovery & loading
│       │   ├── registry.py     # Skill registry
│       │   └── bundled/        # Built-in skills (review, explain)
│       ├── plugins/            # === PLUGIN SYSTEM ===
│       │   ├── __init__.py
│       │   ├── loader.py       # Plugin discovery & loading
│       │   ├── manager.py      # Plugin lifecycle
│       │   └── schemas.py      # Plugin manifest schema
│       ├── config/             # === CONFIGURATION ===
│       │   ├── __init__.py
│       │   ├── manager.py      # Config manager (auth.json + config.toml)
│       │   ├── schema.py       # Pydantic settings models
│       │   └── loader.py       # Multi-layer config resolution
│       ├── memory/             # === MEMORY SYSTEM ===
│       │   ├── __init__.py
│       │   ├── schema.py       # MemoryEntry model
│       │   └── manager.py      # CRUD + search + relevance
│       ├── auth/               # === CREDENTIAL STORAGE ===
│       │   ├── __init__.py
│       │   └── credentials.py  # Fernet-encrypted store
│       ├── sandbox/            # === SANDBOX BACKENDS ===
│       │   ├── __init__.py
│       │   ├── adapter.py      # SandboxAdapter protocol
│       │   ├── local.py        # Subprocess (no isolation)
│       │   └── cube.py         # CubeSandbox (KVM MicroVM)
│       ├── bridge/             # === GUI-CLI BRIDGE ===
│       │   ├── __init__.py
│       │   ├── server.py       # WebSocket server for GUI IPC
│       │   └── protocol.py     # Message types for IPC
│       └── utils/
│           ├── __init__.py
│           ├── files.py        # Atomic file operations
│           ├── file_cache.py   # LRU file state cache
│           ├── logging.py      # Structured logging
│           └── platform.py     # OS detection, path helpers
├── tests/
│   ├── conftest.py             # Shared fixtures
│   ├── unit/                   # Per-module unit tests
│   ├── integration/            # Subsystem interaction tests
│   └── e2e/                    # Full workflow tests
├── docs/
│   ├── plans/                  # Implementation phase plans
│   │   ├── phase1-mvp-core.md
│   │   ├── phase2-enhanced.md
│   │   ├── phase3-full.md
│   │   ├── phase4-gap-analysis.md
│   │   └── phase5-claude-code-reuse.md
│   ├── architecture.md         # System architecture
│   └── developer.md            # Contributing guide
├── CLAUDE.md                   # This file
├── README.md                   # English documentation
├── README-zh_CN.md             # Chinese documentation
└── LICENSE
```

---

## Harness Governance: Core Feature Specification

### Permission Modes
| Mode | Shell | Write/Read/Delete | Use Case |
|------|-------|-------------------|----------|
| **manual** (default) | Ask approval | Ask approval | Untrusted code, review everything |
| **accept_edits** | Block | Allow | Code review, allow edits but no execution |
| **plan** | Block | Allow | Planning, allow file ops but no execution |
| **auto** | Allow | Allow | Trusted environment, full automation |

Switch modes with `Shift+Tab` during interactive sessions.

### File System Sandbox
- AI can only operate within user-authorized folders
- Cross-directory access blocked by default
- Sensitive paths (SSH keys, AWS creds, .env) always blocked regardless of rules
- Configurable allow/deny glob patterns
- CubeSandbox MicroVM isolation for hardware-level security

### Shell Command Governance
- Safe commands (ls, cat, grep, git) allowed by default
- Dangerous commands (rm -rf, sudo, chmod 777) require manual approval
- Command pattern matching with regex
- Per-project command profiles

### Task Rollback
- PreToolUse hook snapshots file state before each modification
- Diffs stored in SQLite
- One-click rollback to any previous checkpoint
- Git integration for version-aware rollback

### Full Behavior Audit
- Every tool call logged: timestamp, tool, args, result, duration, permission decision
- Searchable audit log in both GUI and CLI
- Export to JSON/CSV
- `octopus code logs` CLI command

---

## Configuration System

### Files (in `~/.octopus/`)

**auth.json** — API keys (sensitive, gitignored):
```json
{
  "OPENAI_API_KEY": "sk-...",
  "ANTHROPIC_API_KEY": "sk-ant-..."
}
```

**config.toml** — Provider settings:
```toml
model_provider = "openai"
model = "gpt-4o"
model_reasoning_effort = "high"

[model_providers.openai]
name = "OpenAI"
base_url = "https://api.openai.com/v1"
wire_api = "chat_completions"
requires_openai_auth = true
```

### In-Session Commands
| Command | Description |
|---------|-------------|
| `/model` | Fetch & select model with arrow keys |
| `/config show` | Show current configuration |
| `/config set model <m>` | Set model name |
| `/config set provider <p>` | Set provider name |
| `/config set base_url <u>` | Set provider base URL |
| `/config set api_key <key>` | Set API key |

---

## CLI Command Reference

```bash
# CLI interactive mode
octopus cli
octopus cli -c <session-id>           # Resume a session
octopus cli --model gpt-4o            # Use specific model
octopus cli --permission-mode auto    # Set permission mode

# Single prompt
octopus cli "Write a Python sorting algorithm"

# Code agent subcommands
octopus code init          # Bind current directory as workspace
octopus code fix           # Auto scan and fix bugs
octopus code test          # Generate & run unit tests
octopus code refactor      # Refactor codebase
octopus code logs          # View audit records

# Session management
octopus session list       # List past sessions
octopus session resume <id> # Resume a session
octopus session new        # Start a new session
```

---

## Response Handling

The agent loop processes model output through multiple stages:

1. **XML tool call parsing** — Handles `<tool_call>` and `<function=name>` formats
2. **Code block detection** — Parses ` ```bash ` blocks as shell commands
3. **Bare command detection** — Recognizes plain shell commands
4. **Artifact stripping** — Removes `<thinking>`, `<tool_result>`, `<|python_tag|>`
5. **Tool name normalization** — Maps variations (terminal, execute_command) to canonical names
6. **Deduplication** — Prevents duplicate tool execution

---

## Testing Strategy

| Level | Scope | Tools | Target |
|-------|-------|-------|--------|
| Unit | Per-module, mock LLM | pytest, pytest-asyncio | >80% coverage |
| Integration | Subsystem interactions | pytest, fixtures | Core workflows |
| E2E | Full CLI/GUI workflows | pytest, Playwright (GUI) | Critical paths |
| Performance | Loop throughput, tool latency | pytest-benchmark | Baselines |

---

## Development Guidelines

1. **No emoji**: The entire project must not use emoji characters. No emoji in source code, comments, docstrings, CLI output, commit messages, or documentation. Use plain ASCII text only.
2. **Async-first**: All agent operations use async/await. Use `asyncio.gather` for parallel tool execution.
3. **Pydantic everywhere**: All config, messages, tool inputs use Pydantic v2 models.
4. **Type hints**: Full type annotations. Run mypy in CI.
5. **Ruff formatting**: Use ruff for linting and formatting (configured in pyproject.toml).
6. **Protocol-based abstractions**: Use Python Protocol for tool, provider, and agent interfaces.
7. **Harness-first**: Every new tool or capability must pass through the kernel's permission + audit pipeline.
8. **Test before merge**: All PRs require passing tests and type checks.

---

## Reference Projects

### OpenHarness (HKUDS)
Reference implementation for harness governance. Key modules adapted:
- `engine/query.py` -> `octopus/loop/engine.py`
- `api/` -> `octopus/providers/`
- `permissions/` -> `octopus/core/permissions.py`
- `hooks/` -> `octopus/core/hooks.py`
- `tools/` -> `octopus/tools/`
- `config/settings.py` -> `octopus/config/schema.py`
- `plugins/` -> `octopus/plugins/`

### claude-code (Anthropic)
Production CLI agent. Patterns adopted:
- Skills system (SKILL.md with YAML frontmatter)
- File state cache (LRU, mtime-based invalidation)
- Budget enforcement (turns, tool calls, tokens)
- Worker agents (background execution)
- Response handling (XML parsing, artifact stripping)
- Retry with exponential backoff

---

## Implementation Plans

Detailed phase plans are in `docs/plans/`:
- [Phase 1: MVP Core](docs/plans/phase1-mvp-core.md) — Weeks 1-4: Harness kernel + CLI
- [Phase 2: Enhanced](docs/plans/phase2-enhanced.md) — Weeks 5-8: Multi-provider + GUI foundation
- [Phase 3: Full](docs/plans/phase3-full.md) — Weeks 9-14: Full GUI, plugins, packaging
- [Phase 4: Gap Analysis](docs/plans/phase4-gap-analysis.md) — Weeks 15-20: OpenHarness parity
- [Phase 5: claude-code Patterns](docs/plans/phase5-claude-code-reuse.md) — Weeks 21-26: Skills, cache, budget, workers
