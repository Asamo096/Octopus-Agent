# Phase 10: TUI Fallback, Integration Testing & Hardening

> Generated: 2026-07-27
> Goal: Make Octopus-Agent production-ready from CLI through TUI, with comprehensive test coverage and hardened features

---

## Executive Summary

### Current Project Status

**Completed (Phases 1-6, partial 9):**

| Phase | Scope | Status |
|-------|-------|--------|
| Phase 1: MVP Core | Project scaffold, CLI entry, harness kernel | Done |
| Phase 2: Enhanced | Multi-provider, git/diff tools, config system | Done |
| Phase 3: Full | Harness panel stubs, rollback engine, plugin skeleton | Done |
| Phase 4: Gap Analysis | 15 gaps identified, all Tier 1-3 addressed | Done |
| Phase 5: claude-code Patterns | 10 patterns adopted (skills, cost, budget, compaction, etc.) | Done |
| Phase 6: CLI UI Polish | 9/10 patterns done (spinner, token warn, diff, tool render, compact, context, timestamps, titles, tool summary) | 90% Done |
| Phase 9 (partial): Workflow Engine | Workflow engine with built-in workflows | Done |

**Source code inventory (~13,000 lines Python, 69 files):**

```
Core kernel:     kernel.py(391), permissions.py(281), hooks.py(565),
                 audit.py, sandbox.py, state.py, rollback.py, trust.py
Agent system:    base.py, llm_agent.py, coordinator.py(402), registry.py
Loop engine:     engine.py(740), compaction.py(731), context.py,
                 models.py, cost.py
Tools:           base.py, filesystem.py(292), shell.py, git.py,
                 diff.py, search.py, mcp.py
Providers:       base.py, litellm_adapter.py
Config:          schema.py, loader.py, manager.py(283)
Memory:          schema.py, manager.py
Skills:          schema.py, loader.py, registry.py
Workflow:        engine.py, schema.py, builtin.py
Auth:            credentials.py
Sandbox:         adapter.py, cube.py, local.py
Bridge:          server.py, protocol.py
Plugins:         loader.py, manager.py, schemas.py
Utils:           file_cache.py, files.py, platform.py
CLI:             cli.py(454), cli_runtime.py(1796), cli_ui.py(1229)
```

**Not yet done:**

| Area | Status | Gap |
|------|--------|-----|
| Frontend (Phase 7) | Bare scaffold only (ChatPanel, Sidebar, Terminal stubs) | ~2,350 lines TSX remaining |
| TUI Fallback (Phase 4 Gap 14) | Not started | ~500 lines Python |
| Production Hardening (Phase 8) | Not started | ~2,200 lines |
| Integration/E2E Tests | Not started | Critical gap |
| Remaining Phase 6 pattern | Effort indicator not done | ~40 lines |

### Why Phase 10 Focuses on TUI + Testing + Hardening

The full GUI (Phase 7) is a major TypeScript/React undertaking (~2,350 lines) requiring a different toolchain and skill set. Meanwhile:

1. **A Textual TUI delivers immediate value** — it works in SSH/headless/tmux environments where a GUI cannot run, and costs only ~500 lines of Python
2. **Integration tests are critical** — the 13K-line codebase has zero integration or E2E tests; regressions are invisible
3. **Hardening gaps remain** — CubeSandbox is not wired into the kernel, the workflow engine lacks tests, and there are rough edges from rapid Phase 1-6 development

This phase prioritizes **high-ROI, Python-native work** that makes Octopus production-ready from the CLI/TUI surface, laying the foundation for the GUI later.

---

## Deliverables

### 1. Textual TUI Application (Week 1)
Convert the CLI from a Rich + prompt_toolkit hybrid into a full Textual terminal UI.

### 2. Integration Test Suite (Week 2)
Add tests for agent loop, tool execution pipeline, compaction, memory, and workflows.

### 3. E2E Test Workflows (Week 2-3)
Automated end-to-end scenarios: chat session, code fix, session resume, permission modes.

### 4. Hardening & Bug Fixes (Week 3)
Wire CubeSandbox into kernel, fix Phase 6 gap, improve error handling, CLI edge cases.

### 5. Documentation & Examples (Week 4)
Developer guide, example skills/workflows, architecture doc updates.

---

## Week 1: Textual TUI Application

### Goal
Replace the current CLI (Rich + prompt_toolkit hybrid) with a full Textual TUI that provides the same features plus a richer interface.

### TUI Architecture

```
+---+----------------------------------+
| S |  Chat / Output Area              |
| i |  +----------------------------+  |
| d |  | Messages (markdown)        |  |
| e |  |                            |  |
| b |  +----------------------------+  |
| a |  Input Area                     |
| r |  +----------------------------+  |
|   |  | > _                        |  |
+---+----------------------------------+
|     Status Bar (mode, tokens, cost)   |
+---------------------------------------+
```

### Files to Create

```
src/octopus/tui/
  __init__.py
  app.py           # Textual App subclass, main entry
  screens.py       # Screen definitions (chat, settings, logs)
  widgets/
    __init__.py
    chat.py        # Chat message list widget
    input.py       # Multi-line input with slash command support
    sidebar.py     # Session list, file tree, agent status
    status.py      # Status bar (mode, tokens, cost, model)
    diff.py        # Inline diff preview widget
    tool_output.py # Tool result rendering
    spinner.py     # Activity spinner widget
```

### Implementation Priority

#### 1a. Core App Shell (Priority: P0)
```python
# tui/app.py
class OctopusTUI(App):
    """Octopus-Agent Textual TUI application."""

    CSS_PATH = "octopus.tcss"
    BINDINGS = [
        ("ctrl+c", "quit", "Quit"),
        ("ctrl+p", "toggle_permission_mode", "Toggle Permissions"),
        ("ctrl+s", "focus_sidebar", "Sidebar"),
        ("ctrl+l", "focus_input", "Chat Input"),
        ("/", "slash_command", "Slash Command"),
    ]

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Horizontal():
            yield Sidebar(id="sidebar")
            with Vertical():
                yield ChatLog(id="chat-log")
                yield ChatInput(id="chat-input")
        yield StatusBar(id="status-bar")
```

#### 1b. Chat Message List (Priority: P0)
- Markdown rendering via Rich renderables inside Textual
- User/assistant/system message styling
- Tool call cards (expandable)
- Auto-scroll to bottom on new messages
- Timestamp display

#### 1c. Chat Input (Priority: P0)
- Multi-line input with Ctrl+Enter to submit
- Slash command autocomplete (reuse existing completer)
- Command history (up/down arrow, persisted)
- Emacs/vi keybindings via Textual Input

#### 1d. Sidebar (Priority: P1)
- Session list tab (create, resume, delete)
- File tree tab (workspace navigation)
- Agent status tab (active workers, coordinator)
- Keyboard navigation between tabs

#### 1e. Status Bar (Priority: P0)
- Permission mode indicator (Manual / Accept Edits / Plan / Auto)
- Token usage (current / max, percentage bar)
- Cost tracker ($0.0000)
- Current model name
- Activity indicator during tool execution

#### 1f. Tool Output Rendering (Priority: P1)
- Syntax-highlighted file contents
- Colored diff preview (green/red)
- Shell command output in terminal-style panel
- Collapsible long output
- Error output in red panel

#### 1g. CLI Entry Point Changes (Priority: P0)
```python
# cli.py — add --tui flag
@app.command()
def cli(
    prompt: str = typer.Argument(None),
    model: str = typer.Option(None, "--model", "-m"),
    permission_mode: str = typer.Option("default", "--permission-mode", "-p"),
    tui: bool = typer.Option(False, "--tui", help="Launch Textual TUI (default on --headless)"),
):
    if tui or not sys.stdout.isatty():
        from octopus.tui.app import OctopusTUI
        app = OctopusTUI()
        app.run()
    else:
        # Current CLI mode
        asyncio.run(run_interactive_async(...))
```

### Testing Targets
- TUI app launches and renders all widgets
- Chat input sends messages and displays responses
- Slash commands work in TUI mode
- Status bar updates with mode/token/cost changes
- Sidebar tabs switch correctly
- Keyboard shortcuts trigger correct actions

**Effort:** ~600 lines Python

---

## Week 2: Integration Test Suite

### Goal
Add comprehensive integration tests for all major subsystems. Currently the project has unit tests but zero integration/E2E tests.

### 2a. Agent Loop Integration Tests (Priority: P0)

```python
# tests/integration/test_agent_loop.py

class TestAgentLoop:
    """Integration tests for the agent query loop."""

    @pytest.mark.asyncio
    async def test_single_turn_no_tools(self, mock_provider):
        """Single turn: model responds with text, no tool calls."""
        ...

    @pytest.mark.asyncio
    async def test_multi_turn_with_tools(self, mock_provider, tool_registry):
        """Model calls read_file, gets result, continues conversation."""
        ...

    @pytest.mark.asyncio
    async def test_parallel_tool_execution(self, mock_provider, tool_registry):
        """Multiple tool calls in one turn execute concurrently."""
        ...

    @pytest.mark.asyncio
    async def test_max_turns_enforcement(self, mock_provider):
        """Loop stops after max_turns reached."""
        ...

    @pytest.mark.asyncio
    async def test_cost_budget_enforcement(self, mock_provider, cost_tracker):
        """Loop stops when cost budget exceeded."""
        ...

    @pytest.mark.asyncio
    async def test_tool_permission_blocked(self, mock_provider, kernel):
        """Blocked tool call returns error, loop continues."""
        ...

    @pytest.mark.asyncio
    async def test_streaming_events(self, mock_provider):
        """All stream event types appear in correct order."""
        ...
```

### 2b. Compaction Integration Tests (Priority: P0)

```python
# tests/integration/test_compaction.py

class TestCompaction:
    @pytest.mark.asyncio
    async def test_microcompact_clears_old_results(self):
        """Tool results older than threshold are cleared."""
        ...

    @pytest.mark.asyncio
    async def test_time_based_microcompact(self):
        """Results older than max_age_seconds are cleared."""
        ...

    @pytest.mark.asyncio
    async def test_context_collapse_truncates_large_blocks(self):
        """Oversized text blocks are truncated."""
        ...

    @pytest.mark.asyncio
    async def test_full_llm_compact(self, mock_provider):
        """Full compaction produces valid summary via LLM."""
        ...

    @pytest.mark.asyncio
    async def test_auto_compact_triggered(self, mock_provider):
        """Auto-compact fires when token threshold exceeded."""
        ...

    @pytest.mark.asyncio
    async def test_reactive_compact_escalation(self, mock_provider):
        """Reactive compact tries microcompact, collapse, then LLM compact."""
        ...

    @pytest.mark.asyncio
    async def test_compact_preserves_recent_context(self):
        """Recent messages and file contents survive compaction."""
        ...
```

### 2c. Tool Pipeline Integration Tests (Priority: P0)

```python
# tests/integration/test_tool_pipeline.py

class TestToolPipeline:
    @pytest.mark.asyncio
    async def test_read_file_through_kernel(self, kernel, tmp_path):
        """read_file tool passes through full harness pipeline."""
        ...

    @pytest.mark.asyncio
    async def test_write_file_with_permission_check(self, kernel, tmp_path):
        """write_file requires permission in manual mode."""
        ...

    @pytest.mark.asyncio
    async def test_shell_command_safety_validation(self, kernel):
        """Dangerous commands blocked, safe commands allowed."""
        ...

    @pytest.mark.asyncio
    async def test_edit_file_generates_rollback_checkpoint(self, kernel, tmp_path):
        """Pre-edit snapshot created for rollback."""
        ...

    @pytest.mark.asyncio
    async def test_audit_log_entry_created(self, kernel, tmp_path):
        """Every tool execution logged to audit trail."""
        ...

    @pytest.mark.asyncio
    async def test_git_tool_operations(self, kernel, git_repo):
        """Git status, diff, log work correctly."""
        ...

    @pytest.mark.asyncio
    async def test_mcp_tool_bridge(self, kernel, mcp_server):
        """MCP tools discovered and executed."""
        ...

    @pytest.mark.asyncio
    async def test_file_cache_hit(self, kernel, tmp_path):
        """Second read_file hits cache, does not re-read disk."""
        ...
```

### 2d. Memory System Integration Tests (Priority: P1)

```python
# tests/integration/test_memory.py

class TestMemorySystem:
    @pytest.mark.asyncio
    async def test_store_and_recall(self, memory_manager):
        """Store a memory, recall by keyword."""
        ...

    @pytest.mark.asyncio
    async def test_relevance_scoring(self, memory_manager):
        """More relevant memories score higher."""
        ...

    @pytest.mark.asyncio
    async def test_extract_from_conversation(self, memory_manager, mock_provider):
        """Facts extracted from conversation and stored."""
        ...

    @pytest.mark.asyncio
    async def test_memory_persistence_across_sessions(self, memory_manager, tmp_path):
        """Memories survive process restart."""
        ...
```

### 2e. Workflow Engine Integration Tests (Priority: P1)

```python
# tests/integration/test_workflow.py

class TestWorkflowEngine:
    @pytest.mark.asyncio
    async def test_workflow_phases_execute_in_order(self, workflow_engine):
        """Phase 1 completes before Phase 2 starts."""
        ...

    @pytest.mark.asyncio
    async def test_parallel_agents(self, workflow_engine, mock_provider):
        """Multiple agents run concurrently."""
        ...

    @pytest.mark.asyncio
    async def test_pipeline_stages(self, workflow_engine, mock_provider):
        """Pipeline processes items through stages."""
        ...

    @pytest.mark.asyncio
    async def test_workflow_error_handling(self, workflow_engine):
        """Agent failure doesn't crash the workflow."""
        ...

    @pytest.mark.asyncio
    async def test_builtin_workflow_code_review(self, workflow_engine, tmp_path):
        """Built-in code review workflow runs end-to-end."""
        ...
```

### 2f. Session Persistence Tests (Priority: P1)

```python
# tests/integration/test_session.py

class TestSessionPersistence:
    @pytest.mark.asyncio
    async def test_create_and_resume_session(self, state_manager):
        """Create session, add messages, close, resume, messages restored."""
        ...

    @pytest.mark.asyncio
    async def test_session_list(self, state_manager):
        """List all sessions, sorted by update time."""
        ...

    @pytest.mark.asyncio
    async def test_session_delete(self, state_manager):
        """Delete session removes messages and metadata."""
        ...

    @pytest.mark.asyncio
    async def test_resume_after_compaction(self, state_manager):
        """Session resumes correctly after compaction boundary."""
        ...
```

### Testing Targets
- Agent loop: 7 tests
- Compaction: 7 tests
- Tool pipeline: 9 tests
- Memory: 4 tests
- Workflow: 5 tests
- Session persistence: 4 tests
- **Total: ~36 integration tests**

**Effort:** ~800 lines Python (test code)

---

## Week 3: E2E Tests + Hardening

### 3a. E2E Test Workflows (Priority: P0)

```python
# tests/e2e/test_cli_workflows.py

class TestCLIWorkflows:
    """Full end-to-end CLI scenarios."""

    @pytest.mark.asyncio
    async def test_full_chat_session(self, octopus_cli):
        """User starts CLI, chats for 3 turns, exits cleanly."""
        ...

    @pytest.mark.asyncio
    async def test_code_fix_workflow(self, octopus_cli, tmp_project):
        """octopus code fix scans and fixes a buggy file."""
        ...

    @pytest.mark.asyncio
    async def test_code_test_workflow(self, octopus_cli, tmp_project):
        """octopus code test generates tests for a module."""
        ...

    @pytest.mark.asyncio
    async def test_permission_mode_cycle(self, octopus_cli):
        """Cycling through permission modes changes behavior."""
        ...

    @pytest.mark.asyncio
    async def test_session_resume_workflow(self, octopus_cli, tmp_project):
        """Create session, exit, resume, verify context restored."""
        ...

    @pytest.mark.asyncio
    async def test_slash_commands(self, octopus_cli):
        """/help, /model, /clear, /compact, /config all work."""
        ...

    @pytest.mark.asyncio
    async def test_config_set_and_persist(self, octopus_cli):
        """/config set model changes active model, persists across restart."""
        ...

    @pytest.mark.asyncio
    async def test_model_switching(self, octopus_cli):
        """/model switches provider, subsequent messages use new model."""
        ...
```

### 3b. Hardening Tasks (Priority: P0-P1)

#### CubeSandbox Kernel Integration
Current state: `sandbox/cube.py` adapter exists but `kernel.py` does not route execution through it.

```python
# core/kernel.py — wire sandbox into execute_tool

async def execute_tool(self, tool_call: ToolCall, context: Context) -> ToolResult:
    ...
    # After permission check, before tool execution:
    if self.sandbox.backend == SandboxBackend.CUBE:
        async with CubeBackend.create(
            template=self.settings.sandbox.cube_template_id,
            api_url=self.settings.sandbox.cube_api_url,
        ) as sandbox:
            result = await tool.execute_in_sandbox(sandbox, args, context)
    else:
        result = await tool.execute(args, context)
    ...
```

#### Remaining Phase 6 Pattern: Effort Indicator
```python
# cli_ui.py — add effort indicator
def print_effort_indicator(effort: str) -> None:
    effort_styles = {
        "low": "dim", "medium": "yellow",
        "high": "cyan", "max": "magenta",
    }
    style = effort_styles.get(effort, "dim")
    console.print(f"[{style}][thinking: {effort}][/{style}]", end=" ")
```

#### Error Handling Improvements
- Graceful handling of provider connection failures (retry with backoff)
- Clear error messages for config validation failures
- Recovery from partial tool execution failures
- Timeout handling for long-running shell commands

#### CLI Edge Cases
- Empty input handling (don't send to model)
- Very long single-line input (word wrap in prompt_toolkit)
- Ctrl+C during streaming (clean abort, not crash)
- Unicode/emoji handling in input and output
- Pipe/redirect compatibility (`octopus cli "prompt" | cat`)

### Testing Targets
- E2E: 8 scenarios
- Hardening: 6-8 fixes/improvements

**Effort:** ~600 lines (E2E tests + hardening)

---

## Week 4: Documentation + Polish

### 4a. Developer Documentation (Priority: P1)

```
docs/
  developer.md          # Updated: setup, architecture, contributing
  architecture.md       # Updated: current state, data flow diagrams
  tui-guide.md          # TUI usage, keyboard shortcuts, configuration
  workflow-authoring.md # How to write custom workflows
  skill-authoring.md    # How to create SKILL.md files
  examples/
    custom-skill.md     # Example: custom review skill
    custom-workflow.md  # Example: custom CI workflow
    config-examples.md  # Example configurations
```

### 4b. CLAUDE.md Update (Priority: P1)
Update project CLAUDE.md to reflect current codebase reality:
- Remove planned-file references that now exist
- Add TUI module to architecture diagram
- Add workflow engine to module list
- Update testing section for integration/E2E

### 4c. Example Skills (Priority: P2)

Bundle 3-5 additional skills:
```
src/octopus/skills/bundled/
  review/SKILL.md       # Existing
  explain/SKILL.md      # Existing
  refactor/SKILL.md     # New: structured refactoring with checklist
  test/SKILL.md         # New: generate comprehensive tests
  diagnose/SKILL.md     # New: diagnose and fix CI/build failures
```

### 4d. README and Quick Start (Priority: P2)
- Update README.md and README-zh_CN.md with new features
- Add TUI screenshots
- Quick start guide for first-time users

**Effort:** ~400 lines (docs + examples)

---

## Acceptance Criteria

### Must Have
- [ ] Textual TUI launches and provides full chat functionality
- [ ] All CLI slash commands work in TUI mode
- [ ] Agent loop integration tests pass (7 tests, >80% coverage of engine.py)
- [ ] Compaction integration tests pass (7 tests)
- [ ] Tool pipeline integration tests pass (9 tests)
- [ ] E2E CLI workflows pass (8 scenarios)
- [ ] CubeSandbox is wireable via kernel config (adapter ready, config schema complete)
- [ ] Phase 6 effort indicator implemented
- [ ] CLAUDE.md updated to reflect current codebase
- [ ] All existing unit tests still pass

### Nice to Have
- [ ] Memory system integration tests pass (4 tests)
- [ ] Workflow integration tests pass (5 tests)
- [ ] Session persistence tests pass (4 tests)
- [ ] Developer documentation complete
- [ ] 3+ additional bundled skills
- [ ] TUI keyboard shortcut reference card
- [ ] Slash command TUI integration (command palette accessible via `/`)

### Out of Scope
- React/TypeScript GUI development (Phase 7)
- Cross-platform packaging (Phase 8)
- Plugin marketplace (Phase 8)
- OAuth authentication (Phase 9)
- LSP integration (Phase 9)
- Team collaboration features (Phase 9)

---

## Effort Summary

| Week | Deliverable | Lines | Type |
|------|------------|-------|------|
| 1 | Textual TUI Application | ~600 | Python |
| 2 | Integration Test Suite | ~800 | Python (tests) |
| 3 | E2E Tests + Hardening | ~600 | Python (tests + code) |
| 4 | Documentation + Polish | ~400 | Markdown |
| **Total** | | **~2,400** | |

---

## Dependencies

```
TUI App ──→ uses existing: AgentLoop, Kernel, ToolRegistry, ProviderAdapter
Integration Tests ──→ needs: mock Provider, temp workspace
E2E Tests ──→ needs: fully configured CLI binary
CubeSandbox Integration ──→ uses existing: sandbox/cube.py adapter
Documentation ──→ depends on: TUI app completed, tests passing
```

---

## How This Fits the Big Picture

```
Phase 1-5:  Core backend (DONE)           ~13,000 lines Python
Phase 6:    CLI UI Polish (90% DONE)      ~840 lines
Phase 9p:   Workflow Engine (DONE)        ~500 lines
Phase 10:   TUI + Testing + Hardening     ~2,400 lines  <-- THIS PLAN
Phase 7:    GUI Completion (FUTURE)       ~2,350 lines TSX
Phase 8:    Production Hardening (FUTURE) ~2,200 lines
Phase 9:    MiMo-Code Patterns (FUTURE)   ~3,800 lines

After Phase 10: Octopus-Agent is a production-ready CLI + TUI application
with comprehensive test coverage, hardware sandbox support, and full documentation.
The GUI (Phase 7) becomes an additive enhancement on a stable foundation.
```

---

## Success Criteria

After Phase 10, Octopus-Agent should:

1. Launch in TUI mode (`octopus cli --tui`) with full chat, sidebar, and status bar
2. Work in headless/SSH environments via the TUI fallback
3. Pass 36+ integration tests covering agent loop, compaction, tools, memory, workflow, and sessions
4. Pass 8 E2E test scenarios covering real user workflows
5. Support CubeSandbox hardware isolation for tool execution
6. Display thinking effort level in CLI
7. Have complete developer documentation including workflow and skill authoring
8. Bundle 5+ example skills for common tasks
9. Gracefully handle errors: connection failures, timeouts, invalid config, empty input
10. Maintain backward compatibility: all existing features, commands, and configs work unchanged
