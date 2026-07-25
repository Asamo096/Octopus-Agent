# Phase 2: Enhanced (Weeks 5-8)

## Goal

Multi-provider support, advanced tools, full configuration system, and GUI foundation. This phase expands the CLI's capabilities and introduces the Tauri + React desktop shell with terminal embedding.

---

## Week 5: Multi-Provider + Advanced Tools

### Deliverables
- [ ] `providers/openai.py` — OpenAI-compatible provider
- [ ] `providers/local.py` — Ollama / local model provider
- [ ] `providers/anthropic.py` — Claude-specific features (extended thinking, etc.)
- [ ] `tools/git.py` — Git operations (status, diff, commit, checkout, log)
- [ ] `tools/diff.py` — Structured diff generation for GUI preview
- [ ] `tools/search.py` — Web search (via httpx), code search
- [ ] Provider switching via CLI: `octopus provider use <name>`
- [ ] Integration tests for provider switching

### Module Details

#### Provider System
```python
# providers/base.py
class ProviderProfile(BaseModel):
    """Named provider configuration."""
    name: str
    provider: str          # "anthropic", "openai", "ollama", "custom"
    api_format: str        # "openai", "anthropic"
    model: str
    base_url: str | None = None
    api_key: str | None = None  # Resolved from env/file/keyring

class Provider(Protocol):
    async def stream_messages(
        self, messages: list[Message], tools: list[Tool], model: str
    ) -> AsyncIterator[StreamEvent]: ...
    
    async def count_tokens(self, messages: list[Message], model: str) -> int: ...
```

#### Git Tool
```python
class GitTool(Tool):
    name = "git"
    actions = ["status", "diff", "commit", "checkout", "log", "add", "reset"]
    
    async def execute(self, args, context) -> ToolResult:
        action = args["action"]
        # Validate action is allowed
        # Execute git command via asyncio.create_subprocess_exec
        # Return structured result
```

#### Diff Tool
```python
class DiffTool(Tool):
    name = "diff"
    
    async def execute(self, args, context) -> ToolResult:
        """Generate structured diff for GUI preview.
        Returns: unified diff text + per-file change summary
        """
```

### Testing Targets
- Provider switching: configure 2+ providers, switch mid-session
- Git tool: status, diff, commit in a test repo
- Diff tool: generate diffs for file modifications
- Token counting accuracy per provider

---

## Week 6: Configuration System

### Deliverables
- [ ] `config/schema.py` — Full Pydantic settings models
- [ ] `config/loader.py` — Multi-layer resolution (CLI > env > file > defaults)
- [ ] `config/sync.py` — SQLite state store foundation
- [ ] `octopus config show/set/list` commands
- [ ] Project-level config (`.octopus/config.yaml` in project root)
- [ ] Config validation and error messages
- [ ] Unit tests for config loading and validation

### Configuration Schema
```python
class OctopusSettings(BaseModel):
    # Provider profiles
    providers: list[ProviderProfile] = []
    default_provider: str = "anthropic"
    default_model: str = "claude-sonnet-4-20250514"
    
    # Harness governance
    permissions: PermissionSettings = PermissionSettings()
    sandbox: SandboxSettings = SandboxSettings()
    
    # GUI preferences (used by Phase 3)
    gui: GUISettings = GUISettings()
    
    # CLI preferences
    cli: CLISettings = CLISettings()

class PermissionSettings(BaseModel):
    mode: Literal["default", "plan", "full_auto"] = "default"
    allowed_tools: list[str] = []
    denied_tools: list[str] = []
    path_rules: list[PathRule] = []
    denied_commands: list[str] = ["rm -rf /", "sudo rm", "mkfs", "dd if="]
    
class GUISettings(BaseModel):
    theme: str = "system"
    font_size: int = 14
    terminal_shell: str = "/bin/bash"
    show_harness_panel: bool = True
```

### Multi-Layer Resolution
```
1. CLI arguments (--model, --permission-mode)
2. Environment variables (OCTOPUS_MODEL, OCTOPUS_API_KEY, etc.)
3. Config file (~/.octopus/settings.yaml)
4. Project config (.octopus/config.yaml)
5. Defaults (in Pydantic models)
```

### SQLite Schema Foundation
```sql
-- sessions table
CREATE TABLE sessions (
    id TEXT PRIMARY KEY,
    name TEXT,
    created_at TIMESTAMP,
    updated_at TIMESTAMP,
    metadata JSON
);

-- messages table
CREATE TABLE messages (
    id TEXT PRIMARY KEY,
    session_id TEXT REFERENCES sessions(id),
    role TEXT,
    content TEXT,
    created_at TIMESTAMP
);

-- audit_log table
CREATE TABLE audit_log (
    id TEXT PRIMARY KEY,
    session_id TEXT,
    tool_name TEXT,
    arguments JSON,
    result JSON,
    duration_ms INTEGER,
    permission_decision TEXT,
    created_at TIMESTAMP
);
```

### Testing Targets
- Config loading from file, env vars, CLI args
- Config validation (invalid values, missing required fields)
- Project-level config inheritance
- SQLite schema creation and basic CRUD

---

## Week 7: Tauri + React GUI Shell

### Deliverables
- [ ] `src-tauri/` — Tauri project scaffolding
- [ ] `frontend/` — React + TypeScript project with Vite
- [ ] xterm.js terminal widget (connects to Python PTY)
- [ ] Basic app layout: sidebar + main area
- [ ] Python sidecar integration (Tauri spawns Python process)
- [ ] IPC foundation: JSON-RPC over localhost WebSocket
- [ ] Dev workflow: `npm run dev` + `python -m octopus` hot reload

### Tauri Project Setup
```bash
# Initialize Tauri project
npm create tauri-app@latest src-tauri -- --template react-ts

# Key dependencies
cd frontend
npm install @xterm/xterm @xterm/addon-fit @xterm/addon-webgl
npm install zustand react-markdown react-syntax-highlighter
npm install @codemirror/view @codemirror/state  # Code editor
```

### IPC Protocol
```typescript
// frontend/src/lib/ipc.ts
interface IPCMessage {
  id: string;
  method: string;
  params: Record<string, unknown>;
}

interface IPCResponse {
  id: string;
  result?: unknown;
  error?: { code: number; message: string };
}

// Methods:
// "chat.send" — Send user message to agent
// "chat.stream" — Receive streamed response
// "tool.execute" — Execute a tool call
// "tool.approve" — Approve pending permission request
// "config.get" — Get config value
// "config.set" — Set config value
// "session.list" — List chat sessions
// "session.create" — Create new session
// "audit.query" — Query audit log
```

### App Layout
```
┌──────────┬──────────────────────────────────────┐
│          │  Chat Area                            │
│ Sessions │  ┌──────────────────────────────────┐ │
│ List     │  │ Messages (markdown rendered)      │ │
│          │  │                                   │ │
│          │  └──────────────────────────────────┘ │
│          │  ┌──────────────────────────────────┐ │
│          │  │ Input Area                        │ │
│          │  └──────────────────────────────────┘ │
│          ├──────────────────────────────────────┤
│          │  Terminal (xterm.js)                  │
│          │  ┌──────────────────────────────────┐ │
│          │  │ $ _                               │ │
│          │  └──────────────────────────────────┘ │
└──────────┴──────────────────────────────────────┘
```

### Testing Targets
- Tauri app launches and shows React UI
- xterm.js terminal connects to Python PTY
- IPC round-trip: send message, receive response
- Python sidecar starts and connects to WebSocket

---

## Week 8: GUI-CLI Bridge + Basic Chat

### Deliverables
- [ ] `bridge/server.py` — WebSocket server in Python
- [ ] `bridge/client.py` — WebSocket client (for CLI to connect to running GUI)
- [ ] `bridge/protocol.py` — Shared message types
- [ ] Basic chat working in GUI (send prompt, receive streamed response)
- [ ] Session persistence (survives app restart)
- [ ] CLI can connect to running GUI instance (shared state)
- [ ] Integration tests for GUI-CLI bridge

### Bridge Architecture
```
┌─────────────┐     WebSocket      ┌─────────────┐
│  GUI App    │ ◄──────────────────► │  Python     │
│  (Tauri)    │   localhost:PORT    │  Sidecar    │
└─────────────┘                     └──────┬──────┘
                                           │
┌─────────────┐     WebSocket      ┌──────┴──────┐
│  CLI Client │ ◄──────────────────► │  State DB   │
│  (Typer)    │   localhost:PORT    │  (SQLite)   │
└─────────────┘                     └─────────────┘
```

### State Sync
```python
# bridge/server.py
class BridgeServer:
    """WebSocket server for GUI/CLI IPC."""
    
    def __init__(self, kernel: Kernel, db_path: Path):
        self.kernel = kernel
        self.db = aiosqlite.connect(db_path)
        self.clients: set[WebSocket] = set()
    
    async def start(self, port: int = 0):
        """Start server on dynamic port, write port to ~/.octopus/port"""
    
    async def broadcast(self, message: dict):
        """Send message to all connected clients."""
```

### Testing Targets
- Bridge server starts and accepts connections
- CLI connects to running GUI instance
- Chat message flows: GUI → bridge → agent → bridge → GUI
- Session persistence across app restarts
- Concurrent access: GUI and CLI both active

---

## Acceptance Criteria

### Must Have
- [ ] Multiple LLM providers configurable and switchable
- [ ] Git tool works (status, diff, commit)
- [ ] Config system with multi-layer resolution
- [ ] Tauri app launches with embedded terminal
- [ ] Basic chat works in GUI
- [ ] Sessions persist across restarts
- [ ] CLI can connect to running GUI instance

### Nice to Have
- [ ] Web search tool
- [ ] Code editor widget (Monaco/CodeMirror)
- [ ] Theme switching (light/dark)
- [ ] Project-level config (.octopus/config.yaml)

### Out of Scope (Phase 3)
- Harness control panel GUI
- Code editor with diff preview
- Task rollback
- Plugin system
- Cross-platform packaging
