# Phase 1: MVP Core (Weeks 1-4)

## Goal

Functional CLI tool with harness kernel. This phase delivers the foundational runtime: a working `octopus` command that can chat with an LLM, execute tools through the harness governance pipeline, and run in interactive or single-command mode.

---

## Week 1: Project Scaffolding

### Deliverables
- [ ] `pyproject.toml` with hatchling build backend, all dependencies
- [ ] `src/octopus/` package structure (all `__init__.py` files)
- [ ] `src/octopus/__main__.py` for `python -m octopus`
- [ ] `tests/conftest.py` with shared fixtures
- [ ] CI pipeline (GitHub Actions): lint (ruff), type check (mypy), test (pytest)
- [ ] `README.md` with project description and quick start
- [ ] `.gitignore` updated for Python + future JS/Rust

### Key Tasks
1. Create `pyproject.toml`:
   ```toml
   [build-system]
   requires = ["hatchling"]
   build-backend = "hatchling.build"

   [project]
   name = "octopus-agent"
   version = "0.1.0"
   requires-python = ">=3.11"
   dependencies = [
       "typer>=0.12.0",
       "rich>=13.0.0",
       "prompt-toolkit>=3.0.0",
       "pydantic>=2.0.0",
       "httpx>=0.27.0",
       "litellm>=1.40.0",
       "pyyaml>=6.0",
       "aiosqlite>=0.20.0",
   ]

   [project.optional-dependencies]
   dev = ["pytest", "pytest-asyncio", "pytest-cov", "ruff", "mypy"]
   textual = ["textual>=0.80.0"]

   [project.scripts]
   octopus = "octopus.cli:app"
   ```

2. Initialize module structure:
   ```
   src/octopus/__init__.py
   src/octopus/__main__.py
   src/octopus/cli.py
   src/octopus/core/__init__.py
   src/octopus/agents/__init__.py
   src/octopus/loop/__init__.py
   src/octopus/tools/__init__.py
   src/octopus/providers/__init__.py
   src/octopus/config/__init__.py
   src/octopus/utils/__init__.py
   ```

### Testing
- Verify `pip install -e .` works
- Verify `octopus --help` shows usage
- Verify `python -m octopus --help` works

---

## Week 2: Harness Kernel

### Deliverables
- [ ] `core/kernel.py` — Central orchestrator
- [ ] `core/permissions.py` — Permission engine
- [ ] `core/audit.py` — Audit logger
- [ ] `core/sandbox.py` — Filesystem sandbox
- [ ] `core/hooks.py` — PreToolUse/PostToolUse lifecycle
- [ ] `core/state.py` — Global state manager
- [ ] Unit tests for all kernel components

### Module Details

#### `core/kernel.py`
```python
class Kernel:
    """Central orchestrator. Every agent action passes through it."""
    
    def __init__(self, settings: OctopusSettings):
        self.permissions = PermissionEngine(settings.permissions)
        self.audit = AuditLogger(settings.audit)
        self.sandbox = Sandbox(settings.sandbox)
        self.hooks = HookManager()
        self.state = StateManager()
    
    async def execute_tool(self, tool_call: ToolCall, context: Context) -> ToolResult:
        """Full harness pipeline:
        1. PreToolUse hooks (permission check, rollback checkpoint)
        2. Sandbox validation (path access, command safety)
        3. Tool execution
        4. PostToolUse hooks (audit log, result validation)
        """
```

#### `core/permissions.py`
```python
class PermissionEngine:
    """Multi-level permission checker."""
    
    # Three modes
    DEFAULT = "default"    # Confirm mutating operations
    PLAN = "plan"          # Block all writes
    FULL_AUTO = "full_auto"  # Allow everything
    
    SENSITIVE_PATHS = [
        "~/.ssh/*", "~/.aws/*", "~/.gnupg/*",
        "**/.env", "**/.env.*", "**/id_rsa*", "**/id_ed25519*",
    ]
    
    def check(self, tool_call: ToolCall, context: Context) -> PermissionResult:
        """Check if tool call is allowed."""
```

#### `core/audit.py`
```python
class AuditLogger:
    """Structured audit trail for all agent actions."""
    
    async def log(self, event: AuditEvent):
        """Log: timestamp, tool, args, result, duration, permission decision."""
    
    async def query(self, filters: AuditFilters) -> list[AuditEvent]:
        """Search audit log."""
```

#### `core/sandbox.py`
```python
class Sandbox:
    """Filesystem sandbox isolation."""
    
    def validate_path(self, path: Path, operation: str) -> bool:
        """Check if path is within allowed workspace."""
    
    def validate_command(self, command: str) -> CommandSafety:
        """Check if shell command is safe."""
```

#### `core/hooks.py`
```python
class HookManager:
    """PreToolUse/PostToolUse lifecycle hooks."""
    
    def register(self, event: str, hook: Hook): ...
    async def fire(self, event: str, data: dict) -> HookResult: ...
```

### Testing Targets
- Permission engine: 15+ test cases (sensitive paths, glob patterns, modes)
- Audit logger: write/read/query tests
- Sandbox: path validation, command safety checks
- Hooks: register/fire lifecycle tests
- Kernel: integration test (full pipeline with mock tool)

---

## Week 3: Agent Loop + Tools

### Deliverables
- [ ] `loop/engine.py` — Core query loop
- [ ] `loop/context.py` — Conversation context management
- [ ] `loop/compaction.py` — Auto-compact when context too long
- [ ] `tools/base.py` — Tool protocol & registry
- [ ] `tools/filesystem.py` — read_file, write_file, edit_file, glob, grep
- [ ] `tools/shell.py` — Shell command execution (governed)
- [ ] `providers/base.py` — Provider protocol
- [ ] `providers/litellm_adapter.py` — litellm unified adapter
- [ ] Unit tests for agent loop and tools

### Module Details

#### `loop/engine.py`
```python
async def run_query(
    messages: list[Message],
    tools: list[Tool],
    provider: Provider,
    kernel: Kernel,
    context: Context,
) -> AsyncIterator[StreamEvent]:
    """The agent loop:
    1. Auto-compact check (token budget)
    2. Stream model response via provider
    3. If stop_reason == "tool_use":
       - Execute tools (parallel via asyncio.gather)
       - Append results to messages
       - Loop back to step 1
    4. If no tool calls: done, yield final text
    5. Reactive compaction if prompt too long (retry after summarizing)
    6. Max turns enforcement
    """
```

#### `tools/base.py`
```python
class Tool(Protocol):
    name: str
    description: str
    input_schema: dict[str, Any]
    
    async def execute(self, args: dict, context: Context) -> ToolResult: ...

class ToolRegistry:
    def register(self, tool: Tool): ...
    def get(self, name: str) -> Tool | None: ...
    def list_tools(self) -> list[dict]: ...  # For provider tool definitions
```

#### `tools/filesystem.py`
```python
class ReadFileTool(Tool):
    name = "read_file"
    async def execute(self, args, context) -> ToolResult: ...

class WriteFileTool(Tool):
    name = "write_file"
    async def execute(self, args, context) -> ToolResult: ...

class EditFileTool(Tool):
    name = "edit_file"
    async def execute(self, args, context) -> ToolResult: ...

class GlobTool(Tool):
    name = "glob"
    async def execute(self, args, context) -> ToolResult: ...

class GrepTool(Tool):
    name = "grep"
    async def execute(self, args, context) -> ToolResult: ...
```

#### `tools/shell.py`
```python
class ShellTool(Tool):
    name = "shell"
    async def execute(self, args, context) -> ToolResult:
        # 1. kernel.permissions.check_command(args["command"])
        # 2. kernel.sandbox.validate_command(args["command"])
        # 3. Execute via asyncio.create_subprocess_shell
        # 4. Return stdout/stderr/exit_code
```

#### `providers/litellm_adapter.py`
```python
class LiteLLMProvider:
    """Unified LLM provider via litellm."""
    
    async def stream_messages(
        self, messages: list[Message], tools: list[Tool], model: str
    ) -> AsyncIterator[StreamEvent]:
        # 1. Convert messages/tools to litellm format
        # 2. Call litellm.acompletion(stream=True)
        # 3. Yield StreamEvent for each chunk
        # 4. Track token usage
```

### Testing Targets
- Agent loop: mock provider, verify tool dispatch loop, max turns, compaction
- Tool registry: register/get/list
- Filesystem tools: read/write/edit with sandbox validation
- Shell tool: command execution through permission pipeline
- Provider: streaming response handling

---

## Week 4: CLI Entry Point

### Deliverables
- [ ] `cli.py` — Typer CLI with all commands
- [ ] Interactive mode with Rich rendering
- [ ] Single-command mode (`octopus cli "prompt"`)
- [ ] `octopus --help` with full usage info
- [ ] Integration tests for CLI workflows
- [ ] Getting-started documentation

### CLI Structure
```python
app = typer.Typer(name="octopus", help="AI agent with harness governance")

@app.callback()
def main(
    gui: bool = typer.Option(False, "--gui", help="Launch GUI (default on desktop)"),
    version: bool = typer.Option(False, "--version"),
):
    """Octopus Agent — AI coding assistant with harness governance."""

@app.command()
def cli(
    prompt: str = typer.Argument(None, help="Single prompt (omit for interactive)"),
    model: str = typer.Option(None, "--model", "-m"),
    permission_mode: str = typer.Option("default", "--permission-mode", "-p"),
):
    """Enter CLI interactive mode or run a single prompt."""

@app.command()
def code(
    action: str = typer.Argument(..., help="init|fix|test|refactor|logs"),
):
    """Code agent subcommands."""

@app.command()
def config(
    action: str = typer.Argument(..., help="show|set"),
    key: str = typer.Argument(None),
    value: str = typer.Argument(None),
):
    """Configuration management."""
```

### Interactive Mode Features
- Rich-formatted markdown output
- Code block syntax highlighting
- Permission prompts (y/n for dangerous operations)
- Session history (up/down arrow)
- `/help`, `/clear`, `/exit` slash commands
- Streaming token display

### Testing Targets
- `octopus --help` output
- `octopus cli "hello"` single prompt
- `octopus config show` output
- `octopus code init` workspace setup
- Interactive mode: send prompt, receive response

---

## Acceptance Criteria

### Must Have
- [ ] `octopus` command launches and shows help
- [ ] `octopus cli` enters interactive chat mode
- [ ] `octopus cli "prompt"` runs single prompt and exits
- [ ] All file operations pass through permission engine
- [ ] Sensitive paths are blocked by default
- [ ] Shell commands are validated before execution
- [ ] All actions are logged to audit trail
- [ ] Unit tests pass with >80% coverage for core modules

### Nice to Have
- [ ] `octopus code init` creates workspace config
- [ ] `octopus code logs` shows recent audit entries
- [ ] Streaming response display in interactive mode

### Out of Scope (Phase 2+)
- GUI
- Multiple LLM providers
- Git tool, diff tool
- Task rollback
- Plugin system
- Cross-platform packaging
