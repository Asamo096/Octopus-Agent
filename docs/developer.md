# Octopus Agent — Developer Guide

## Quick Start

```bash
# Clone and install
git clone <repo-url> Octopus-Agent
cd Octopus-Agent
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev,textual]"

# Run tests
pytest

# Run type checking
mypy src/

# Run linting
ruff check src/
```

## Architecture

See [architecture.md](architecture.md) for the full system architecture diagram and component descriptions.

### Key Modules

| Module | Path | Purpose |
|--------|------|---------|
| Kernel | `octopus/core/kernel.py` | Central orchestrator — all actions pass through harness |
| Permissions | `octopus/core/permissions.py` | Permission engine (4 modes) |
| Audit | `octopus/core/audit.py` | Structured audit logging |
| Hooks | `octopus/core/hooks.py` | Pre/PostToolUse lifecycle hooks |
| Sandbox | `octopus/core/sandbox.py` | Filesystem isolation |
| Rollback | `octopus/core/rollback.py` | Task rollback via checkpoints |
| Engine | `octopus/loop/engine.py` | Agent query loop (think-act-observe) |
| Compaction | `octopus/loop/compaction.py` | Context overflow handling |
| Tools | `octopus/tools/` | File, shell, git, diff, search, MCP tools |
| Providers | `octopus/providers/` | LLM provider adapters (litellm) |
| Memory | `octopus/memory/` | Persistent knowledge storage |
| Skills | `octopus/skills/` | Markdown-based skill definitions |
| Plugins | `octopus/plugins/` | Plugin discovery and lifecycle |
| Workflow | `octopus/workflow/` | Multi-agent orchestration |
| CLI | `octopus/cli.py`, `cli_runtime.py`, `cli_ui.py` | CLI entry and UI |
| TUI | `octopus/tui/` | Textual terminal UI |
| Bridge | `octopus/bridge/` | WebSocket IPC for GUI |
| Sandbox Backends | `octopus/sandbox/` | Local and CubeSandbox backends |

## Configuration

Configuration files are in `~/.octopus/`:

- `auth.json` — API keys (sensitive, gitignored)
- `config.toml` — Provider and model settings
- `octopus.db` — SQLite database (sessions, audit log, state)
- `port` — WebSocket port (when bridge server is running)

## Testing

### Running Tests

```bash
# All tests
pytest

# Unit tests only
pytest tests/unit/

# Integration tests
pytest tests/integration/

# End-to-end tests
pytest tests/e2e/

# With coverage
pytest --cov=octopus --cov-report=term-missing
```

### Test Organization

```
tests/
  conftest.py          # Shared fixtures
  unit/                # Per-module unit tests
    test_kernel.py
    test_permissions.py
    test_compaction.py
    ...
  integration/         # Subsystem interaction tests
    test_agent_loop.py
    test_compaction.py
    test_tool_pipeline.py
    test_memory.py
    test_session.py
  e2e/                 # Full workflow tests
    test_cli_workflows.py
```

## Adding a New Tool

1. Create a tool class implementing the `Tool` protocol in `octopus/tools/base.py`:

```python
class MyTool:
    name = "my_tool"
    description = "Does something useful"
    parameters = {"type": "object", "properties": {...}}

    async def execute(self, args, context):
        return ToolResult(success=True, output="Done")

    def to_openai_schema(self):
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }
```

2. Register the tool:

```python
from octopus.tools.base import ToolRegistry

registry = ToolRegistry()
registry.register(MyTool())
```

## Adding a New Skill

Create a `SKILL.md` file with YAML frontmatter:

```markdown
---
name: my-skill
description: Does something useful
allowed-tools:
  - read_file
  - shell
---

# Skill Instructions

Detailed instructions for the skill here.

$ARGUMENTS
```

Place it in one of:
- `src/octopus/skills/bundled/` — shipped with Octopus
- `~/.octopus/skills/` — user-specific skills
- `<workspace>/.octopus/skills/` — project-specific skills

## Adding a Workflow

See `src/octopus/workflow/builtin.py` for examples. Workflows define phased multi-agent execution:

```python
from octopus.workflow.schema import WorkflowDefinition, PhaseDefinition

my_workflow = WorkflowDefinition(
    name="my-workflow",
    description="My custom workflow",
    phases=[
        PhaseDefinition(name="Analyze", prompt="Analyze the codebase"),
        PhaseDefinition(name="Fix", prompt="Fix issues found"),
    ],
    strategy="sequential",
)
```

## Code Style

- Python 3.11+, async-first
- Type hints on all functions
- Pydantic v2 for data models
- Ruff for linting and formatting
- No emoji anywhere
- 88 character line length
