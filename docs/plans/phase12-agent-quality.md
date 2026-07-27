# Phase 12: Agent Quality — Production-Grade Development Workflow

> Generated: 2026-07-28
> Goal: Fix the broken tool execution pipeline, implement claude-code-level code writing workflow, make Octopus usable for real work.

---

## Problem Statement

The current agent is **unusable for real development work**. A simple request like "write an HTML file" results in:

```
write love.html (attempt 1) → model doesn't see result, retries
write love.html (attempt 2) → same content, different JSON key order
shell cat > love.html        → same content via shell
edit love.html               → empty old_string, useless
write love.html (attempt 3) → still retrying
shell printf > love.html     → yet another approach
... 10+ redundant calls, file never actually written correctly
```

**Root causes:**
1. Tool dedup fails (JSON key ordering, cross-tool duplicates, partial dedup)
2. System prompt doesn't teach proper tool usage patterns
3. No turn limits — model loops forever retrying
4. Tool results not being fed back correctly to model
5. Model doesn't understand when a tool succeeded

---

## Benchmarks: How Claude Code Works

### claude-code Development Flow

```
User: "write an HTML love letter page"
    │
    ▼
1. write_file(path="love.html", content="<!DOCTYPE html>...")
    │
    ▼
2. [Tool result: "Wrote love.html (2.3KB)"]
    │
    ▼
3. "I've created love.html with a romantic design..."
   [DONE — no retries, no redundant calls]
```

Key differences from Octopus:
- **One write call, one result** — model trusts the tool result
- **Precise edit tool**: `edit_file(old_string, new_string)` for targeted changes
- **Read-before-write**: model reads existing files before modifying
- **Clear success indicators**: tool results clearly state success/failure
- **Max turns enforced**: never loops more than 50 turns
- **System prompt is production-grade**: 100+ lines of precise instructions

### MiMo-Code Development Flow

```
User: "write an HTML love letter page"
    │
    ▼
1. Uses write_file or shell with heredoc
    │
    ▼
2. [Tool result: success/failure with exit code]
    │
    ▼
3. If success → describes what was done
   If failure → diagnoses why, tries DIFFERENT approach
```

Key additions:
- **Error diagnosis**: when a tool fails, the model analyzes the error
- **Different approach on retry**: never retries the same command twice
- **Verification**: reads back the file to confirm it was written correctly

---

## Implementation Plan

### Phase 12A: Fix Tool Execution Pipeline (Week 1)

#### 12A-1. Robust Tool Call Dedup (P0)

Current dedup only checks `(tool_name, json_args)` with sorted keys. Still fails when:
- Same file written via `write_file` AND `shell cat` AND `shell printf`
- Same command with slightly different quoting

New dedup algorithm:
```python
def _dedup_tool_calls(calls: list[ToolCall]) -> list[ToolCall]:
    """Aggressive dedup to prevent redundant tool calls."""

    seen_hashes = set()       # (tool_name, content_hash) for write/edit
    seen_paths = set()        # file paths being written to
    unique = []

    for tc in calls:
        # Parse args
        args = parse_json(tc.arguments)

        # Hash-based dedup for write/edit: same content = same result
        if tc.name in ("write", "write_file", "edit", "edit_file"):
            content = args.get("content") or args.get("new_string", "")
            path = args.get("path") or args.get("file_path", "")
            content_hash = hashlib.sha256(content.encode()).hexdigest()

            # Same content hash → skip
            key = (tc.name, content_hash)
            if key in seen_hashes:
                continue
            seen_hashes.add(key)

            # Same path via different tools → keep first
            if path and path in seen_paths:
                continue
            if path:
                seen_paths.add(path)

        # Shell dedup: normalize command before comparison
        if tc.name == "shell":
            cmd = args.get("command", "")
            normalized = normalize_shell(cmd)  # strip whitespace, normalize quotes
            key = ("shell", normalized)
            if key in seen_hashes:
                continue
            seen_hashes.add(key)

            # File-targeting shell: extract target path
            target = extract_target_path(cmd)
            if target and target in seen_paths:
                continue
            if target:
                seen_paths.add(target)

        unique.append(tc)

    return unique
```

#### 12A-2. Turn Limit Enforcement (P0)

```python
MAX_TURNS = 50  # Maximum tool-calling turns per user message

# In the engine loop:
turn_count = 0
while turn_count < MAX_TURNS:
    response = await provider.stream(...)
    if no_tool_calls_in_response:
        break  # Model is done
    turn_count += 1
    if turn_count >= MAX_TURNS:
        yield error("Reached maximum number of tool-calling turns")
        break
```

#### 12A-3. Tool Result Feedback (P0)

Ensure tool results are fed back to the model in the correct format:

```python
# After tool execution, append to messages:
{
    "role": "tool",
    "tool_call_id": tc.id,
    "content": json.dumps({
        "success": result.success,
        "output": result.output,
        "error": result.error,
        "exit_code": result.metadata.get("exit_code", 0),
    })
}
```

The model needs to see BOTH success and failure clearly to decide next steps.

#### 12A-4. Streaming Tool Call Accumulation (P0)

Models stream tool calls in chunks. The current accumulation is buggy — chunks with partial JSON get truncated or malformed. Fix:

```python
# Accumulate tool call delta chunks correctly
tool_call_buffers: dict[int, ToolCallDelta] = {}

for chunk in stream:
    if chunk.type == "tool_call_delta":
        idx = chunk.index
        if idx not in tool_call_buffers:
            tool_call_buffers[idx] = ToolCallDelta(index=idx)
        tc = tool_call_buffers[idx]
        if chunk.id:
            tc.id = chunk.id
        if chunk.name:
            tc.name = chunk.name
        if chunk.arguments:
            tc.arguments += chunk.arguments  # APPEND, not replace
```

### Phase 12B: Professional System Prompt (Week 1)

#### 12B-1. Claude Code-Style System Prompt (P0)

Replace the current 20-line prompt with a comprehensive, production-grade prompt:

```python
SYSTEM_PROMPT = """You are Octopus, a professional AI coding assistant.

# Core Rules
1. Use tools to accomplish tasks. NEVER describe what you would do — DO IT.
2. When a tool succeeds, move on. Do NOT retry successful operations.
3. When a tool fails, diagnose the error before trying a DIFFERENT approach.
4. Read files before editing them. Understand the code before changing it.
5. One write per file. Use edit_file for subsequent changes.

# File Operations
- CREATE a file: use write_file with path + full content
- MODIFY a file: use edit_file with old_string + new_string (precise)
- DELETE a file: use shell with 'rm filename'
- READ a file: use read_file with path
- MOVE/RENAME: use shell with 'mv old new'

# Writing Code
- Think through the full implementation before writing
- Write complete, working code — no placeholders or TODOs
- Include imports, error handling, and comments where appropriate
- Test the code after writing it

# Shell Commands
- Use shell for: git, npm, pip, ls, mkdir, rm, mv, cp, cat, grep, find
- Use shell for running tests and build commands
- Always check exit codes — non-zero means failure

# Response Style
- After tool execution, describe what was done and the result
- Be concise. Lead with the answer, not the reasoning
- When referencing code, include file:line for navigation
- If you can say it in one sentence, don't use three

# Limits
- You have a maximum of 50 tool-calling turns per user message
- Do not retry the same operation more than twice
- If stuck after 3 attempts, explain the problem to the user"""
```

### Phase 12C: Edit Tool Improvements (Week 1-2)

#### 12C-1. Robust edit_file Implementation (P0)

claude-code's `edit_file` is the primary code modification tool. It uses exact string matching with fuzzy fallback:

```python
class EditFileTool:
    async def execute(self, args, ctx):
        path = args["path"]
        old_string = args["old_string"]
        new_string = args["new_string"]

        content = read_file(path)

        # Exact match
        if old_string in content:
            new_content = content.replace(old_string, new_string, 1)
            write_file(path, new_content)
            return success(f"Edited {path}")

        # Fuzzy match: try stripped version
        old_stripped = old_string.strip()
        if old_stripped in content:
            new_content = content.replace(old_stripped, new_string, 1)
            write_file(path, new_content)
            return success(f"Edited {path} (stripped match)")

        # Line-based match: try each line
        old_lines = old_string.strip().split("\n")
        for i in range(len(content.split("\n"))):
            window = "\n".join(content.split("\n")[i:i+len(old_lines)])
            if window.strip() == old_string.strip():
                # Found at line i
                ...

        return error(f"Could not find old_string in {path}")
```

#### 12C-2. Write File with Overwrite Protection (P1)

```python
class WriteFileTool:
    async def execute(self, args, ctx):
        path = args["path"]
        content = args["content"]

        # If file exists, warn but allow
        if os.path.exists(path):
            existing = read_file(path)
            if existing == content:
                return success(f"File {path} already has this content")
            # File exists with different content — overwrite

        write_file(path, content)
        return success(f"Wrote {path} ({len(content)} bytes)")
```

### Phase 12D: Integration Testing for Tool Pipeline (Week 2)

#### 12D-1. Tool Pipeline E2E Tests (P0)

```python
# tests/integration/test_tool_pipeline_e2e.py

async def test_write_and_read_roundtrip():
    """Write a file, read it back, verify content matches."""
    ...

async def test_edit_file_exact_match():
    """Edit a file with exact old_string match."""
    ...

async def test_edit_file_fuzzy_match():
    """Edit a file with whitespace differences."""
    ...

async def test_dedup_prevents_duplicate_writes():
    """Same content + same path = only one write executes."""
    ...

async def test_dedup_cross_tool():
    """write_file + shell cat to same file = only first executes."""
    ...

async def test_max_turns_enforced():
    """Agent stops after 50 tool-calling turns."""
    ...

async def test_tool_result_feedback():
    """Model receives tool results and responds appropriately."""
    ...
```

### Phase 12E: Verification & Acceptance (Week 2)

#### 12E-1. Manual Test Scenarios (P0)

Each scenario must complete in <10 tool calls with correct results:

| # | Scenario | Expected |
|---|----------|----------|
| 1 | "Write a Python hello world to hello.py" | 1 write_file call, file contains correct code |
| 2 | "Create an HTML love letter page" | 1 write_file call, file opens in browser correctly |
| 3 | "Fix the typo in src/main.py: 'improt' → 'import'" | 1 read_file + 1 edit_file, typo fixed |
| 4 | "List all Python files and count lines" | Shell calls, results displayed |
| 5 | "Create a project with 3 files" | 3 write calls, no duplicates |
| 6 | "Read config.py and explain what it does" | 1 read_file, explanation follows |
| 7 | "Run pytest and fix any failures" | Shell + edit, tests pass |

#### 12E-2. Quality Gates

- [ ] No file ever written to more than once per user request
- [ ] No tool retried more than twice for the same operation  
- [ ] Turn count visible in status bar
- [ ] Model responses include actual file paths and line counts
- [ ] Error messages are clear and actionable

---

## Implementation Roadmap

| Day | Task | Effort |
|-----|------|--------|
| 1-2 | 12A: Robust dedup, turn limits, tool result feedback, stream accumulation fix | ~300 lines |
| 2-3 | 12B: Professional system prompt, edit tool robustness, overwrite protection | ~200 lines |
| 3-4 | 12C: Integration tests for tool pipeline | ~300 lines |
| 4-5 | 12D: Manual scenario testing, fix edge cases, polish | ~200 lines |
| **Total** | | **~1,000 lines** |

---

## Success Criteria

After Phase 12, Octopus must:

1. Complete "write an HTML love letter page" in **1 tool call** (not 10+)
2. Never make the same write/edit/shell call twice
3. Stop after 50 tool-calling turns (never loop forever)
4. Show clear success/failure in tool results
5. Use edit_file for modifications, write_file for new files
6. Read files before editing them
7. Diagnose errors and try DIFFERENT approaches on failure
8. Describe results concisely after tool execution

### Measurable Targets

| Metric | Current | Target |
|--------|---------|--------|
| Tool calls per "write file" request | 10+ | 1-2 |
| Duplicate tool calls | Common | Never |
| Infinite loops | Frequent | Impossible (50 turn cap) |
| Successful file writes | ~30% | >95% |
| Test coverage (tool pipeline) | ~65% | >85% |
