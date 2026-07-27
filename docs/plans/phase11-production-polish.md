# Phase 11: Production Polish & Harness Excellence

> Generated: 2026-07-28
> Goal: Transform Octopus from a working prototype into a polished, production-grade agent that fully embodies Harness governance philosophy.

---

## Executive Summary

Phase 1-10 built the engine. Phase 11 makes it a product.

The Octopus Agent is not a research toy — it is the reference implementation of **Harness governance**: every action passes through Permission → Sandbox → Audit → Rollback. This phase focuses on making that philosophy visible, intuitive, and trustworthy for real users.

### Guiding Principles

1. **Harness-first**: Every feature surfaces the governance pipeline, not hides it
2. **Trust through visibility**: Users should see what the agent is doing, why, and what was checked
3. **Graceful degradation**: When things fail, fail informatively with recovery paths
4. **Polish matters**: Spacing, timing, color, animation — the details that separate a prototype from a product

### Current State

| Quality | Status |
|---------|--------|
| Core agent loop | Working |
| Harness pipeline (permission/sandbox/audit/rollback) | Working, but invisible to user |
| TUI | Working, needs polish |
| Error handling | Basic — no retry, no recovery hints |
| Test coverage | ~65% — needs integration depth |
| Documentation | Minimal developer docs |
| Packaging | pip install only, no standalone binary |
| Cross-platform | Linux only tested |

---

## Week 1-2: Harness Governance UI — Make the Invisible Visible

The harness pipeline is Octopus's core differentiator. Currently it operates silently — users have no idea permission checks, sandbox validation, and audit logging are happening. This must change.

### 1a. Permission Audit Trail in TUI (P0)

**`/audit` command** — opens interactive audit viewer:
```
┌─ Audit Trail ───────────────────────────────────────────────────────┐
│ Filter: [All ▼]  Session: current  │ 14 events                      │
│──────────────────────────────────────────────────────────────────────│
│ 14:32:01  read_file   main.py         ALLOWED        12ms          │
│ 14:32:05  shell       npm test        APPROVED       1.2s          │
│ 14:32:19  write_file  test_main.py    BLOCKED        0ms   ~/.ssh/ │
│ 14:32:25  grep        "def test"      ALLOWED        45ms          │
│──────────────────────────────────────────────────────────────────────│
│ [Enter] details  [/] filter  [e] export  [q] close                  │
└──────────────────────────────────────────────────────────────────────┘
```

- Real-time audit log with color-coded decisions (green=allowed, yellow=approved, red=blocked)
- Filter by tool, decision, time range
- Click for full details (args, result, duration)
- Export to JSON/CSV

### 1b. Permission Mode Indicator (P0)

Status bar shows current permission mode with clear visual distinction:
```
FULL_AUTO:    [auto]      — green  — no checks, all allowed
DEFAULT:      [manual]    — yellow — each action requires approval  
ACCEPT_EDITS: [edits]     — cyan   — allow file ops, block shell
PLAN:         [plan]      — blue   — all writes blocked
```

- `Ctrl+P` cycles with a brief toast showing what changed
- Mode change logged to audit trail

### 1c. Permission Request Dialog (P1)

When in DEFAULT mode, tool calls trigger an inline approval card in the chat:
```
┌─ Permission Required ──────────────────────────────────────────────┐
│ shell: rm -rf /tmp/cache                                           │
│ Risk: MEDIUM — this will delete files                              │
│                                                                    │
│ [Allow once]  [Allow all]  [Deny]  [Always deny this command]     │
│                                                                    │
│ Rule preview: deny "rm -rf /tmp/*"                                 │
└────────────────────────────────────────────────────────────────────┘
```

- Shows the tool, arguments, risk assessment
- One-click to create persistent permission rules
- Feedback loop: decision → audit log → rule update

### 1d. Rollback Preview (P1)

Before destructive operations, show what will change:
```
┌─ Pre-edit Snapshot ───────────────────────────────────────────────┐
│ File: src/core/kernel.py                                          │
│                                                                   │
│ - async def _sandbox_check(self, tool_call, ctx):                 │
│ + async def _sandbox_check(self, tool_call: ToolCall, ctx):       │
│                                                                   │
│ [Proceed]  [Skip]  [View full diff]                               │
└───────────────────────────────────────────────────────────────────┘
```

- Auto-snapshot before write/edit/shell
- Diff preview with accept/reject
- Rollback history: `/rollback list` and `/rollback restore <id>`

### Effort: ~600 lines Python

---

## Week 3-4: UI Polish & Responsiveness

The TUI must feel as smooth as Claude Code. Every frame counts.

### 2a. Smooth Scrolling (P0)
- Animated scroll with easing (not instant jumps)
- Fade-in for new messages (opacity 0→1 over 150ms)
- Batch mount operations — don't mount one widget at a time

### 2b. Message Spacing & Typography (P0)
```
❯ user message                                    ← 8px top margin
                                                  ← 4px gap
  assistant response with markdown rendering      ← 4px bottom
  second paragraph with proper line spacing       ← same block
                                                  ← 4px gap  
┌ shell echo hello ──────────────────────────────┐ ← tool card with
│ hello                                          │   consistent padding
└────────────────────────────────────────────────┘
                                                  ← 16px gap between turns
❯ next user message
```

- Consistent vertical rhythm (4/8/16px grid)
- Tool cards always same width (full chat width minus 2)
- Code blocks always same background, padding, font
- No orphaned single-line gaps

### 2c. Color System (P0)
```python
# Semantic token system — every color has a purpose
COLORS = {
    "bg":           "#0d1117",  # Screen background
    "surface":      "#161b22",  # Cards, panels
    "border":       "#21262d",  # Subtle borders
    "border_strong":"#30363d",  # Active/selected borders
    "text":         "#c9d1d9",  # Primary text
    "text_dim":     "#8b949e",  # Secondary text
    "text_muted":   "#484f58",  # Tertiary/disabled
    "accent":       "#58a6ff",  # Links, user messages
    "success":      "#7ee787",  # Allowed, completed
    "warning":      "#d29922",  # Requires approval
    "error":        "#f85149",  # Denied, failed
    "info":         "#79c0ff",  # Neutral information
    "code_bg":      "#0d1117",  # Inline code background
    "code_fg":      "#d2a8ff",  # Inline code text
}
```

- Consistent color usage across all components
- High contrast for text (WCAG AA minimum)
- Color-blind friendly: never rely on color alone

### 2d. Responsive Resize (P0)
Current resize triggers a full recompose — this causes visible flicker. Fix:
- Use CSS `min-width` / `max-width` for responsive breakpoints
- Never remove/re-mount on resize — use `display` toggle only
- Debounce resize events (100ms)
- Preserve scroll position across resize

### 2e. Animations & Micro-interactions (P1)
- Tool card: slide in from left (200ms)
- Message fade-in (150ms opacity transition)
- "Thinking..." pulse animation (breathing opacity)
- Permission mode change: brief flash on status bar
- Copy confirmation: brief "[Copied]" toast that fades after 1s

### Effort: ~500 lines Python

---

## Week 5-6: Reliability & Error Recovery

A product that crashes is not a product. Every failure mode must be handled.

### 3a. Network Error Recovery (P0)
```
┌─ Connection Lost ──────────────────────────────────────────────────┐
│ Provider API unreachable: https://api.example.com/v1               │
│                                                                   │
│ Retrying in 3s... (attempt 1/3)                                   │
│ [Retry now]  [Switch model]  [Exit]                               │
└───────────────────────────────────────────────────────────────────┘
```

- Auto-retry with exponential backoff (1s, 3s, 9s)
- Retry-After header support
- Provider health check on startup
- Graceful fallback to offline message

### 3b. Session Crash Recovery (P0)
- Auto-save conversation after every turn (already done)
- On crash, next launch offers to resume last session
- Session integrity check on load (no corrupted messages)
- Auto-compact before save to keep sessions small

### 3c. Input Validation (P1)
- Prevent sending empty messages
- Warn on very long messages (>10k chars): "This message is very long. Send anyway?"
- Escape rich markup in user input (prevent injection)
- Detect and warn on paste of secrets (API key patterns)

### 3d. Graceful Degradation (P1)
```
If textual not installed → fallback to basic CLI mode
If provider unreachable → show offline status, queue messages
If config invalid → show specific error with fix suggestion
If DB corrupted → offer repair or reset
```

### 3e. Error Messages That Help (P1)
Not: `AttributeError: 'NoneType' object has no attribute 'execute'`
But: `Tool 'shell' is not registered. Available tools: read, write, edit, shell, grep, glob.`

- Map every common error to a user-friendly message
- Include actionable next steps
- Log full traceback to file, show summary to user

### Effort: ~500 lines Python

---

## Week 7: Testing & Quality Gates

### 4a. Integration Test Depth (P0)
Current coverage: ~65%. Target: >80% for core modules.

| Module | Current | Target | New Tests |
|--------|---------|--------|-----------|
| kernel.py | 40% | 85% | Permission pipeline, sandbox routing, audit logging |
| permissions.py | 45% | 90% | All modes, all tool types, edge cases |
| loop/engine.py | 50% | 85% | Streaming, compaction, error recovery |
| loop/compaction.py | 55% | 85% | All 6 strategies, boundaries |
| tui/app.py | 0% | 60% | Component rendering, message flow |

### 4b. E2E Smoke Tests (P0)
```python
# tests/e2e/test_smoke.py
def test_full_chat_flow(): ...       # Send prompt, receive response
def test_tool_execution(): ...       # Model calls tool, result shown
def test_permission_block(): ...     # Blocked operation shows error
def test_session_resume(): ...       # Close, reopen, messages persist
def test_slash_commands(): ...       # All /commands work
def test_config_roundtrip(): ...     # Set config, restart, verify
```

### 4c. Performance Benchmarks (P1)
```
Startup time: <500ms (import + kernel init)
First token: <2s from submit
Streaming: >30 tokens/sec display rate
Memory: <200MB for 100-turn session
```

### Effort: ~400 lines Python (tests)

---

## Week 8: Documentation & Packaging

### 5a. User Documentation (P0)
```
docs/
  getting-started.md    ← 5-minute quick start
  configuration.md      ← All config options with examples  
  permissions.md        ← Permission system deep dive
  tui-guide.md          ← Updated with new features
  troubleshooting.md    ← Common issues and fixes
```

### 5b. Harness Philosophy Document (P0)
`docs/harness-philosophy.md` — explains the governance model:
- Why harness governance matters
- Permission → Sandbox → Audit → Rollback pipeline
- How to configure for different trust levels
- Case studies: untrusted code, team environments, CI/CD

### 5c. Standalone Packaging (P1)
```
# One-command install
curl -sSL https://get.octopus-agent.dev | bash

# pip install
pip install octopus-agent

# Binary distribution (PyInstaller)
octopus-linux-x86_64
octopus-darwin-arm64
```

### 5d. CI/CD Pipeline (P1)
```yaml
# .github/workflows/ci.yml
on: [push, pull_request]
jobs:
  lint:    ruff check + mypy
  test:    pytest (unit + integration + e2e)
  build:   PyInstaller binary + Tauri bundle
  release: publish to PyPI + GitHub Releases
```

### Effort: ~400 lines (docs + CI config)

---

## Implementation Roadmap

| Week | Deliverable | Effort |
|------|------------|--------|
| 1-2 | Harness Governance UI (audit viewer, permission dialog, rollback preview) | ~600 lines |
| 3-4 | UI Polish (scrolling, spacing, colors, animations, responsive resize) | ~500 lines |
| 5-6 | Reliability (error recovery, crash recovery, input validation, graceful degradation) | ~500 lines |
| 7 | Testing (integration depth, E2E smoke tests, performance benchmarks) | ~400 lines |
| 8 | Documentation + Packaging (user docs, harness philosophy, CI/CD) | ~400 lines |
| **Total** | | **~2,400 lines** |

---

## Dependencies

```
Harness UI ──→ uses existing: PermissionEngine, AuditLogger, RollbackEngine
UI Polish ──→ uses existing: OctopusTUI, all widgets
Reliability ──→ uses existing: LiteLLMProvider, Kernel, StateManager
Testing ──→ builds on existing test suite
Packaging ──→ PyInstaller + GitHub Actions
```

---

## Acceptance Criteria

### Must Have (P0)
- [ ] `/audit` shows interactive audit trail with filter/search
- [ ] Permission mode changes show visual feedback
- [ ] Smooth scrolling with fade-in animations
- [ ] Consistent color system applied everywhere
- [ ] Network errors auto-retry with user feedback
- [ ] Session crash recovery (auto-resume on restart)
- [ ] All common errors have user-friendly messages
- [ ] Integration test coverage >80% for core modules
- [ ] 5 E2E smoke tests covering critical paths
- [ ] User documentation complete (getting started, config, permissions)
- [ ] Harness philosophy document published

### Nice to Have (P1)
- [ ] Permission request inline dialog with one-click rule creation
- [ ] Rollback preview with diff before destructive operations
- [ ] Tool card slide-in animation
- [ ] Input validation (empty check, length warning, secret detection)
- [ ] Standalone binary packaging (PyInstaller)
- [ ] CI/CD pipeline (lint + test + build)
- [ ] Performance benchmarks tracking

### Out of Scope (Phase 12+)
- Multi-agent workflow UI
- MCP tool bridge
- Plugin system UI
- OAuth authentication
- Team collaboration
- Mobile/web interface
