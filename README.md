# 🐙 Octopus Agent

Desktop + CLI dual AI coding & general-purpose agent client with **harness governance**.

Benchmarks Claude Desktop, Claude Code CLI, Codex, and Hermes agent capabilities. A standalone harness-governed intelligent assistant for ordinary users and developers.

## Core Differentiator: Harness Governance

All AI outputs, file operations, shell execution, and code writing behaviors are **intercepted, verified, and constrained** by the harness layer:

- **Permission Engine** — configurable allow/deny rules for paths and commands
- **Filesystem Sandbox** — AI can only operate within authorized directories
- **Shell Command Governance** — safe commands allowed, dangerous ones require approval
- **Full Behavior Audit** — every action logged to SQLite for review
- **Task Rollback** — one-click restore to any previous state (coming Phase 3)

## Quick Start

```bash
# Install from source
git clone https://github.com/octopus-agent/octopus-agent.git
cd octopus-agent
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ".[dev]"

# Show help
octopus --help

# Enter interactive CLI mode
octopus cli

# Run a single prompt
octopus cli "Write a Python sorting algorithm"

# Code agent subcommands
octopus code init       # Initialize workspace
octopus code fix        # Scan and fix bugs
octopus code test       # Generate unit tests
octopus code logs       # View audit logs

# Configuration
octopus config show
octopus config set permissions.mode full_auto

# Provider management
octopus provider list
octopus provider use openai
```

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    Entry: `octopus`                      │
├──────────────────────┬──────────────────────────────────┤
│   CLI Layer (Typer)  │   GUI Layer (Tauri + React)      │
├──────────────────────┴──────────────────────────────────┤
│              Shared Core: octopus-core                   │
│  ┌─────────┐ ┌──────────┐ ┌───────────┐ ┌───────────┐  │
│  │ Harness │ │  Agent   │ │   Tool    │ │  LLM      │  │
│  │ Kernel  │ │  System  │ │  System   │ │ Providers │  │
│  └─────────┘ └──────────┘ └───────────┘ └───────────┘  │
├─────────────────────────────────────────────────────────┤
│  SQLite (persistent state + audit) + WebSocket (IPC)     │
└─────────────────────────────────────────────────────────┘
```

## Development

```bash
# Run tests
.venv/bin/pytest tests/ -v

# Lint
.venv/bin/ruff check src/ tests/

# Type check
.venv/bin/mypy src/
```

## Tech Stack

| Layer | Technology |
|-------|-----------|
| GUI | Tauri 2.x + React + TypeScript |
| CLI | Typer + Rich |
| LLM | litellm (100+ providers) |
| Data | Pydantic v2 + SQLite (aiosqlite) |
| Testing | pytest + pytest-asyncio |

## Project Structure

```
src/octopus/
├── core/          # Harness kernel (permissions, audit, sandbox, hooks, state)
├── agents/        # Agent system (coming Phase 1 Week 3)
├── loop/          # Agent loop engine (coming Phase 1 Week 3)
├── tools/         # Tool system (coming Phase 1 Week 3)
├── providers/     # LLM provider adapters (coming Phase 1 Week 3)
├── config/        # Configuration management
├── bridge/        # GUI-CLI IPC bridge
├── plugins/       # Plugin system
└── utils/         # Utility functions
```

## License

MIT License — see [LICENSE](LICENSE) for details.

## Acknowledgments

- [OpenHarness](https://github.com/HKUDS/OpenHarness) (HKUDS) for reference architecture
- Claude Desktop, Claude Code CLI, Codex, and Hermes for inspiration
