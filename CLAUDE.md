# CLAUDE.md — Octopus-Agent Project Requirements

## Project Overview

**Octopus-Agent** is a desktop + CLI dual AI coding & general-purpose agent client, benchmarking Claude Desktop, Claude Code CLI, Codex, and Hermes agent capabilities. Standalone harness-governed intelligent assistant for ordinary users and developers.

**License**: MIT | **Language**: Python + TypeScript | **Entry command**: `octopus`

### Core Differentiator: Harness Governance
All AI outputs, file operations, shell execution, code writing behaviors are intercepted, verified and constrained by the harness layer. Support permission adjustment, safety guard toggle, resource limitation, action rollback and full audit tracking.

### Two Usage Modes (Shared Kernel)
1. **Desktop GUI App** — Tauri + React, for daily users (analogous to Claude Desktop)
2. **CLI Terminal Client** — Typer + Textual, for developers (analogous to Claude Code)

Both share identical core: harness kernel, configuration, conversation records, sandbox environment, agent policies.

---

## Technology Stack

| Layer | Technology | Rationale |
|-------|-----------|-----------|
| **GUI Framework** | Tauri 2.x + React 18 + TypeScript | 25-50MB package, xterm.js terminal, modern UI, native sidecar for Python |
| **CLI Framework** | Typer 0.12+ | Type-annotation-driven, auto-completion, Rich integration |
| **TUI Fallback** | Textual 0.80+ | Terminal UI for headless/SSH environments |
| **Terminal Embedding** | xterm.js (in Tauri webview) | Industry standard (VS Code, Hyper), full VT100 support |
| **LLM Provider Layer** | litellm + custom abstraction | 100+ providers unified, custom governance hooks on top |
| **Data Models** | Pydantic v2 | Type-safe config, messages, tool inputs, JSON Schema generation |
| **State/Config Sync** | SQLite (WAL mode) + localhost WebSocket | Persistent state + real-time GUI/CLI sync |
| **HTTP Client** | httpx (async) | API calls, web tools, hooks |
| **CLI UI** | Rich + prompt-toolkit | Terminal rendering, interactive prompts |
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
│   octopus-cli        │   octopus-gui                    │
│   - Textual TUI      │   - React frontend               │
│   - Rich rendering    │   - xterm.js terminal            │
│   - Interactive mode  │   - Code editor + diff preview   │
│   - Code subcommands  │   - Harness control panel        │
├──────────────────────┴──────────────────────────────────┤
│              Shared Core: octopus-core                   │
│  ┌─────────┐ ┌──────────┐ ┌───────────┐ ┌───────────┐  │
│  │ Harness │ │  Agent   │ │   Tool    │ │  LLM      │  │
│  │ Kernel  │ │  System  │ │  System   │ │ Providers │  │
│  └─────────┘ └──────────┘ └───────────┘ └───────────┘  │
│  ┌─────────┐ ┌──────────┐ ┌───────────┐ ┌───────────┐  │
│  │Permission│ │  Audit   │ │  Plugin   │ │  Config   │  │
│  │ Engine  │ │  Logger  │ │  System   │ │  Manager  │  │
│  └─────────┘ └──────────┘ └───────────┘ └───────────┘  │
├─────────────────────────────────────────────────────────┤
│              IPC Layer: octopus-bridge                   │
│  SQLite (persistent) + WebSocket (real-time sync)        │
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
│       ├── core/               # === HARNESS KERNEL ===
│       │   ├── __init__.py
│       │   ├── kernel.py       # Kernel: central orchestrator
│       │   ├── permissions.py  # Permission engine (path rules, command rules)
│       │   ├── audit.py        # Audit logger (all actions tracked)
│       │   ├── sandbox.py      # Filesystem sandbox isolation
│       │   ├── hooks.py        # PreToolUse/PostToolUse lifecycle
│       │   ├── rollback.py     # Task rollback via state checkpoints
│       │   └── state.py        # Global state manager
│       ├── agents/             # === AGENT SYSTEM ===
│       │   ├── __init__.py
│       │   ├── base.py         # BaseAgent protocol
│       │   ├── llm_agent.py    # LLM-backed agent
│       │   ├── coordinator.py  # Multi-agent coordinator
│       │   └── registry.py     # Agent discovery & registration
│       ├── loop/               # === AGENT LOOP ===
│       │   ├── __init__.py
│       │   ├── engine.py       # Query loop (think-act-observe)
│       │   ├── context.py      # Conversation context management
│       │   ├── scheduler.py    # Priority task scheduler
│       │   └── compaction.py   # Auto-compact when context too long
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
│       │   ├── litellm_adapter.py  # litellm unified adapter
│       │   ├── anthropic.py    # Claude-specific features
│       │   ├── openai.py       # OpenAI-compatible
│       │   └── local.py        # Ollama / local models
│       ├── plugins/            # === PLUGIN SYSTEM ===
│       │   ├── __init__.py
│       │   ├── loader.py       # Plugin discovery & loading
│       │   ├── manager.py      # Plugin lifecycle
│       │   └── schemas.py      # Plugin manifest schema
│       ├── config/             # === CONFIGURATION ===
│       │   ├── __init__.py
│       │   ├── schema.py       # Pydantic settings models
│       │   ├── loader.py       # Multi-layer config resolution
│       │   └── sync.py         # SQLite + WebSocket state sync
│       ├── bridge/             # === GUI-CLI BRIDGE ===
│       │   ├── __init__.py
│       │   ├── server.py       # WebSocket server for GUI IPC
│       │   ├── client.py       # WebSocket client for CLI
│       │   └── protocol.py     # Message types for IPC
│       └── utils/
│           ├── __init__.py
│           ├── files.py        # Atomic file operations
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
│   │   └── phase3-full.md
│   ├── architecture.md         # System architecture
│   ├── api/                    # Auto-generated API docs
│   ├── user-guide.md           # User documentation
│   └── developer.md            # Contributing guide
├── scripts/
│   ├── build.py                # Build automation
│   ├── package.py              # Cross-platform packaging
│   └── release.py              # Release automation
├── vendor/
│   └── openharness/            # Vendored OpenHarness modules (with attribution)
├── CLAUDE.md                   # This file
├── README.md
└── LICENSE
```

---

## Harness Governance: Core Feature Specification

### File System Sandbox
- AI can only operate within user-authorized folders
- Cross-directory access blocked by default
- Sensitive paths (SSH keys, AWS creds, .env) always blocked regardless of rules
- Configurable allow/deny glob patterns

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

## CLI Command Reference

```bash
# Launch GUI (default)
octopus

# CLI interactive mode
octopus cli
octopus cli "Write a Python sorting algorithm"

# Code agent subcommands
octopus code init          # Bind current directory as workspace
octopus code fix           # Auto scan and fix bugs
octopus code test          # Generate & run unit tests
octopus code refactor      # Refactor codebase
octopus code logs          # View audit records

# Harness governance
octopus config show        # Show current config
octopus config set <key> <value>  # Update config
octopus permissions list   # Show permission rules
octopus permissions add <pattern>  # Add rule

# Provider management
octopus provider list      # List configured providers
octopus provider use <name> # Switch default provider

# Session management
octopus session list       # List past sessions
octopus session resume <id> # Resume a session
```

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

1. **Async-first**: All agent operations use async/await. Use `asyncio.gather` for parallel tool execution.
2. **Pydantic everywhere**: All config, messages, tool inputs use Pydantic v2 models.
3. **Type hints**: Full type annotations. Run mypy in CI.
4. **Ruff formatting**: Use ruff for linting and formatting (configured in pyproject.toml).
5. **Protocol-based abstractions**: Use Python Protocol for tool, provider, and agent interfaces.
6. **Harness-first**: Every new tool or capability must pass through the kernel's permission + audit pipeline.
7. **Test before merge**: All PRs require passing tests and type checks.

---

## Reference: OpenHarness

OpenHarness (HKUDS) is the reference implementation. Key modules vendored:
- `engine/query.py` → `octopus/loop/engine.py`
- `api/` → `octopus/providers/`
- `permissions/` → `octopus/core/permissions.py`
- `hooks/` → `octopus/core/hooks.py`
- `tools/` → `octopus/tools/`
- `config/settings.py` → `octopus/config/schema.py`
- `plugins/` → `octopus/plugins/`

**Attribution**: OpenHarness credited in LICENSE and docs. Vendored modules retain original copyright headers.

---

## Implementation Plans

Detailed phase plans are in `docs/plans/`:
- [Phase 1: MVP Core](docs/plans/phase1-mvp-core.md) — Weeks 1-4: Harness kernel + CLI
- [Phase 2: Enhanced](docs/plans/phase2-enhanced.md) — Weeks 5-8: Multi-provider + GUI foundation
- [Phase 3: Full](docs/plans/phase3-full.md) — Weeks 9-14: Full GUI, plugins, packaging
