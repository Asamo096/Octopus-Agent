# Phase 3: Full (Weeks 9-14)

## Goal

Production-ready release with full GUI features, harness control panel, plugin system, task rollback, and cross-platform packaging. This phase completes the product vision.

---

## Week 9-10: Harness Control Panel + Audit Viewer

### Deliverables
- [ ] Harness control panel GUI component
- [ ] Real-time permission request dialog
- [ ] Audit log viewer with search and filters
- [ ] Permission rule editor (add/remove/modify rules)
- [ ] Agent status dashboard (active session, token usage, cost)
- [ ] Governance mode switcher (Default/Plan/Full Auto)

### Control Panel Layout
```
┌─────────────────────────────────────────────────────────┐
│  Harness Control Panel                                   │
├──────────────┬──────────────┬───────────────────────────┤
│  Status      │  Permissions │  Audit Log                 │
│              │              │                            │
│  Mode:       │  Rules:      │  2026-07-25 14:32:01      │
│  [Default ▼] │  ✓ ~/code/*  │  read_file: main.py       │
│              │  ✗ ~/.ssh/*  │  Status: ALLOWED           │
│  Session:    │  ✗ sudo      │  Duration: 12ms            │
│  Active      │              │                            │
│              │  [Add Rule]  │  2026-07-25 14:32:05      │
│  Tokens:     │              │  shell: npm test           │
│  12,450      │              │  Status: APPROVED          │
│              │              │  Duration: 1,234ms         │
│  Cost:       │              │                            │
│  $0.03       │              │  [Export] [Filter] [Clear] │
└──────────────┴──────────────┴───────────────────────────┘
```

### Permission Request Dialog
```typescript
// When agent tries a dangerous operation, GUI shows:
interface PermissionDialog {
  tool: string;           // "shell"
  description: string;    // "Execute shell command"
  arguments: Record<string, unknown>;  // {"command": "rm -rf /tmp/cache"}
  risk_level: "low" | "medium" | "high";
  options: ["Allow", "Allow Once", "Deny", "Always Deny"];
}
```

### Audit Viewer Features
- Chronological list of all agent actions
- Filter by: tool name, permission decision, date range, session
- Search by: file path, command string, result content
- Export to JSON/CSV
- Click to see full details (args, result, duration)

### Testing Targets
- Control panel renders with live data
- Permission dialog appears for dangerous operations
- Audit log shows entries from CLI session
- Rule editor persists changes to config

---

## Week 11: Code Editor + Diff Preview

### Deliverables
- [ ] Code editor widget (CodeMirror 6 or Monaco)
- [ ] Inline diff preview for proposed changes
- [ ] Accept/reject individual file changes
- [ ] File tree sidebar with change indicators
- [ ] Syntax highlighting for 50+ languages
- [ ] Side-by-side diff view

### Editor Integration
```
┌─────────────────────────────────────────────────────────┐
│  File: src/main.py                        [Accept] [Reject] │
├─────────────────────────────────────────────────────────┤
│  1 │ import os                                          │
│  2 │                                                    │
│  3 │-def old_function():                               │
│  3 │+def new_function(param: str) -> bool:             │
│  4 │-    return False                                   │
│  4 │+    return param.startswith("valid")              │
│  5 │                                                    │
│  6 │ if __name__ == "__main__":                         │
│  7 │-    old_function()                                 │
│  7 │+    result = new_function("valid_input")          │
│  8 │+    print(f"Result: {result}")                    │
└─────────────────────────────────────────────────────────┘
```

### File Tree with Change Indicators
```
📁 src/
  📄 main.py          [+2 -2]  ✏️
  📄 utils.py          [unchanged]
  📁 models/
    📄 user.py         [+15]    🆕
    📄 config.py       [unchanged]
📁 tests/
  📄 test_main.py      [+8 -1]  ✏️
```

### Diff Generation Pipeline
```python
# tools/diff.py
class DiffTool(Tool):
    async def execute(self, args, context) -> ToolResult:
        """Generate structured diff.
        
        Returns:
            unified_diff: str  # Standard unified diff
            files: list[FileDiff]  # Per-file changes
            summary: ChangeSummary  # Stats (+N -N files)
        """
```

### Testing Targets
- Editor renders code with syntax highlighting
- Diff view shows additions (green) and deletions (red)
- Accept/reject buttons work correctly
- File tree updates with change indicators

---

## Week 12: Task Rollback Engine

### Deliverables
- [ ] `core/rollback.py` — Checkpoint/restore system
- [ ] PreToolUse hook for automatic snapshots
- [ ] One-click rollback in GUI
- [ ] `octopus rollback` CLI command
- [ ] Rollback history viewer
- [ ] Git-aware rollback (respects git state)

### Rollback Architecture
```python
class RollbackEngine:
    """Task rollback via state checkpoints."""
    
    def __init__(self, db: aiosqlite.Connection, workspace: Path):
        self.db = db
        self.workspace = workspace
    
    async def checkpoint(self, tool_call: ToolCall, context: Context) -> str:
        """Create checkpoint before tool execution.
        - Snapshot affected files
        - Store in SQLite
        - Return checkpoint ID
        """
    
    async def rollback(self, checkpoint_id: str) -> RollbackResult:
        """Restore files to checkpoint state.
        - Read snapshot from SQLite
        - Write files back
        - Return list of restored files
        """
    
    async def list_checkpoints(self, session_id: str) -> list[Checkpoint]:
        """List all checkpoints for a session."""
    
    async def diff_checkpoint(self, checkpoint_id: str) -> str:
        """Show diff between checkpoint and current state."""
```

### SQLite Schema
```sql
CREATE TABLE checkpoints (
    id TEXT PRIMARY KEY,
    session_id TEXT,
    tool_name TEXT,
    tool_args JSON,
    created_at TIMESTAMP,
    files JSON  -- [{path, content_hash, content}]
);
```

### CLI Commands
```bash
octopus rollback list           # List checkpoints
octopus rollback show <id>      # Show checkpoint details
octopus rollback restore <id>   # Restore to checkpoint
octopus rollback diff <id>      # Show diff from checkpoint
```

### Testing Targets
- Checkpoint created before each file modification
- Rollback restores exact file content
- Multiple rollbacks work correctly
- Git-aware: doesn't rollback uncommitted git changes

---

## Week 13: Plugin System

### Deliverables
- [ ] `plugins/loader.py` — Plugin discovery from directories
- [ ] `plugins/manager.py` — Plugin lifecycle (load, enable, disable, unload)
- [ ] `plugins/schemas.py` — Plugin manifest schema
- [ ] Plugin directories: `~/.octopus/plugins/`, `.octopus/plugins/`
- [ ] Example plugins (3+)
- [ ] `octopus plugin list/install/uninstall` CLI commands
- [ ] Plugin development documentation

### Plugin Manifest
```json
{
  "name": "my-plugin",
  "version": "1.0.0",
  "description": "A custom tool plugin",
  "author": "Developer",
  "octopus_version": ">=0.1.0",
  "tools": ["tools.py"],
  "providers": ["providers.py"],
  "hooks": {
    "pre_tool_use": ["hooks.py:check_sensitive"],
    "post_tool_use": ["hooks.py:log_custom"]
  }
}
```

### Plugin API
```python
# plugins/schemas.py
class Plugin:
    """Base class for Octopus plugins."""
    
    def register_tools(self, registry: ToolRegistry): ...
    def register_providers(self, registry: ProviderRegistry): ...
    def register_hooks(self, hook_manager: HookManager): ...
```

### Example Plugins
1. **custom-search** — Adds a custom web search tool
2. **jira-integration** — Jira issue lookup and update
3. **slack-notify** — Send notifications to Slack on task completion

### Testing Targets
- Plugin discovery from user and project directories
- Plugin tools register and execute correctly
- Plugin hooks fire at correct lifecycle points
- Plugin disable/unload cleans up properly

---

## Week 14: Cross-Platform Packaging

### Deliverables
- [ ] PyInstaller build for Python backend (Windows/macOS/Linux)
- [ ] Tauri bundler configuration for full app
- [ ] macOS: .dmg with ad-hoc signing
- [ ] Windows: .msi installer via NSIS
- [ ] Linux: .AppImage
- [ ] `scripts/package.py` — Automated packaging script
- [ ] `scripts/release.py` — Release automation
- [ ] Installation documentation

### Build Pipeline
```bash
# Python backend (PyInstaller)
pyinstaller --name octopus-backend --onefile src/octopus/__main__.py

# Tauri app (bundles Python backend as sidecar)
cd src-tauri && cargo tauri build

# Output:
# macOS:   src-tauri/target/release/bundle/dmg/Octopus-Agent_0.1.0_aarch64.dmg
# Windows: src-tauri/target/release/bundle/msi/Octopus-Agent_0.1.0_x64.msi
# Linux:   src-tauri/target/release/bundle/appimage/Octopus-Agent_0.1.0_amd64.AppImage
```

### CI/CD Matrix
```yaml
# .github/workflows/release.yml
strategy:
  matrix:
    include:
      - os: macos-latest
        target: aarch64-apple-darwin
        artifact: dmg
      - os: macos-latest
        target: x86_64-apple-darwin
        artifact: dmg
      - os: windows-latest
        target: x86_64-pc-windows-msvc
        artifact: msi
      - os: ubuntu-latest
        target: x86_64-unknown-linux-gnu
        artifact: appimage
```

### Testing Targets
- macOS .dmg installs and runs
- Windows .msi installs and runs
- Linux .AppImage runs
- `octopus` command available in PATH after install
- GUI launches from installed app

---

## Acceptance Criteria

### Must Have
- [ ] Harness control panel shows real-time status
- [ ] Permission dialogs work for dangerous operations
- [ ] Audit log viewable and searchable in GUI
- [ ] Code editor shows syntax-highlighted code
- [ ] Diff preview shows proposed changes before applying
- [ ] Accept/reject individual file changes
- [ ] One-click rollback to any checkpoint
- [ ] Plugin system loads custom tools and hooks
- [ ] Standalone installers for macOS, Windows, Linux
- [ ] End-to-end: install → launch → chat → code edit → rollback

### Nice to Have
- [ ] Auto-update mechanism
- [ ] Plugin marketplace/registry
- [ ] Voice input (STT)
- [ ] Multi-agent coordination GUI

### Out of Scope (Future)
- IM channel integration (Telegram, Slack)
- Repo-level autopilot
- Mobile apps
- Cloud sync
