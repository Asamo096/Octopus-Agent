# Phase 6: CLI UI Polish

> Generated: 2026-07-26
> Reference: ~/claude-code (TypeScript, Anthropic internal)
> Goal: Polish CLI UI to match claude-code's terminal UX quality

---

## Executive Summary

Phase 5 completed the core functionality (skills, budget, workers, response handling). Phase 6 focuses on **UI polish** — making the CLI feel as polished as claude-code's terminal experience. These are quality-of-life improvements that don't add new capabilities but dramatically improve usability.

### Patterns to Adopt

| # | Pattern | Source | Effort | Priority |
|---|---------|--------|--------|----------|
| 1 | Spinner with activity description | `Spinner.tsx` | ~100 lines | P0 |
| 2 | Token warning bar | `TokenWarning.tsx` | ~80 lines | P0 |
| 3 | Diff preview for file edits | `diff/DiffDetailView.tsx` | ~150 lines | P0 |
| 4 | Tool result rendering polish | `MessageResponse.tsx` | ~100 lines | P1 |
| 5 | Compact summary display | `CompactSummary.tsx` | ~80 lines | P1 |
| 6 | Context visualization grid | `ContextVisualization.tsx` | ~120 lines | P1 |
| 7 | Message timestamps | `MessageTimestamp.tsx` | ~30 lines | P2 |
| 8 | Session title generation | `sessionTitle.ts` | ~60 lines | P2 |
| 9 | Tool use summary (collapsed) | `ToolUseLoader.tsx` | ~80 lines | P2 |
| 10 | Effort/thinking indicator | `EffortIndicator.ts` | ~40 lines | P2 |

**Total estimated effort:** ~840 lines

---

## Pattern 1: Spinner with Activity Description

**Source:** `~/claude-code/src/components/Spinner.tsx`

**What claude-code does:**
- Shows what the model is currently doing: "Reading src/foo.ts", "Running tests", "Searching for pattern"
- Activity description comes from `getActivityDescription()` on each tool
- Spinner updates in real-time as tool execution progresses
- Uses animated spinner characters (dots, line, etc.)

**What Octopus has now:**
- Static "Thinking..." message before first token
- No activity description during tool execution

**Implementation:**

```python
# src/octopus/cli_ui.py — extend ThinkingSpinner

class ThinkingSpinner:
    """Animated spinner with activity description."""

    def __init__(self, message: str = "Thinking") -> None:
        self.message = message
        self._start_time = 0.0
        self._current_activity: str | None = None
        self._frames = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
        self._frame_index = 0

    def update_activity(self, activity: str) -> None:
        """Update the activity description (e.g., 'Reading src/main.py')."""
        self._current_activity = activity

    def __enter__(self) -> ThinkingSpinner:
        self._start_time = time.monotonic()
        return self

    def tick(self) -> None:
        """Advance spinner frame and redraw."""
        frame = self._frames[self._frame_index % len(self._frames)]
        self._frame_index += 1
        desc = self._current_activity or self.message
        console.print(f"\r[frame]{frame}[/] [dim]{desc}[/]", end="", highlight=False)

    def __exit__(self, *args: object) -> None:
        # Clear spinner line
        console.print(f"\r{' ' * 60}\r", end="", highlight=False)
```

**Wire into tool execution:**

```python
# src/octopus/loop/engine.py — yield activity events

class StreamEventType(StrEnum):
    # ... existing ...
    ACTIVITY = "activity"  # Tool activity description

# In tool execution:
yield StreamEvent(
    type=StreamEventType.ACTIVITY,
    text=f"{tool_name}: {args.get('path', args.get('command', ''))[:50]}",
)
```

**Activity descriptions per tool:**

```python
# src/octopus/tools/base.py — add to Tool protocol

def get_activity_description(self, **kwargs) -> str | None:
    """Human-readable activity for spinner."""
    return None

# Example implementations:
# read_file -> "Reading src/main.py"
# shell -> "Running ls -la"
# grep -> "Searching for pattern"
# write_file -> "Writing src/main.py"
```

**Effort:** ~100 lines | **Priority:** P0

---

## Pattern 2: Token Warning Bar

**Source:** `~/claude-code/src/components/TokenWarning.tsx`

**What claude-code does:**
- Shows warning when approaching context limit: "Context: 85% full (170k/200k tokens)"
- Different colors based on usage: green (<50%), yellow (50-80%), red (>80%)
- Suggests `/compact` when near limit
- Updates in real-time after each turn

**What Octopus has now:**
- No token usage warning
- `/tokens` command shows estimate but no visual indicator

**Implementation:**

```python
# src/octopus/cli_ui.py — add token warning

@dataclass
class TokenWarning:
    """Token usage warning display."""
    current_tokens: int
    max_tokens: int
    threshold_warn: float = 0.75
    threshold_critical: float = 0.90

    @property
    def percentage(self) -> float:
        return self.current_tokens / self.max_tokens if self.max_tokens > 0 else 0

    @property
    def level(self) -> str:
        if self.percentage >= self.threshold_critical:
            return "critical"
        if self.percentage >= self.threshold_warn:
            return "warning"
        return "ok"

    def render(self) -> None:
        """Render token warning bar."""
        if self.percentage < 0.5:
            return  # Don't show when usage is low

        pct = int(self.percentage * 100)
        current = _format_token_count(self.current_tokens)
        max_str = _format_token_count(self.max_tokens)

        if self.level == "critical":
            console.print(
                f"[error]Context: {pct}% full ({current}/{max_str} tokens). "
                f"Consider /compact.[/]"
            )
        elif self.level == "warning":
            console.print(
                f"[warning]Context: {pct}% full ({current}/{max_str} tokens)[/]"
            )
```

**Wire into turn completion:**

```python
# After each turn in run_interactive_async:
tokens = conversation.estimate_tokens()
max_tokens = 200_000  # Default context window
warning = TokenWarning(tokens, max_tokens)
warning.render()
```

**Effort:** ~80 lines | **Priority:** P0

---

## Pattern 3: Diff Preview for File Edits

**Source:** `~/claude-code/src/components/diff/DiffDetailView.tsx`

**What claude-code does:**
- Shows colored diff when editing files
- Green for additions, red for deletions
- Line numbers on both sides
- Context lines around changes

**What Octopus has now:**
- Edit tool shows "OK (1.2s)" with no preview
- No visual diff display

**Implementation:**

```python
# src/octopus/cli_ui.py — add diff rendering

def render_diff(old_text: str, new_text: str, file_path: str) -> None:
    """Render a colored diff between old and new text."""
    import difflib

    old_lines = old_text.splitlines(keepends=True)
    new_lines = new_text.splitlines(keepends=True)

    diff = list(difflib.unified_diff(
        old_lines,
        new_lines,
        fromfile=f"a/{file_path}",
        tofile=f"b/{file_path}",
        lineterm="",
    ))

    if not diff:
        return

    for line in diff[:30]:  # Limit to 30 lines
        if line.startswith("+++") or line.startswith("---"):
            console.print(f"[bold]{line}[/]")
        elif line.startswith("+"):
            console.print(f"[green]{line}[/]")
        elif line.startswith("-"):
            console.print(f"[red]{line}[/]")
        elif line.startswith("@@"):
            console.print(f"[cyan]{line}[/]")
        else:
            console.print(f"[dim]{line}[/]")

    if len(diff) > 30:
        console.print(f"[dim]... +{len(diff) - 30} more lines[/]")
```

**Wire into edit tool rendering:**

```python
# In _render_tool_output for edit tools:
if lower in ("edit", "edit_file", "file_edit"):
    # Try to get old content from cache
    old_content = ""  # TODO: get from file_cache
    new_content = output
    render_diff(old_content, new_content, file_path)
```

**Effort:** ~150 lines | **Priority:** P0

---

## Pattern 4: Tool Result Rendering Polish

**Source:** `~/claude-code/src/components/MessageResponse.tsx`

**What claude-code does:**
- Different rendering per tool type (already partially done in Octopus)
- Syntax highlighting for code files
- Collapsible long output
- Error display with stack trace formatting

**What Octopus has now:**
- Basic panel rendering per tool type
- No syntax highlighting for read results
- No collapsible output

**Implementation:**

```python
# src/octopus/cli_ui.py — enhance _render_tool_output

def _render_tool_output(tool_name: str, output: str, args: dict[str, Any] | None = None) -> None:
    """Enhanced tool output rendering."""
    from rich.syntax import Syntax
    from rich.panel import Panel

    if not output or not output.strip():
        return

    lower = tool_name.lower()
    args = args or {}

    # Read/file_read: syntax highlight
    if lower in ("read", "read_file", "file_read"):
        file_path = str(args.get("path", args.get("file_path", "")))
        ext = file_path.rsplit(".", 1)[-1] if "." in file_path else ""

        # Syntax highlighting map
        lexer_map = {
            "py": "python", "js": "javascript", "ts": "typescript",
            "rs": "rust", "go": "go", "rb": "ruby", "java": "java",
            "c": "c", "cpp": "cpp", "h": "c", "json": "json",
            "yaml": "yaml", "yml": "yaml", "toml": "toml",
            "sh": "bash", "bash": "bash", "html": "html", "css": "css",
        }
        lexer = lexer_map.get(ext)

        if lexer and len(output) < 5000:
            # Syntax highlighted
            console.print(Syntax(output, lexer, theme="monokai", line_numbers=True))
        else:
            # Plain panel
            console.print(Panel(output[:2000], title=file_path, border_style="dim"))
        return

    # Shell: panel with command
    if lower in ("shell", "bash", "execute_command"):
        cmd = args.get("command", "")
        title = f"$ {cmd[:80]}" if cmd else "Shell"
        console.print(Panel(output[:2000], title=title, border_style="dim"))
        return

    # Edit: diff view
    if lower in ("edit", "edit_file", "file_edit"):
        file_path = str(args.get("path", args.get("file_path", "")))
        console.print(Panel(output[:2000], title=f"Edit: {file_path}", border_style="green"))
        return

    # Grep: results panel
    if lower in ("grep", "search"):
        console.print(Panel(output[:2000], title="Search results", border_style="cyan"))
        return

    # Default: truncated
    lines = output.split("\n")
    if len(lines) > 15:
        display = "\n".join(lines[:12]) + f"\n... ({len(lines) - 12} more lines)"
    else:
        display = output
    console.print(f"    [dim]{display}[/dim]")
```

**Effort:** ~100 lines | **Priority:** P1

---

## Pattern 5: Compact Summary Display

**Source:** `~/claude-code/src/components/CompactSummary.tsx`

**What claude-code does:**
- After compaction, shows what was summarized
- "Summarized 45 messages up to this point"
- Shows context that was preserved: 'Context: "working on auth module"'
- Displays compact metadata

**What Octopus has now:**
- Basic "[Compacted: X -> Y tokens via strategy]" status message
- No summary of what was kept

**Implementation:**

```python
# src/octopus/cli_ui.py — add compact summary

def print_compact_summary(
    messages_before: int,
    messages_after: int,
    tokens_before: int,
    tokens_after: int,
    strategy: str,
    preserved_context: str | None = None,
) -> None:
    """Display compact summary after compaction."""
    saved = tokens_before - tokens_after
    pct = int((saved / tokens_before) * 100) if tokens_before > 0 else 0

    console.print()
    console.print("[accent]Conversation compacted[/]")
    console.print(f"  Messages: {messages_before} -> {messages_after}")
    console.print(f"  Tokens: {_format_token_count(tokens_before)} -> {_format_token_count(tokens_after)} ({pct}% saved)")
    console.print(f"  Strategy: {strategy}")

    if preserved_context:
        console.print(f'  Context: "{preserved_context}"')
    console.print()
```

**Effort:** ~80 lines | **Priority:** P1

---

## Pattern 6: Context Visualization Grid

**Source:** `~/claude-code/src/components/ContextVisualization.tsx`

**What claude-code does:**
- Colored grid showing context usage breakdown
- Categories: system prompt, messages, tool results, buffer
- Progress bar with percentage
- Suggestions for reducing context

**What Octopus has now:**
- `/context` command shows basic text breakdown
- No visual grid

**Implementation:**

```python
# src/octopus/cli_ui.py — enhance /context display

def print_context_grid(
    total_tokens: int,
    max_tokens: int,
    breakdown: dict[str, int],
) -> None:
    """Display context usage as colored grid."""
    from rich.progress import BarColumn, Progress, TextColumn
    from rich.table import Table

    pct = total_tokens / max_tokens if max_tokens > 0 else 0
    bar_width = 30
    filled = int(pct * bar_width)
    empty = bar_width - filled

    # Color based on usage
    if pct >= 0.9:
        color = "red"
    elif pct >= 0.75:
        color = "yellow"
    else:
        color = "green"

    # Progress bar
    bar = f"[{color}]{'█' * filled}[/{color}][dim]{'░' * empty}[/dim]"
    console.print(f"\n  Context: {bar} {int(pct * 100)}% ({_format_token_count(total_tokens)}/{_format_token_count(max_tokens)})")
    console.print()

    # Breakdown table
    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column("Category", style="dim")
    table.add_column("Tokens", justify="right")
    table.add_column("Percentage", justify="right")
    table.add_column("Bar")

    for category, tokens in breakdown.items():
        cat_pct = tokens / total_tokens if total_tokens > 0 else 0
        cat_filled = int(cat_pct * 20)
        cat_bar = f"[{color}]{'█' * cat_filled}[/{color}][dim]{'░' * (20 - cat_filled)}[/dim]"
        table.add_row(
            category,
            _format_token_count(tokens),
            f"{int(cat_pct * 100)}%",
            cat_bar,
        )

    console.print(table)
    console.print()
```

**Effort:** ~120 lines | **Priority:** P1

---

## Pattern 7: Message Timestamps

**Source:** `~/claude-code/src/components/MessageTimestamp.tsx`

**What claude-code does:**
- Shows timestamps on messages: "12:34 PM"
- Relative time for recent messages
- Absolute time for older messages

**What Octopus has now:**
- No timestamps on messages

**Implementation:**

```python
# src/octopus/cli_runtime.py — add timestamps to messages

from datetime import datetime

def _format_timestamp(dt: datetime | None = None) -> str:
    """Format timestamp for display."""
    if dt is None:
        dt = datetime.now()
    return dt.strftime("%H:%M")

# In message rendering:
timestamp = _format_timestamp()
console.print(f"[dim]{timestamp}[/dim] ", end="")
console.print(f"[bold]>[/] {user_input}")
```

**Effort:** ~30 lines | **Priority:** P2

---

## Pattern 8: Session Title Generation

**Source:** `~/claude-code/src/utils/sessionTitle.ts`

**What claude-code does:**
- Auto-generates session title from first user message
- Shows in banner and session list
- Truncated to fit display

**What Octopus has now:**
- Only session ID shown
- No session title

**Implementation:**

```python
# src/octopus/loop/context.py — add title generation

def generate_session_title(first_message: str, max_len: int = 50) -> str:
    """Generate session title from first user message."""
    # Take first line, strip markdown
    title = first_message.split("\n")[0].strip()
    # Remove markdown formatting
    title = title.replace("*", "").replace("_", "").replace("`", "")
    # Truncate
    if len(title) > max_len:
        title = title[:max_len - 3] + "..."
    return title or "New session"
```

**Effort:** ~60 lines | **Priority:** P2

---

## Pattern 9: Tool Use Summary (Collapsed)

**Source:** `~/claude-code/src/components/ToolUseLoader.tsx`

**What claude-code does:**
- Groups multiple tool calls into a summary
- "3 tool uses (2 read, 1 grep)"
- Collapsed by default, expandable

**What Octopus has now:**
- Each tool call shown individually

**Implementation:**

```python
# src/octopus/cli_ui.py — add tool summary

def print_tool_summary(tool_calls: list[ToolCallDisplay]) -> None:
    """Print collapsed summary of multiple tool calls."""
    if len(tool_calls) <= 1:
        return

    # Group by tool name
    counts: dict[str, int] = {}
    for tc in tool_calls:
        counts[tc.name] = counts.get(tc.name, 0) + 1

    # Format: "3 tool uses (2 read, 1 grep)"
    total = len(tool_calls)
    parts = [f"{count} {name}" for name, count in counts.items()]
    summary = f"{total} tool uses ({', '.join(parts)})"

    console.print(f"[dim]{summary}[/dim]")
```

**Effort:** ~80 lines | **Priority:** P2

---

## Pattern 10: Effort/Thinking Indicator

**Source:** `~/claude-code/src/components/EffortIndicator.ts`

**What claude-code does:**
- Shows thinking effort level: "[thinking: high]"
- Different levels: low, medium, high
- Displayed during model thinking

**What Octopus has now:**
- No effort indicator

**Implementation:**

```python
# src/octopus/cli_ui.py — add effort indicator

def print_effort_indicator(effort: str) -> None:
    """Display thinking effort level."""
    effort_colors = {
        "low": "dim",
        "medium": "yellow",
        "high": "cyan",
        "max": "magenta",
    }
    color = effort_colors.get(effort, "dim")
    console.print(f"[{color}][thinking: {effort}][/{color}]", end=" ")
```

**Effort:** ~40 lines | **Priority:** P2

---

## Implementation Roadmap

### Phase 6A: Critical UX (Weeks 27-28)

| Week | Tasks | Effort |
|------|-------|--------|
| 27 | Pattern 1 (Spinner) + Pattern 2 (Token warning) | ~180 lines |
| 28 | Pattern 3 (Diff preview) + Pattern 4 (Tool rendering) | ~250 lines |

**Deliverable:** Animated spinner with activity, token warnings, diff previews for edits.

### Phase 6B: Polish (Weeks 29-30)

| Week | Tasks | Effort |
|------|-------|--------|
| 29 | Pattern 5 (Compact summary) + Pattern 6 (Context grid) | ~200 lines |
| 30 | Patterns 7-10 (Timestamps, titles, summaries, effort) | ~210 lines |

**Deliverable:** Polished UI with timestamps, session titles, tool summaries.

---

## Dependencies

```
Pattern 1 (Spinner) ──→ needs StreamEventType.ACTIVITY from engine
Pattern 3 (Diff) ──→ needs file_cache for old content
Pattern 5 (Compact) ──→ needs compaction metadata
Pattern 6 (Context) ──→ needs token estimation
```

---

## Success Criteria

After Phase 6, Octopus CLI should:

1. Show animated spinner with activity description during tool execution
2. Warn when approaching context limit (75% yellow, 90% red)
3. Display colored diff preview when editing files
4. Render tool output with syntax highlighting
5. Show compact summary with preserved context
6. Display context usage as colored grid with breakdown
7. Show timestamps on messages
8. Auto-generate session titles
9. Collapse multiple tool calls into summary
10. Display thinking effort level
