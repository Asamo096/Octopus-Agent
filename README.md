# Octopus Agent

Desktop + CLI dual AI coding & general-purpose agent client with **harness governance**.

Benchmarks Claude Desktop, Claude Code CLI, Codex, and Hermes agent capabilities. A standalone harness-governed intelligent assistant for ordinary users and developers.

## Core Differentiator: Harness Governance

All AI outputs, file operations, shell execution, and code writing behaviors are **intercepted, verified, and constrained** by the harness layer:

- **Permission Engine** — 4 modes: manual, accept_edits, plan, auto
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
pip install -e ".[dev]"

# Configure provider
octopus cli
/config set provider openai
/config set api_key sk-your-key-here
/config set base_url https://api.openai.com/v1
/model                    # Select model with arrow keys

# Or use litellm-native provider
/config set provider xiaomi_mimo
/config set api_key your-key-here
/model

# Start chatting
❯ Write a Python sorting algorithm
```

## Usage Modes

### Interactive CLI

```bash
octopus cli                           # Start interactive session
octopus cli -c <session-id>           # Resume a session
octopus cli --model gpt-4o            # Use specific model
octopus cli --permission-mode auto    # Set permission mode
```

### Single Prompt

```bash
octopus cli "Write a hello world in Python"
octopus cli "Fix the bug in main.py"
```

### Code Agent

```bash
octopus code init           # Initialize workspace
octopus code fix            # Scan and fix bugs
octopus code test           # Generate unit tests
octopus code refactor       # Refactor codebase
octopus code logs           # View audit logs
```

## Permission Modes

| Mode | Shell | Write/Read/Delete | Use Case |
|------|-------|-------------------|----------|
| **manual** | Ask approval | Ask approval | Untrusted code, review everything |
| **accept_edits** | Block | Allow | Code review, allow edits but no execution |
| **plan** | Block | Allow | Planning, allow file ops but no execution |
| **auto** | Allow | Allow | Trusted environment, full automation |

Switch modes with `Shift+Tab` during a session.

## In-Session Commands

| Command | Description |
|---------|-------------|
| `/help` | Show help |
| `/model` | Fetch & select model (arrow keys) |
| `/config show` | Show current configuration |
| `/config set model <m>` | Set model name |
| `/config set provider <p>` | Set provider name |
| `/config set base_url <u>` | Set provider base URL |
| `/config set api_key <key>` | Set API key |
| `/tokens` | Show token estimate |
| `/compact` | Force conversation compaction |
| `/reset` | Reset conversation |
| `/exit` | Exit |

## Configuration

Configuration files are stored in `~/.octopus/`:

### auth.json (API keys)

```json
{
  "OPENAI_API_KEY": "sk-...",
  "ANTHROPIC_API_KEY": "sk-ant-..."
}
```

### config.toml (Provider settings)

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
- Budget enforcement (turns, tool calls, tokens)

### Multi-Agent System
- In-process agent coordinator with parallel/sequential execution
- Built-in agent definitions: general, explorer, reviewer, planner
- Background worker agents with per-worker budgets
- Agent definitions from markdown with YAML frontmatter

### Memory System
- Persistent cross-session memory stored as markdown files
- Relevance scoring with TF-based search and importance/recency boosts
- Memory types: user, feedback, project, reference
- Session memory compaction with fact extraction

### Hook System (4 Types)
- **Python** — async callback hooks
- **Command** — shell execution with `$ARGUMENTS` and env injection
- **HTTP** — webhook POST to external services
- **Prompt** — LLM-based validation
- Hot-reload on config file change
- Default hooks: permission check, rollback checkpoint, audit log

### Skills System
- Markdown-based skill definitions with YAML frontmatter
- Skill discovery: bundled, user, project directories
- Argument substitution (`$ARGUMENTS`, `$1`, `$2`, etc.)
- Per-skill tool restrictions

### Sandbox Isolation
- **CubeSandbox** — hardware-isolated KVM MicroVMs (sub-60ms cold start)
- **Local** — subprocess fallback when CubeSandbox unavailable
- File read/write, command execution, snapshots, rollback

### Response Handling
- XML tool call parsing for providers without function calling
- Code block detection and execution
- Bare shell command detection
- Thinking block stripping
- Model artifact cleanup
- Per-tool-type output rendering (syntax highlight, panels)

### Retry & Error Handling
- Exponential backoff (10 retries, 0.5s-32s)
- 429/529 rate limit handling
- Prompt-too-long reactive compaction
- Orphaned tool_use/tool_result cleanup

## Tools (14)

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

## Tech Stack

| Layer | Technology |
|-------|-----------|
| GUI | Tauri 2.x + React + TypeScript |
| CLI | Typer + Rich + prompt-toolkit |
| LLM | litellm (100+ providers) |
| Data | Pydantic v2 + SQLite (aiosqlite) |
| Sandbox | CubeSandbox (KVM MicroVM) |
| Memory | Markdown files with YAML frontmatter |
| Auth | Fernet encryption (cryptography) |
| Testing | pytest + pytest-asyncio |
| Linting | ruff + mypy |

## Development

```bash
# Install dependencies
pip install -e ".[dev]"

# Run tests
pytest tests/ -v

# Lint
ruff check src/ tests/

# Format
ruff format src/ tests/

# Type check
mypy src/
```

## Implementation Status

| Phase | Status | Content |
|-------|--------|---------|
| Phase 1 (Weeks 1-4) | Complete | Kernel, agent loop, tools, CLI |
| Phase 2 (Weeks 5-8) | Complete | Config, providers, Tauri GUI, IPC bridge |
| Phase 3 (Weeks 9-14) | Complete | Rollback engine, plugin system |
| Phase 4 (Weeks 15-20) | Complete | Context, compaction, memory, hooks, multi-agent, sandbox, auth, MCP |
| Phase 5 (Weeks 21-26) | Complete | claude-code patterns: skills, file cache, budget, worker agents |

## License

MIT License — see [LICENSE](LICENSE) for details.

## Acknowledgments

- [OpenHarness](https://github.com/HKUDS/OpenHarness) (HKUDS) for reference architecture
- [claude-code](https://github.com/anthropics/claude-code) (Anthropic) for CLI patterns
- [CubeSandbox](https://github.com/TencentCloud/CubeSandbox) (Tencent Cloud) for hardware-isolated sandbox
- Claude Desktop, Claude Code CLI, Codex, and Hermes for inspiration
