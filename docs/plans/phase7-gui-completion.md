# Phase 7: GUI Completion

> Generated: 2026-07-26
> Reference: ~/claude-code (Tauri + React, TypeScript)
> Goal: Wire the React frontend to the Python backend, completing the desktop GUI

---

## Executive Summary

Phase 1-5 completed the core backend, CLI, and harness governance. Phase 6 polishes the CLI UI. Phase 7 wraps the backend into a working desktop GUI application using Tauri + React, mirroring Claude Desktop's UX.

### Current State

The frontend scaffold exists (`frontend/`) with basic components, but:
- No WebSocket IPC connection to Python backend
- Chat panel doesn't stream responses
- Terminal (xterm.js) placeholder only
- No editor/diff view
- No harness panel controls

### Patterns to Adopt

| # | Pattern | Source | Effort | Priority |
|---|---------|--------|--------|----------|
| 1 | Chat panel with streaming | `App.tsx` | ~300 lines | P0 |
| 2 | WebSocket IPC bridge | `replBridge.ts` | ~200 lines | P0 |
| 3 | Terminal (xterm.js PTY) | `Terminal/` | ~200 lines | P0 |
| 4 | Code editor + diff preview | `Editor/`, `diff/` | ~400 lines | P1 |
| 5 | Harness control panel | `HarnessPanel/` | ~300 lines | P1 |
| 6 | Sidebar (files, sessions) | `Sidebar/` | ~250 lines | P1 |
| 7 | Settings panel | `Settings/` | ~250 lines | P2 |
| 8 | State management (Zustand) | `stores/` | ~200 lines | P2 |
| 9 | Tauri sidecar management | `main.rs` | ~150 lines | P1 |
| 10 | Cross-platform packaging | `build.ts` | ~100 lines | P2 |

**Total estimated effort:** ~2,350 lines

---

## Pattern 1: Chat Panel with Streaming

**What claude-code does:**
- Messages rendered as React components with role-specific styling
- Streaming text rendered in real-time via SSE/WebSocket
- Tool calls shown as expandable cards
- Markdown rendering for assistant messages
- Message actions (copy, retry, edit)

**Implementation:**

```typescript
// frontend/src/components/Chat/ChatPanel.tsx
interface Message {
  id: string;
  role: 'user' | 'assistant' | 'system' | 'tool';
  content: string;
  timestamp: Date;
  toolCalls?: ToolCall[];
}

function ChatPanel() {
  const messages = useChatStore(s => s.messages);
  const { sendMessage } = useIPC();
  const [streaming, setStreaming] = useState(false);
  const [partialText, setPartialText] = useState('');

  return (
    <div className="chat-panel">
      <MessageList messages={messages} />
      {streaming && <StreamingMessage text={partialText} />}
      <ChatInput onSubmit={sendMessage} disabled={streaming} />
    </div>
  );
}
```

**Effort:** ~300 lines (TypeScript) | **Priority:** P0

---

## Pattern 2: WebSocket IPC Bridge

**What claude-code does:**
- WebSocket connection between React frontend and Python backend
- JSON message protocol for commands, responses, streaming
- Reconnection with exponential backoff
- Heartbeat/ping for connection health

**Implementation:**

```python
# src/octopus/bridge/server.py — WebSocket server

async def handle_client(websocket: WebSocketServerProtocol) -> None:
    """Handle a GUI client connection."""
    async for message in websocket:
        data = json.loads(message)
        msg_type = data.get("type")

        if msg_type == "chat":
            # Stream assistant response
            async for event in run_query(...):
                await websocket.send(json.dumps({
                    "type": event.type.value,
                    "data": event.text or event.tool_call,
                }))
        elif msg_type == "tool_approval":
            # Forward permission decision
            decision = data.get("approved", False)
            ...
```

```typescript
// frontend/src/lib/ipc.ts
class IPCClient {
  private ws: WebSocket;
  private reconnectDelay = 1000;

  connect() {
    this.ws = new WebSocket('ws://localhost:9876');
    this.ws.onmessage = this.handleMessage;
    this.ws.onclose = () => setTimeout(() => this.connect(), this.reconnectDelay);
  }

  send(type: string, data: any) {
    this.ws.send(JSON.stringify({ type, ...data }));
  }
}
```

**Effort:** ~200 lines | **Priority:** P0

---

## Pattern 3: Terminal (xterm.js PTY)

**What claude-code does:**
- xterm.js terminal widget embedded in React
- PTY connection to shell process via Tauri sidecar
- Full VT100 support (colors, cursor, resize)
- Terminal tabs for multiple sessions

**Implementation:**

```typescript
// frontend/src/components/Terminal/TerminalWidget.tsx
import { Terminal } from '@xterm/xterm';
import { FitAddon } from '@xterm/addon-fit';
import { WebglAddon } from '@xterm/addon-webgl';

function TerminalWidget() {
  const terminalRef = useRef<HTMLDivElement>(null);
  const term = useRef<Terminal>();

  useEffect(() => {
    term.current = new Terminal({
      fontFamily: 'Menlo, Monaco, monospace',
      fontSize: 13,
      theme: {
        background: '#1e1e1e',
        foreground: '#d4d4d4',
      },
    });

    const fitAddon = new FitAddon();
    term.current.loadAddon(fitAddon);
    term.current.loadAddon(new WebglAddon());

    term.current.open(terminalRef.current!);
    fitAddon.fit();

    // Connect to Python shell via IPC
    ipc.send('terminal_open', { rows: term.current.rows, cols: term.current.cols });
    term.current.onData(data => ipc.send('terminal_input', { data }));

    ipc.on('terminal_output', ({ data }) => term.current?.write(data));
  }, []);

  return <div ref={terminalRef} className="terminal-container" />;
}
```

**Effort:** ~200 lines | **Priority:** P0

---

## Pattern 4: Code Editor + Diff Preview

**What claude-code does:**
- Monaco editor for code viewing/editing
- Diff view with split pane (old/new)
- Syntax highlighting for all major languages
- Line numbers, minimap, word wrap
- File path breadcrumb navigation

**Implementation:**

```typescript
// frontend/src/components/Editor/DiffPreview.tsx
import { DiffEditor } from '@monaco-editor/react';

function DiffPreview({ original, modified, filePath }: {
  original: string;
  modified: string;
  filePath: string;
}) {
  return (
    <div className="diff-preview">
      <div className="diff-header">
        <span className="file-path">{filePath}</span>
        <button onClick={onAccept}>Accept</button>
        <button onClick={onReject}>Reject</button>
      </div>
      <DiffEditor
        original={original}
        modified={modified}
        language={getLanguage(filePath)}
        theme="vs-dark"
        options={{ readOnly: true, minimap: { enabled: false } }}
      />
    </div>
  );
}
```

**Effort:** ~400 lines | **Priority:** P1

---

## Pattern 5: Harness Control Panel

**What claude-code does:**
- Permission mode toggle
- Audit log viewer
- Rollback history
- Sandbox status
- Hook configuration

**Implementation:**

```typescript
// frontend/src/components/HarnessPanel/HarnessPanel.tsx
function HarnessPanel() {
  const { permissionMode, setPermissionMode } = useHarnessStore();

  return (
    <div className="harness-panel">
      <h3>Harness Governance</h3>

      <section>
        <h4>Permission Mode</h4>
        <select value={permissionMode} onChange={e => {
          setPermissionMode(e.target.value);
          ipc.send('set_permission_mode', { mode: e.target.value });
        }}>
          <option value="default">Manual</option>
          <option value="plan">Plan</option>
          <option value="accept_edits">Accept Edits</option>
          <option value="full_auto">Auto</option>
        </select>
      </section>

      <section>
        <h4>Audit Log</h4>
        <AuditLogTable />
      </section>

      <section>
        <h4>Rollback</h4>
        <RollbackHistory />
      </section>
    </div>
  );
}
```

**Effort:** ~300 lines | **Priority:** P1

---

## Pattern 6: Sidebar (Files, Sessions)

**What claude-code does:**
- File tree navigation
- Session list with resume
- Agent status display
- MCP server status

**Implementation:**

```typescript
// frontend/src/components/Sidebar/Sidebar.tsx
function Sidebar() {
  const [activeTab, setActiveTab] = useState<'files' | 'sessions' | 'agents'>('files');

  return (
    <div className="sidebar">
      <TabBar activeTab={activeTab} onChange={setActiveTab} />
      {activeTab === 'files' && <FileTree />}
      {activeTab === 'sessions' && <SessionList />}
      {activeTab === 'agents' && <AgentStatus />}
    </div>
  );
}
```

**Effort:** ~250 lines | **Priority:** P1

---

## Pattern 7: Settings Panel

**What claude-code does:**
- Model configuration
- Provider management
- API key setup
- Theme/personalization
- Keyboard shortcuts

**Implementation:**

```typescript
// frontend/src/components/Settings/SettingsPanel.tsx
function SettingsPanel() {
  return (
    <div className="settings-panel">
      <section>
        <h4>Model</h4>
        <ModelPicker />
      </section>
      <section>
        <h4>Provider</h4>
        <ProviderConfig />
      </section>
      <section>
        <h4>API Keys</h4>
        <APIKeyManager />
      </section>
      <section>
        <h4>Appearance</h4>
        <ThemePicker />
      </section>
    </div>
  );
}
```

**Effort:** ~250 lines | **Priority:** P2

---

## Pattern 8: State Management (Zustand)

**What claude-code does:**
- Zustand stores for chat, harness, config state
- Real-time sync between stores and Python backend
- Persistent state (localStorage/SQLite)
- Optimistic updates for responsiveness

**Implementation:**

```typescript
// frontend/src/stores/chat.ts
interface ChatState {
  messages: Message[];
  streaming: boolean;
  partialText: string;
  sendMessage: (text: string) => void;
  addMessage: (msg: Message) => void;
  setStreaming: (v: boolean) => void;
}

const useChatStore = create<ChatState>((set, get) => ({
  messages: [],
  streaming: false,
  partialText: '',

  sendMessage: (text: string) => {
    const msg: Message = { id: uuid(), role: 'user', content: text, timestamp: new Date() };
    set(s => ({ messages: [...s.messages, msg], streaming: true }));
    ipc.send('chat', { message: text });
  },

  addMessage: (msg: Message) => set(s => ({
    messages: [...s.messages, msg],
    streaming: false,
    partialText: '',
  })),

  setStreaming: (v: boolean) => set({ streaming: v }),
}));
```

**Effort:** ~200 lines | **Priority:** P2

---

## Pattern 9: Tauri Sidecar Management

**What claude-code does:**
- Launches Python backend as Tauri sidecar process
- Manages process lifecycle (start, stop, restart)
- Stdio IPC between Rust shell and Python
- Port allocation for WebSocket server

**Implementation:**

```toml
# src-tauri/tauri.conf.json
{
  "bundle": {
    "externalBin": ["binaries/octopus-backend"]
  }
}
```

```rust
// src-tauri/src/main.rs
fn main() {
    tauri::Builder::default()
        .setup(|app| {
            // Start Python sidecar
            let sidecar = app.shell().sidecar("octopus-backend")?.spawn()?;

            // Wait for WebSocket port
            let port = read_port_from_stdout(&sidecar);

            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("error running tauri application");
}
```

**Effort:** ~150 lines | **Priority:** P1

---

## Pattern 10: Cross-Platform Packaging

**What claude-code does:**
- PyInstaller for Python backend bundling
- Tauri bundler for frontend + Rust shell
- Platform-specific installers (DMG, MSI, AppImage)
- Auto-update via Tauri updater

**Implementation:**

```bash
# Build Python backend
pyinstaller --onefile src/octopus/__main__.py \
  --name octopus-backend \
  --add-data "src/octopus:octopus"

# Build Tauri frontend
npm run tauri build
```

**Effort:** ~100 lines | **Priority:** P2

---

## Implementation Roadmap

### Phase 7A: Core GUI (Weeks 31-32)

| Week | Tasks | Effort |
|------|-------|--------|
| 31 | Pattern 1 (Chat panel) + Pattern 2 (IPC bridge) | ~500 lines |
| 32 | Pattern 3 (Terminal) + Pattern 8 (State stores) | ~400 lines |

**Deliverable:** Working GUI with chat streaming and terminal.

### Phase 7B: Feature GUI (Weeks 33-35)

| Week | Tasks | Effort |
|------|-------|--------|
| 33 | Pattern 4 (Editor/Diff) + Pattern 9 (Sidecar) | ~550 lines |
| 34 | Pattern 5 (Harness panel) + Pattern 6 (Sidebar) | ~550 lines |
| 35 | Pattern 7 (Settings) + integration testing | ~350 lines |

**Deliverable:** Full-featured GUI with editor, harness controls, sidebar.

### Phase 7C: Packaging (Weeks 36-37)

| Week | Tasks | Effort |
|------|-------|--------|
| 36 | Pattern 10 (PyInstaller + Tauri bundler) | ~150 lines |
| 37 | Cross-platform testing, installer creation | ~100 lines |

**Deliverable:** Standalone desktop application for Linux, macOS, Windows.

---

## Dependencies

```
Pattern 2 (IPC Bridge) ──→ Pattern 1 (Chat), Pattern 3 (Terminal)
Pattern 8 (State Stores) ──→ Pattern 4 (Editor), Pattern 5 (Harness)
Pattern 9 (Sidecar) ──→ Pattern 10 (Packaging)
```

---

## Success Criteria

After Phase 7, Octopus should:

1. Chat panel streams AI responses in real-time
2. Terminal widget connects to Python shell via PTY
3. File edits show colored diff preview in Monaco editor
4. Harness panel allows permission mode switching, audit viewing, rollback
5. Sidebar shows file tree, session list, agent status
6. Settings panel for model, provider, API key configuration
7. TypeScript frontend communicates with Python backend via WebSocket
8. Cross-platform installers for Linux, macOS, Windows
9. Tauri sidecar manages Python process lifecycle
10. State syncs between GUI and CLI via shared SQLite
