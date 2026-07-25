# 🐙 Octopus Agent

Desktop + CLI dual AI coding & general-purpose agent client with **harness governance**.

Benchmarks Claude Desktop, Claude Code CLI, Codex, and Hermes agent capabilities. A standalone harness-governed intelligent assistant for ordinary users and developers.

## Core Differentiator: Harness Governance

All AI outputs, file operations, shell execution, and code writing behaviors are **intercepted, verified, and constrained** by the harness layer:

- **Permission Engine** — configurable allow/deny rules for paths and commands
- **Filesystem Sandbox** — AI can only operate within authorized directories (CubeSandbox MicroVM or local)
- **Shell Command Governance** — safe commands allowed, dangerous ones require approval
- **Full Behavior Audit** — every action logged to SQLite for review
- **Task Rollback** — one-click restore to any previous file state
- **Hook System** — 4 hook types (Python, Command, HTTP, Prompt) with hot-reload
- **Credential Management** — encrypted storage with machine-derived keys

## Quick Start

```bash
# Install from source
git clone https://github.com/Asamo096/Octopus-Agent.git
cd Octopus-Agent
uv sync                    # or: python -m venv .venv && pip install -e ".[dev]"

# Set API key
export ANTHROPIC_API_KEY=sk-ant-...

# Show help
octopus --help

# Enter interactive CLI mode
octopus cli

# Run a single prompt
octopus cli "Write a Python sorting algorithm"

# Code agent subcommands
octopus code init           # Initialize workspace
octopus code fix            # Scan and fix bugs
octopus code test           # Generate unit tests
octopus code refactor       # Refactor codebase
octopus code logs           # View audit logs

# Session management
octopus session list        # List past sessions
octopus session resume <id> # Resume a session

# Configuration
octopus config show
octopus config set permissions.mode full_auto

# Provider management
octopus provider list
octopus provider use openai
octopus provider add deepseek --api-key sk-... --base-url https://api.deepseek.com

# Permissions
octopus permissions list
octopus permissions add /data/projects --type path
octopus permissions add docker --type command
```

## Architecture

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

## Features

### Agent Loop
- Think-act-observe cycle with parallel tool execution
- Auto-compaction: microcompact, context collapse, reactive compaction
- Session persistence: resume conversations across restarts
- Max turns enforcement with configurable limits

### Multi-Agent System
- In-process agent coordinator with parallel/sequential execution
- Built-in agent definitions: general, explorer, reviewer, planner
- Agent registry with user/project/built-in discovery
- Agent definitions from markdown with YAML frontmatter

### Memory System
- Persistent cross-session memory stored as markdown files
- Relevance scoring with TF-based search and importance/recency boosts
- Memory types: user, feedback, project, reference
- Store, recall, list, delete operations

### Hook System (4 Types)
- **Python** — async callback hooks
- **Command** — shell execution with `$ARGUMENTS` and env injection
- **HTTP** — webhook POST to external services
- **Prompt** — LLM-based validation
- Hot-reload on config file change
- Default hooks: permission check, rollback checkpoint, audit log

### Sandbox Isolation
- **CubeSandbox** — hardware-isolated KVM MicroVMs (sub-60ms cold start)
- **Local** — subprocess fallback when CubeSandbox unavailable
- File read/write, command execution, snapshots, rollback
- Config: `CUBE_API_URL`, `CUBE_TEMPLATE_ID`, `CUBE_API_KEY`

### Tools (14)
| Tool | Description |
|------|-------------|
| `read_file` | Read file contents with offset/limit |
| `write_file` | Write file with parent directory creation |
| `edit_file` | String-based find/replace editing |
| `glob` | File pattern matching |
| `grep` | Regex content search across files |
| `shell` | Shell command execution (governed) |
| `git` | Git operations (status, diff, log, commit, etc.) |
| `diff` | Unified diff generation |
| `git_diff` | Git diff for staged/unstaged changes |
| `web_search` | Web search via DuckDuckGo |
| `web_fetch` | Fetch URL content |
| `code_search` | Regex search in workspace |
| `mcp` | MCP server tool bridge |
| `agent` | Spawn sub-agent (via coordinator) |

### Configuration
- Multi-layer resolution: CLI args > env vars > user config > project config > defaults
- YAML-based configuration with Pydantic validation
- Environment variables: `OCTOPUS_API_KEY`, `OCTOPUS_MODEL`, `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`

## Tech Stack

| Layer | Technology |
|-------|-----------|
| GUI | Tauri 2.x + React + TypeScript |
| CLI | Typer + Rich |
| LLM | litellm (100+ providers) |
| Data | Pydantic v2 + SQLite (aiosqlite) |
| Sandbox | CubeSandbox (KVM MicroVM) |
| Memory | Markdown files with YAML frontmatter |
| Auth | Fernet encryption (cryptography) |
| Testing | pytest + pytest-asyncio |
| Linting | ruff + mypy |

## Project Structure

```
src/octopus/
├── core/           # Harness kernel
│   ├── kernel.py       # Central orchestrator (5-step pipeline)
│   ├── permissions.py  # Permission engine (3 modes)
│   ├── audit.py        # Async audit logger (SQLite)
│   ├── sandbox.py      # Path/command validation
│   ├── hooks.py        # 4 hook types with hot-reload
│   ├── rollback.py     # File state checkpoints
│   └── state.py        # Session + KV store (SQLite)
├── agents/         # Multi-agent system
│   ├── base.py         # AgentDefinition + BaseAgent protocol
│   ├── llm_agent.py    # LLM-backed autonomous agent
│   ├── coordinator.py  # Multi-agent orchestrator
│   └── registry.py     # Agent discovery (built-in/user/project)
├── loop/           # Agent loop
│   ├── engine.py       # Think-act-observe cycle
│   ├── context.py      # ConversationContext (persistence)
│   ├── compaction.py   # Hybrid compaction strategies
│   └── models.py       # Message, StreamEvent, Role
├── tools/          # Tool system (14 tools)
│   ├── base.py         # Tool protocol + registry
│   ├── filesystem.py   # read/write/edit/glob/grep
│   ├── shell.py        # Shell execution (governed)
│   ├── git.py          # Git operations
│   ├── diff.py         # Diff generation
│   ├── search.py       # Web search + web fetch + code search
│   └── mcp.py          # MCP client bridge
├── providers/      # LLM providers
│   ├── base.py         # Provider protocol
│   └── litellm_adapter.py  # litellm unified adapter
├── config/         # Configuration
│   ├── schema.py       # Pydantic settings models
│   └── loader.py       # Multi-layer config resolution
├── memory/         # Persistent memory
│   ├── schema.py       # MemoryEntry model
│   └── manager.py      # CRUD + search + relevance
├── auth/           # Credential storage
│   └── credentials.py  # Fernet-encrypted store
├── sandbox/        # Sandbox backends
│   ├── adapter.py      # SandboxAdapter protocol
│   ├── local.py        # Subprocess (no isolation)
│   └── cube.py         # CubeSandbox (KVM MicroVM)
├── plugins/        # Plugin system
│   ├── schemas.py      # PluginManifest
│   ├── loader.py       # Discovery + loading
│   └── manager.py      # Lifecycle management
├── bridge/         # GUI-CLI IPC
│   ├── server.py       # WebSocket server
│   └── protocol.py     # IPC message types
├── utils/          # Utilities
│   ├── files.py        # Atomic write, file lock
│   └── platform.py     # OS detection, capabilities
├── cli.py          # Typer CLI entry point
├── cli_runtime.py  # Async CLI runtime helpers
└── __main__.py     # python -m octopus
```

## Development

```bash
# Run tests (319 passing)
uv run pytest tests/ -v

# Lint
uv run ruff check src/ tests/

# Format
uv run ruff format src/ tests/

# Type check
uv run mypy src/ --ignore-missing-imports

# Full CI pipeline
uv run pytest tests/ -q && uv run ruff check src/ && uv run mypy src/ --ignore-missing-imports
```

## CLI Reference

```bash
# Launch GUI (default)
octopus

# CLI interactive mode
octopus cli
octopus cli "Write a Python sorting algorithm"
octopus cli --model claude-sonnet-4-20250514 --permission-mode full_auto

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
octopus permissions add <pattern> --type path   # Add path rule
octopus permissions add <pattern> --type command # Add command rule

# Provider management
octopus provider list      # List configured providers
octopus provider use <name> # Switch default provider
octopus provider add <name> --api-key <key> --base-url <url>

# Session management
octopus session list       # List past sessions
octopus session resume <id> # Resume a session
octopus session new        # Start a new session
```

## Implementation Status

| Phase | Status | Content |
|-------|--------|---------|
| Phase 1 (Weeks 1-4) | ✅ Complete | Kernel, agent loop, tools, CLI |
| Phase 2 (Weeks 5-8) | ✅ Complete | Config, providers, Tauri GUI, IPC bridge |
| Phase 3 (Weeks 9-14) | ✅ Complete | Rollback engine, plugin system |
| Phase 4 (Weeks 15-20) | ✅ Complete | Context, compaction, memory, hooks, multi-agent, sandbox, auth, MCP |

## License

MIT License — see [LICENSE](LICENSE) for details.

## Acknowledgments

- [OpenHarness](https://github.com/HKUDS/OpenHarness) (HKUDS) for reference architecture
- [CubeSandbox](https://github.com/TencentCloud/CubeSandbox) (Tencent Cloud) for hardware-isolated sandbox
- Claude Desktop, Claude Code CLI, Codex, and Hermes for inspiration
