# Phase 5: claude-code Reusable Patterns Integration

> Generated: 2026-07-25
> Reference: ~/claude-code (TypeScript, Anthropic internal)
> Goal: Adopt proven patterns from claude-code into Octopus-Agent's Python architecture

---

## Executive Summary

claude-code is Anthropic's production CLI agent (TypeScript/Bun). While not a harness-governed system, it has battle-tested patterns for compaction, memory, tools, cost tracking, and session management. Phase 5 selectively integrates these patterns into Octopus-Agent.

### Patterns to Adopt

| # | Pattern | Source | Effort | Priority |
|---|---------|--------|--------|----------|
| 1 | Time-based microcompact | `services/compact/compact.ts` | ~150 lines | P0 |
| 2 | Cost tracking | `cost-tracker.ts` | ~200 lines | P0 |
| 3 | Tool enhancements | `Tool.ts` | ~250 lines | P0 |
| 4 | Skills system | `skills/loadSkillsDir.ts` | ~400 lines | P1 |
| 5 | File state cache | `utils/fileStateCache.ts` | ~150 lines | P1 |
| 6 | Session memory compaction | `services/compact/sessionMemoryCompact.ts` | ~200 lines | P1 |
| 7 | QueryEngine budget enforcement | `QueryEngine.ts` | ~150 lines | P1 |
| 8 | Compact boundary messages | `services/compact/compact.ts` | ~100 lines | P2 |
| 9 | Coordinator worker agents | `coordinator/workerAgent.ts` | ~300 lines | P2 |
| 10 | Reactive compact improvements | `services/compact/reactiveCompact.ts` | ~100 lines | P2 |

**Total estimated effort:** ~2,000 lines across 10 patterns.

---

## Pattern 1: Time-Based Microcompact

**Source:** `~/claude-code/src/services/compact/compact.ts` lines 41-50, 80+

**What claude-code does:**
- Maintains a `COMPACTABLE_TOOLS` set (Read, Bash, Grep, Glob, WebSearch, WebFetch, Edit, Write)
- Microcompact clears old tool result content to `[Old tool result content cleared]`
- Time-based variant clears results older than a configurable age threshold
- Preserves message structure (tool_use_id, type) but removes content payload
- Reduces token count without breaking conversation flow

**What Octopus has now:**
- `CompactionEngine.microcompact()` clears tool results older than N turns
- No time-based variant (turns != time; a slow turn may span minutes)

**Implementation:**

```python
# src/octopus/loop/compaction.py — extend existing

COMPACTABLE_TOOLS = {
    "read_file",
    "write_file",
    "edit_file",
    "shell",
    "glob",
    "grep",
    "web_search",
    "web_fetch",
}


@dataclass
class MicrocompactConfig:
    max_age_seconds: int = 600  # Clear results older than 10 min
    max_turns: int = 5  # Clear results older than 5 turns
    preserve_last_n: int = 2  # Always keep last N tool results per type
    cleared_marker: str = "[Previous tool result cleared]"


class CompactionEngine:
    # ... existing methods ...

    def time_based_microcompact(
        self,
        messages: list[Message],
        config: MicrocompactConfig | None = None,
    ) -> list[Message]:
        """Clear tool results based on age AND turn distance.

        Unlike turn-based microcompact, this considers wall-clock time
        so slow turns don't accumulate stale results.
        """
        if config is None:
            config = MicrocompactConfig()

        now = datetime.now(UTC)
        cleared_count = 0

        # Track per-tool-type occurrence for preserve_last_n
        tool_occurrences: dict[str, list[int]] = {}

        for i, msg in enumerate(messages):
            if msg.role != "assistant" or not msg.tool_calls:
                continue
            for tc in msg.tool_calls:
                tool_name = tc.function.name
                if tool_name not in COMPACTABLE_TOOLS:
                    continue

                # Track occurrences
                if tool_name not in tool_occurrences:
                    tool_occurrences[tool_name] = []
                tool_occurrences[tool_name].append(i)

        # Find indices to clear
        indices_to_clear: set[int] = set()
        for tool_name, indices in tool_occurrences.items():
            # Keep last N occurrences
            to_check = (
                indices[: -config.preserve_last_n]
                if config.preserve_last_n
                else indices
            )
            for idx in to_check:
                msg = messages[idx]
                msg_time = msg.timestamp or now
                age_seconds = (now - msg_time).total_seconds()
                turn_distance = len(messages) - idx

                if (
                    age_seconds > config.max_age_seconds
                    or turn_distance > config.max_turns
                ):
                    # Clear tool results in this message
                    for tc in msg.tool_calls:
                        if tc.function.name in COMPACTABLE_TOOLS:
                            # Find matching tool result and clear it
                            self._clear_tool_result(messages, idx, tc.id)
                            cleared_count += 1

        if cleared_count > 0:
            log.info("time_based_microcompact", cleared=cleared_count)

        return messages

    def _clear_tool_result(
        self, messages: list[Message], assistant_idx: int, tool_call_id: str
    ) -> None:
        """Clear content of a tool result message while preserving structure."""
        # Find the tool_result message after the assistant message
        for i in range(assistant_idx + 1, len(messages)):
            msg = messages[i]
            if msg.role == "tool" and msg.tool_call_id == tool_call_id:
                msg.content = MicrocompactConfig().cleared_marker
                break
```

**Config additions:**

```python
# src/octopus/config/schema.py — add to OctopusSettings
microcompact_max_age_seconds: int = 600
microcompact_max_turns: int = 5
microcompact_preserve_last_n: int = 2
```

**Effort:** ~150 lines | **Priority:** P0

---

## Pattern 2: Cost Tracking

**Source:** `~/claude-code/src/cost-tracker.ts`

**What claude-code does:**
- Tracks per-model usage: input_tokens, output_tokens, cache_read_tokens, cache_creation_tokens
- Calculates total cost in USD using per-model pricing
- `getModelUsage()` returns per-model breakdown
- `getTotalCost()` returns aggregate cost
- Exposed in result messages for SDK consumers

**What Octopus has now:**
- No cost tracking at all. Users have no visibility into API spend.

**Implementation:**

```python
# src/octopus/loop/cost.py — NEW

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass


# Pricing per 1M tokens (input / output)
MODEL_PRICING: dict[str, tuple[float, float]] = {
    "claude-sonnet-4-20250514": (3.0, 15.0),
    "claude-opus-4-20250514": (15.0, 75.0),
    "claude-haiku-4-5-20251001": (0.80, 4.0),
    "gpt-4o": (2.50, 10.0),
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4-turbo": (10.0, 30.0),
    "o1": (15.0, 60.0),
    "o3-mini": (1.10, 4.40),
    "deepseek-chat": (0.14, 0.28),
    "deepseek-reasoner": (0.55, 2.19),
}


@dataclass
class TokenUsage:
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_creation_tokens: int = 0


@dataclass
class ModelUsage:
    model: str
    usage: TokenUsage = field(default_factory=TokenUsage)
    request_count: int = 0
    total_cost_usd: float = 0.0


@dataclass
class CostTracker:
    """Track API costs across a session."""

    model_usage: dict[str, ModelUsage] = field(default_factory=dict)
    _pricing: dict[str, tuple[float, float]] = field(
        default_factory=lambda: MODEL_PRICING
    )

    def record_usage(self, model: str, usage: TokenUsage) -> None:
        """Record token usage for a model and calculate cost."""
        if model not in self.model_usage:
            self.model_usage[model] = ModelUsage(model=model)

        mu = self.model_usage[model]
        mu.usage.input_tokens += usage.input_tokens
        mu.usage.output_tokens += usage.output_tokens
        mu.usage.cache_read_tokens += usage.cache_read_tokens
        mu.usage.cache_creation_tokens += usage.cache_creation_tokens
        mu.request_count += 1

        # Calculate cost
        cost = self._calculate_cost(model, usage)
        mu.total_cost_usd += cost

    def _calculate_cost(self, model: str, usage: TokenUsage) -> float:
        """Calculate USD cost for a single request."""
        # Find pricing (try exact match, then prefix match)
        input_price, output_price = self._get_pricing(model)

        # Cache reads are 90% cheaper
        cache_read_price = input_price * 0.1

        cost = (
            (usage.input_tokens / 1_000_000) * input_price
            + (usage.output_tokens / 1_000_000) * output_price
            + (usage.cache_read_tokens / 1_000_000) * cache_read_price
            + (usage.cache_creation_tokens / 1_000_000) * input_price
        )
        return cost

    def _get_pricing(self, model: str) -> tuple[float, float]:
        """Get pricing for a model, with prefix fallback."""
        if model in self._pricing:
            return self._pricing[model]
        # Try prefix match (e.g., "claude-sonnet-4-20250514" matches "claude-sonnet-4")
        for prefix, pricing in self._pricing.items():
            if model.startswith(prefix.rsplit("-", 1)[0]):
                return pricing
        # Unknown model: assume sonnet pricing
        return self._pricing.get("claude-sonnet-4-20250514", (3.0, 15.0))

    def get_total_cost(self) -> float:
        return sum(mu.total_cost_usd for mu in self.model_usage.values())

    def get_model_breakdown(self) -> list[ModelUsage]:
        return sorted(
            self.model_usage.values(),
            key=lambda mu: mu.total_cost_usd,
            reverse=True,
        )

    def get_summary(self) -> str:
        total = self.get_total_cost()
        lines = [f"Total cost: ${total:.4f}"]
        for mu in self.get_model_breakdown():
            lines.append(
                f"  {mu.model}: ${mu.total_cost_usd:.4f} "
                f"({mu.usage.input_tokens} in / {mu.usage.output_tokens} out, "
                f"{mu.request_count} requests)"
            )
        return "\n".join(lines)
```

**Wire into AgentLoop:**

```python
# src/octopus/loop/engine.py — modify run_turn()

from octopus.loop.cost import CostTracker, TokenUsage

class AgentLoop:
    def __init__(self, ...):
        # ... existing ...
        self.cost_tracker = CostTracker()

    async def run_turn(self, ...) -> LoopResult:
        # After provider.chat():
        usage = TokenUsage(
            input_tokens=response.usage.get("prompt_tokens", 0),
            output_tokens=response.usage.get("completion_tokens", 0),
            cache_read_tokens=response.usage.get("prompt_tokens_details", {}).get("cached_tokens", 0),
        )
        self.cost_tracker.record_usage(model, usage)

        # In result:
        return LoopResult(
            ...,
            cost_usd=self.cost_tracker.get_total_cost(),
            model_usage=self.cost_tracker.get_model_breakdown(),
        )
```

**CLI display:**

```python
# src/octopus/cli_runtime.py — after each turn
cost = loop.cost_tracker.get_total_cost()
if cost > 0:
    console.print(f"[dim]Cost: ${cost:.4f}[/dim]")
```

**Effort:** ~200 lines | **Priority:** P0

---

## Pattern 3: Tool Enhancements

**Source:** `~/claude-code/src/Tool.ts` (buildTool, TOOL_DEFAULTS)

**What claude-code does:**
- `buildTool()` factory with safe defaults
- `validateInput()` — check input validity before execution
- `checkPermissions()` — tool-specific permission logic
- `isReadOnly()` — whether tool modifies state
- `isDestructive()` — whether tool performs irreversible operations
- `isConcurrencySafe()` — whether tool can run in parallel
- `maxResultSizeChars` — result budget (persist to disk if exceeded)
- `interruptBehavior` — 'cancel' vs 'block' on user interrupt
- `isSearchOrReadCommand()` — UI collapse grouping

**What Octopus has now:**
- `Tool` has `requires_permission`, `requires_shell_access`, `category`
- No validation, no destructiveness classification, no result size limits

**Implementation:**

```python
# src/octopus/tools/base.py — extend existing Tool class


class ToolInterruptBehavior(str, Enum):
    CANCEL = "cancel"  # Stop and discard result
    BLOCK = "block"  # Keep running, queue new input


class Tool(Protocol):
    """Enhanced tool protocol."""

    # Existing
    name: str
    description: str
    parameters: dict[str, Any]
    category: str
    requires_permission: bool
    requires_shell_access: bool

    # New from claude-code patterns
    is_read_only: bool = False
    is_destructive: bool = False
    is_concurrency_safe: bool = False
    max_result_size_chars: int = 100_000  # 100KB default
    interrupt_behavior: ToolInterruptBehavior = ToolInterruptBehavior.BLOCK

    # Methods
    async def validate_input(self, **kwargs) -> ValidationResult:
        """Validate input before execution. Override for tool-specific checks."""
        return ValidationResult(valid=True)

    async def call(self, context: ToolContext, **kwargs) -> ToolResult: ...

    def get_activity_description(self, **kwargs) -> str | None:
        """Human-readable activity for spinner. E.g., 'Reading src/foo.py'"""
        return None

    def to_classifier_input(self, **kwargs) -> str:
        """Compact representation for security classifier."""
        return ""


@dataclass
class ValidationResult:
    valid: bool
    error_message: str | None = None
    error_code: int | None = None


@dataclass
class ToolResult:
    output: str
    metadata: dict[str, Any] = field(default_factory=dict)
    truncated: bool = False
    persisted_to: str | None = None  # Path if result exceeded max_result_size_chars
```

**Result size enforcement:**

```python
# src/octopus/tools/base.py — add to tool execution


async def enforce_result_size(result: ToolResult, tool: Tool) -> ToolResult:
    """Persist large results to disk, return preview."""
    if len(result.output) <= tool.max_result_size_chars:
        return result

    # Persist full result to temp file
    import tempfile
    from pathlib import Path

    cache_dir = Path.home() / ".octopus" / "tool_results"
    cache_dir.mkdir(parents=True, exist_ok=True)

    import hashlib

    content_hash = hashlib.sha256(result.output.encode()).hexdigest()[:12]
    persist_path = cache_dir / f"{tool.name}_{content_hash}.txt"

    persist_path.write_text(result.output)

    # Return truncated preview
    preview = result.output[: tool.max_result_size_chars]
    preview += f"\n\n[Result truncated. Full output: {persist_path}]"

    return ToolResult(
        output=preview,
        metadata=result.metadata,
        truncated=True,
        persisted_to=str(persist_path),
    )
```

**Effort:** ~250 lines | **Priority:** P0

---

## Pattern 4: Skills System

**Source:** `~/claude-code/src/skills/loadSkillsDir.ts`

**What claude-code does:**
- Skills are markdown files with YAML frontmatter
- Loaded from: bundled, user config, project, plugins
- Frontmatter defines: name, description, allowed-tools, model, effort, hooks
- `loadSkillsDir()` scans directories, parses frontmatter, builds Command objects
- Skills can use argument substitution (`$ARGUMENTS`)
- Skills have per-skill tool restrictions

**What Octopus has now:**
- `AgentRegistry` with markdown-based agent definitions (name, model, description)
- No skills system

**Implementation:**

```python
# src/octopus/skills/__init__.py
# src/octopus/skills/loader.py — NEW
# src/octopus/skills/schema.py — NEW
# src/octopus/skills/registry.py — NEW

# schema.py
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

import yaml


class SkillSource(str, Enum):
    BUNDLED = "bundled"
    USER = "user"
    PROJECT = "project"
    PLUGIN = "plugin"


@dataclass
class SkillDefinition:
    """A skill loaded from a SKILL.md file."""

    name: str
    description: str
    source: SkillSource
    path: Path

    # From frontmatter
    allowed_tools: list[str] = field(default_factory=list)
    blocked_tools: list[str] = field(default_factory=list)
    model: str | None = None
    effort: str | None = None
    system_prompt_suffix: str | None = None

    # Body (markdown after frontmatter)
    instructions: str = ""

    # Metadata
    argument_names: list[str] = field(default_factory=list)
    hooks: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_file(cls, path: Path, source: SkillSource) -> SkillDefinition | None:
        """Parse a SKILL.md file into a SkillDefinition."""
        try:
            content = path.read_text(encoding="utf-8")
        except OSError:
            return None

        if not content.startswith("---"):
            return None

        # Split frontmatter and body
        parts = content.split("---", 2)
        if len(parts) < 3:
            return None

        try:
            meta = yaml.safe_load(parts[1]) or {}
        except yaml.YAMLError:
            return None

        if not isinstance(meta, dict) or "name" not in meta:
            return None

        body = parts[2].strip()

        # Extract argument names from body ($ARGUMENTS, $1, $2, etc.)
        import re

        arg_names = list(set(re.findall(r"\$(?:ARGUMENTS|\d+)", body)))

        return cls(
            name=meta["name"],
            description=meta.get("description", ""),
            source=source,
            path=path,
            allowed_tools=meta.get("allowed-tools", []),
            blocked_tools=meta.get("blocked-tools", []),
            model=meta.get("model"),
            effort=meta.get("effort"),
            system_prompt_suffix=meta.get("system-prompt"),
            instructions=body,
            argument_names=arg_names,
            hooks=meta.get("hooks", {}),
        )

    def render_instructions(self, arguments: str = "") -> str:
        """Render skill instructions with argument substitution."""
        result = self.instructions
        result = result.replace("$ARGUMENTS", arguments)
        # Replace $1, $2, etc. with split arguments
        parts = arguments.split() if arguments else []
        for i, part in enumerate(parts, 1):
            result = result.replace(f"${i}", part)
        return result


# loader.py
from __future__ import annotations

from pathlib import Path
from typing import Iterator

from octopus.skills.schema import SkillDefinition, SkillSource
from octopus.utils.logging import get_logger

log = get_logger(__name__)

# Directories to scan for skills
SKILL_DIRS = [
    ("bundled", SkillSource.BUNDLED),
    ("user", SkillSource.USER),
    ("project", SkillSource.PROJECT),
]


def discover_skills(
    bundled_dir: Path | None = None,
    user_dir: Path | None = None,
    project_dir: Path | None = None,
) -> list[SkillDefinition]:
    """Discover all skills from standard directories."""
    skills: list[SkillDefinition] = []
    seen_names: set[str] = set()

    search_dirs: list[tuple[Path, SkillSource]] = []

    if bundled_dir and bundled_dir.exists():
        search_dirs.append((bundled_dir, SkillSource.BUNDLED))
    if user_dir and user_dir.exists():
        search_dirs.append((user_dir, SkillSource.USER))
    if project_dir and project_dir.exists():
        search_dirs.append((project_dir, SkillSource.PROJECT))

    for dir_path, source in search_dirs:
        for skill_file in _scan_directory(dir_path):
            skill = SkillDefinition.from_file(skill_file, source)
            if skill is None:
                continue
            if skill.name in seen_names:
                log.warning("duplicate_skill", name=skill.name, path=str(skill_file))
                continue
            seen_names.add(skill.name)
            skills.append(skill)

    return skills


def _scan_directory(directory: Path) -> Iterator[Path]:
    """Recursively find SKILL.md files."""
    for path in directory.rglob("SKILL.md"):
        # Skip hidden directories
        if any(part.startswith(".") for part in path.relative_to(directory).parts):
            continue
        yield path


# registry.py
from __future__ import annotations

from pathlib import Path
from typing import Any

from octopus.skills.loader import discover_skills
from octopus.skills.schema import SkillDefinition, SkillSource


class SkillRegistry:
    """Registry of available skills."""

    def __init__(self) -> None:
        self._skills: dict[str, SkillDefinition] = {}

    def load(
        self,
        bundled_dir: Path | None = None,
        user_dir: Path | None = None,
        project_dir: Path | None = None,
    ) -> None:
        """Load skills from standard directories."""
        for skill in discover_skills(bundled_dir, user_dir, project_dir):
            self._skills[skill.name] = skill

    def get(self, name: str) -> SkillDefinition | None:
        return self._skills.get(name)

    def list_skills(self) -> list[SkillDefinition]:
        return sorted(self._skills.values(), key=lambda s: s.name)

    def to_tool_prompt(self) -> str:
        """Generate tool prompt section listing available skills."""
        if not self._skills:
            return ""
        lines = ["## Available Skills", ""]
        for skill in self.list_skills():
            lines.append(f"- **{skill.name}**: {skill.description}")
        return "\n".join(lines)
```

**Bundled skills:**

```python
# src/octopus/skills/bundled/ — create initial bundled skills

# src/octopus/skills/bundled/review/SKILL.md
"""
---
name: review
description: Perform a thorough code review of the specified files or changes
allowed-tools:
  - read_file
  - glob
  - grep
  - shell
effort: high
---

Review the code changes specified by the user. Focus on:

1. **Correctness**: Logic errors, edge cases, off-by-one bugs
2. **Security**: Input validation, injection, secrets exposure
3. **Performance**: N+1 queries, unnecessary allocations, blocking calls
4. **Readability**: Naming, complexity, documentation

Output a structured review with severity levels: critical, warning, suggestion.

$ARGUMENTS
"""

# src/octopus/skills/bundled/explain/SKILL.md
"""
---
name: explain
description: Explain how a file, function, or concept works
allowed-tools:
  - read_file
  - glob
  - grep
---

Explain the following to the user in clear, concise language.
Adapt detail level to complexity — simple things get brief explanations,
complex architecture gets detailed breakdowns with diagrams.

$ARGUMENTS
"""
```

**Effort:** ~400 lines | **Priority:** P1

---

## Pattern 5: File State Cache

**Source:** `~/claude-code/src/utils/fileStateCache.ts`

**What claude-code does:**
- LRU cache of file contents read during session
- Prevents re-reading unchanged files
- Used for dedup in compaction (skip re-reading files already in context)
- Cloneable for subagent forking

**What Octopus has now:**
- No file read cache. Every `read_file` call hits disk.

**Implementation:**

```python
# src/octopus/utils/file_cache.py — NEW

from __future__ import annotations

import hashlib
import os
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class CachedFile:
    path: str
    content: str
    mtime: float
    size: int
    content_hash: str


class FileStateCache:
    """LRU cache of file contents read during a session.

    Prevents re-reading unchanged files and enables dedup
    in compaction (files already in context don't need re-reading).
    """

    def __init__(self, max_size: int = 200) -> None:
        self._cache: OrderedDict[str, CachedFile] = OrderedDict()
        self._max_size = max_size
        self._hits = 0
        self._misses = 0

    def get(self, path: str) -> CachedFile | None:
        """Get cached file if still valid (exists and mtime unchanged)."""
        abs_path = str(Path(path).resolve())

        cached = self._cache.get(abs_path)
        if cached is None:
            self._misses += 1
            return None

        # Check if file has changed
        try:
            stat = os.stat(abs_path)
        except OSError:
            # File deleted — evict
            self._cache.pop(abs_path, None)
            self._misses += 1
            return None

        if stat.st_mtime != cached.mtime or stat.st_size != cached.size:
            # File changed — evict
            self._cache.pop(abs_path, None)
            self._misses += 1
            return None

        # Move to end (most recently used)
        self._cache.move_to_end(abs_path)
        self._hits += 1
        return cached

    def put(self, path: str, content: str) -> CachedFile:
        """Cache a file's content."""
        abs_path = str(Path(path).resolve())

        try:
            stat = os.stat(abs_path)
            mtime = stat.st_mtime
            size = stat.st_size
        except OSError:
            mtime = 0.0
            size = len(content)

        content_hash = hashlib.sha256(content.encode()).hexdigest()[:16]

        entry = CachedFile(
            path=abs_path,
            content=content,
            mtime=mtime,
            size=size,
            content_hash=content_hash,
        )

        self._cache[abs_path] = entry
        self._cache.move_to_end(abs_path)

        # Evict oldest if over capacity
        while len(self._cache) > self._max_size:
            self._cache.popitem(last=False)

        return entry

    def invalidate(self, path: str) -> None:
        """Remove a file from cache."""
        abs_path = str(Path(path).resolve())
        self._cache.pop(abs_path, None)

    def clear(self) -> None:
        self._cache.clear()
        self._hits = 0
        self._misses = 0

    @property
    def stats(self) -> dict[str, Any]:
        total = self._hits + self._misses
        return {
            "size": len(self._cache),
            "max_size": self._max_size,
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": self._hits / total if total > 0 else 0.0,
        }
```

**Wire into tools:**

```python
# src/octopus/tools/filesystem.py — modify ReadFileTool.call()


async def call(self, context: ToolContext, path: str, **kwargs) -> ToolResult:
    # Check cache first
    cached = context.file_cache.get(path)
    if cached:
        return ToolResult(output=cached.content, metadata={"cache_hit": True})

    # Read from disk
    content = Path(path).read_text(encoding="utf-8")

    # Cache for future reads
    context.file_cache.put(path, content)

    return ToolResult(output=content)
```

**Effort:** ~150 lines | **Priority:** P1

---

## Pattern 6: Session Memory Compaction

**Source:** `~/claude-code/src/services/compact/sessionMemoryCompact.ts`

**What claude-code does:**
- Before full LLM compaction, extracts memories from the conversation
- Writes extracted facts to memory files
- Then compacts the conversation with memory-aware instructions
- Compaction prompt includes: preserved memories, current task, recent files

**What Octopus has now:**
- `CompactionEngine.session_memory_compact()` generates LLM summary
- Does NOT extract memories before compaction

**Implementation:**

```python
# src/octopus/loop/compaction.py — extend existing


async def session_memory_compact(
    self,
    messages: list[Message],
    provider: Any,
    memory_manager: Any = None,
) -> CompactionResult:
    """Compact with memory extraction.

    1. Extract facts worth remembering from the conversation
    2. Store extracted memories (if memory_manager provided)
    3. Generate compaction summary that references stored memories
    """
    # Step 1: Extract memories
    extracted_facts: list[str] = []
    if memory_manager and self.config.extract_memories_on_compact:
        extraction_prompt = self._build_extraction_prompt(messages)
        extraction_response = await provider.chat(
            messages=[{"role": "user", "content": extraction_prompt}],
            model=self.config.summary_model,
            max_tokens=1000,
        )
        extracted_facts = self._parse_extracted_facts(extraction_response.content)

        # Store each fact
        for fact in extracted_facts:
            await memory_manager.store_from_extraction(fact)

    # Step 2: Generate summary with memory awareness
    summary_prompt = self._build_memory_aware_summary_prompt(messages, extracted_facts)
    summary_response = await provider.chat(
        messages=[{"role": "user", "content": summary_prompt}],
        model=self.config.summary_model,
        max_tokens=self.config.summary_max_tokens,
    )

    summary = summary_response.content
    if extracted_facts:
        summary += "\n\nStored memories from this session:\n"
        for fact in extracted_facts:
            summary += f"- {fact}\n"

    # Build compacted messages
    compacted = [
        Message(
            role="user",
            content=f"Conversation summary:\n{summary}",
        ),
    ]

    return CompactionResult(
        summary=summary,
        compacted_messages=compacted,
        original_count=len(messages),
        compacted_count=len(compacted),
        strategy=CompactionStrategy.SESSION_MEMORY,
    )


def _build_extraction_prompt(self, messages: list[Message]) -> str:
    """Build prompt for fact extraction."""
    conversation = self._format_for_summary(messages)
    return f"""Extract important facts from this conversation that should be remembered for future sessions.

Focus on:
- User preferences and corrections
- Project decisions and their rationale
- Key technical facts discovered
- Action items or TODOs
- External references (URLs, file paths, config values)

Format each fact as a single line. Do NOT include:
- Temporary debugging info
- Obvious facts derivable from code
- Conversation mechanics ("user asked me to...")

Conversation:
{conversation}

Extracted facts (one per line):"""


def _parse_extracted_facts(self, response: str) -> list[str]:
    """Parse extracted facts from LLM response."""
    facts = []
    for line in response.strip().split("\n"):
        line = line.strip()
        if line and not line.startswith("#") and len(line) > 10:
            # Strip list markers
            for prefix in ("- ", "* ", "1. ", "2. ", "3. "):
                if line.startswith(prefix):
                    line = line[len(prefix) :]
                    break
            facts.append(line)
    return facts[:20]  # Cap at 20 facts per compaction
```

**Config additions:**

```python
# src/octopus/config/schema.py
extract_memories_on_compact: bool = True
summary_model: str = "claude-haiku-4-5-20251001"
summary_max_tokens: int = 2000
```

**Effort:** ~200 lines | **Priority:** P1

---

## Pattern 7: QueryEngine Budget Enforcement

**Source:** `~/claude-code/src/QueryEngine.ts` lines 1023-1055

**What claude-code does:**
- `maxBudgetUsd` — stops execution when total cost exceeds limit
- `maxTurns` — stops after N turns
- `maxStructuredOutputRetries` — stops after N failed structured output attempts
- Yields specific error result types: `error_max_budget_usd`, `error_max_turns`, `error_max_structured_output_retries`

**What Octopus has now:**
- `max_turns` in LoopConfig but no cost budget

**Implementation:**

```python
# src/octopus/loop/engine.py — extend AgentLoop


@dataclass
class LoopBudget:
    """Budget constraints for agent loop execution."""

    max_turns: int | None = None
    max_cost_usd: float | None = None
    max_tool_calls: int | None = None
    max_input_tokens: int | None = None

    def check(
        self, tracker: CostTracker, turn_count: int, tool_call_count: int
    ) -> BudgetViolation | None:
        """Check if any budget constraint is violated."""
        if self.max_turns and turn_count >= self.max_turns:
            return BudgetViolation(
                type="max_turns",
                message=f"Reached maximum number of turns ({self.max_turns})",
                current=turn_count,
                limit=self.max_turns,
            )

        total_cost = tracker.get_total_cost()
        if self.max_cost_usd and total_cost >= self.max_cost_usd:
            return BudgetViolation(
                type="max_cost_usd",
                message=f"Reached maximum budget (${self.max_cost_usd:.2f})",
                current=total_cost,
                limit=self.max_cost_usd,
            )

        if self.max_tool_calls and tool_call_count >= self.max_tool_calls:
            return BudgetViolation(
                type="max_tool_calls",
                message=f"Reached maximum tool calls ({self.max_tool_calls})",
                current=tool_call_count,
                limit=self.max_tool_calls,
            )

        total_tokens = sum(
            mu.usage.input_tokens + mu.usage.output_tokens
            for mu in tracker.model_usage.values()
        )
        if self.max_input_tokens and total_tokens >= self.max_input_tokens:
            return BudgetViolation(
                type="max_input_tokens",
                message=f"Reached maximum tokens ({self.max_input_tokens})",
                current=total_tokens,
                limit=self.max_input_tokens,
            )

        return None


@dataclass
class BudgetViolation:
    type: str
    message: str
    current: float | int
    limit: float | int
```

**Wire into run_turn:**

```python
# In run_turn loop:
violation = self.budget.check(self.cost_tracker, turn_count, tool_call_count)
if violation:
    yield StreamEvent(
        type=StreamEventType.ERROR,
        data={
            "code": violation.type,
            "message": violation.message,
        },
    )
    break
```

**Effort:** ~150 lines | **Priority:** P1

---

## Pattern 8: Compact Boundary Messages

**Source:** `~/claude-code/src/services/compact/compact.ts`

**What claude-code does:**
- Emits `SystemCompactBoundaryMessage` after compaction
- Message contains `compactMetadata`: preserved segment, stats, strategy
- Messages after boundary are active context; pre-boundary released for GC
- Enables session resume from compaction point

**What Octopus has now:**
- Compaction replaces messages in-place, no boundary marker

**Implementation:**

```python
# src/octopus/loop/models.py — add message type


class CompactBoundaryData(BaseModel):
    """Metadata for a compaction boundary message."""

    strategy: str
    original_count: int
    compacted_count: int
    tokens_before: int
    tokens_after: int
    preserved_tail_uuid: str | None = None
    extracted_memories: list[str] = []


# src/octopus/loop/compaction.py — emit boundary after compaction


def apply_compaction(
    self,
    context: ConversationContext,
    result: CompactionResult,
) -> None:
    """Apply compaction result to context, preserving boundary marker."""
    # Insert compact boundary message
    boundary = Message(
        role="system",
        content=f"[Conversation compacted: {result.strategy.value}]",
        metadata={
            "type": "compact_boundary",
            "compact_metadata": result.to_boundary_data().model_dump(),
        },
    )

    # Replace messages: boundary + compacted tail
    context.messages = [boundary] + result.compacted_messages
```

**Effort:** ~100 lines | **Priority:** P2

---

## Pattern 9: Coordinator Worker Agents

**Source:** `~/claude-code/src/coordinator/workerAgent.ts`

**What claude-code does:**
- `workerAgent.ts`: background agent workers that run autonomously
- Workers have their own message history, tools, budget
- Coordinator injects task context, monitors progress
- Workers report results via attachment messages

**What Octopus has now:**
- `AgentCoordinator` with spawn/wait/stop
- No background execution, no per-worker budget

**Implementation:**

```python
# src/octopus/agents/coordinator.py — extend existing


@dataclass
class WorkerConfig:
    """Configuration for a background worker agent."""

    task: str
    agent_type: str = "general"
    model: str | None = None
    max_turns: int = 10
    max_cost_usd: float | None = None
    allowed_tools: list[str] | None = None
    isolation: Literal["none", "worktree"] = "none"


class WorkerAgent:
    """Background agent worker that runs autonomously."""

    def __init__(
        self,
        worker_id: str,
        config: WorkerConfig,
        tools: list[Tool],
        provider: Any,
        kernel: Any,
    ) -> None:
        self.worker_id = worker_id
        self.config = config
        self.tools = tools
        self.provider = provider
        self.kernel = kernel
        self.loop: AgentLoop | None = None
        self.result: Any = None
        self.status = "pending"
        self._task: asyncio.Task | None = None

    async def start(self) -> None:
        """Start worker in background."""
        self.status = "running"
        self._task = asyncio.create_task(self._run())

    async def _run(self) -> None:
        """Execute the worker's task."""
        try:
            self.loop = AgentLoop(
                provider=self.provider,
                tools=self.tools,
                kernel=self.kernel,
                config=LoopConfig(
                    max_turns=self.config.max_turns,
                    budget=LoopBudget(
                        max_turns=self.config.max_turns,
                        max_cost_usd=self.config.max_cost_usd,
                    ),
                ),
            )

            self.result = await self.loop.run(
                query=self.config.task,
                context=ConversationContext(),
            )
            self.status = "completed"
        except Exception as e:
            self.status = "failed"
            self.result = {"error": str(e)}

    async def wait(self, timeout: float | None = None) -> Any:
        """Wait for worker to complete."""
        if self._task:
            await asyncio.wait_for(self._task, timeout=timeout)
        return self.result

    def cancel(self) -> None:
        """Cancel the worker."""
        if self._task and not self._task.done():
            self._task.cancel()
            self.status = "cancelled"


class AgentCoordinator:
    """Extended coordinator with background workers."""

    def __init__(self, provider: Any, tools: list[Tool], kernel: Any) -> None:
        self.provider = provider
        self.tools = tools
        self.kernel = kernel
        self._workers: dict[str, WorkerAgent] = {}

    def spawn_worker(self, config: WorkerConfig) -> str:
        """Spawn a background worker agent."""
        import uuid

        worker_id = str(uuid.uuid4())[:8]
        worker = WorkerAgent(
            worker_id=worker_id,
            config=config,
            tools=self.tools,
            provider=self.provider,
            kernel=self.kernel,
        )
        self._workers[worker_id] = worker
        return worker_id

    async def start_worker(self, worker_id: str) -> None:
        worker = self._workers[worker_id]
        await worker.start()

    async def wait_worker(self, worker_id: str, timeout: float | None = None) -> Any:
        worker = self._workers[worker_id]
        return await worker.wait(timeout=timeout)

    def list_workers(self) -> list[dict[str, Any]]:
        return [
            {
                "id": w.worker_id,
                "status": w.status,
                "task": w.config.task[:100],
            }
            for w in self._workers.values()
        ]
```

**Effort:** ~300 lines | **Priority:** P2

---

## Pattern 10: Reactive Compact Improvements

**Source:** `~/claude-code/src/services/compact/reactiveCompact.ts`

**What claude-code does:**
- Detects "prompt too long" errors by checking error message patterns
- Retries with progressively more aggressive compaction
- Tracks whether reactive compact was triggered to avoid infinite loops
- `isReactiveOnlyMode()` — can disable auto-compact, rely only on reactive

**What Octopus has now:**
- `reactive_compact()` exists but is basic — just calls LLM summary
- No retry with escalation

**Implementation:**

```python
# src/octopus/loop/compaction.py — improve reactive_compact


async def reactive_compact(
    self,
    context: ConversationContext,
    error: Exception,
    provider: Any,
    attempt: int = 1,
    max_attempts: int = 3,
) -> CompactionResult:
    """Handle 'prompt too long' errors with escalating compaction.

    Attempt 1: microcompact (clear old tool results)
    Attempt 2: context collapse (truncate large blocks) + microcompact
    Attempt 3: full LLM compaction
    """
    error_msg = str(error).lower()
    is_prompt_too_long = any(
        pattern in error_msg
        for pattern in (
            "prompt is too long",
            "context_length_exceeded",
            "maximum context length",
            "tokens exceeds",
        )
    )

    if not is_prompt_too_long:
        raise error  # Not a context length error, re-raise

    messages = context.messages

    if attempt == 1:
        # Level 1: microcompact only
        messages = self.time_based_microcompact(
            messages,
            MicrocompactConfig(
                max_age_seconds=60,  # More aggressive: 1 min
                max_turns=3,
                preserve_last_n=1,
            ),
        )
        strategy = "reactive_microcompact"

    elif attempt == 2:
        # Level 2: microcompact + context collapse
        messages = self.time_based_microcompact(
            messages,
            MicrocompactConfig(
                max_age_seconds=30,
                max_turns=2,
                preserve_last_n=0,  # Clear ALL old results
            ),
        )
        messages = self.context_collapse(messages, max_chars=500_000)
        strategy = "reactive_collapse"

    else:
        # Level 3: full LLM compaction
        return await self.full_compact(messages, provider)

    tokens_after = self.estimate_tokens(messages)
    return CompactionResult(
        summary=f"Reactive compaction (attempt {attempt}): reduced context",
        compacted_messages=messages,
        original_count=len(context.messages),
        compacted_count=len(messages),
        strategy=CompactionStrategy.MICROCOMPACT,
        tokens_before=self.estimate_tokens(context.messages),
        tokens_after=tokens_after,
    )
```

**Effort:** ~100 lines | **Priority:** P2

---

## Implementation Roadmap

### Phase 5A: Core Enhancements (Weeks 25-26)

| Week | Tasks | Effort |
|------|-------|--------|
| 25 | Pattern 1 (Time-based microcompact) + Pattern 2 (Cost tracking) | ~350 lines |
| 26 | Pattern 3 (Tool enhancements) + Pattern 7 (Budget enforcement) | ~400 lines |

**Deliverable:** Token-aware compaction, cost visibility, hardened tools, budget limits.

### Phase 5B: Feature Additions (Weeks 27-28)

| Week | Tasks | Effort |
|------|-------|--------|
| 27 | Pattern 4 (Skills system) + Pattern 5 (File state cache) | ~550 lines |
| 28 | Pattern 6 (Session memory compaction) + Pattern 10 (Reactive compact) | ~300 lines |

**Deliverable:** Skills ecosystem, file read optimization, memory-aware compaction.

### Phase 5C: Advanced Patterns (Weeks 29-30)

| Week | Tasks | Effort |
|------|-------|--------|
| 29 | Pattern 8 (Compact boundaries) + Pattern 9 (Worker agents) | ~400 lines |
| 30 | Integration testing, documentation, bundled skills | ~300 lines |

**Deliverable:** Session resume from compaction points, background agent workers.

---

## Dependencies

```
Pattern 1 (Time microcompact) ──→ Pattern 6 (Session memory compact)
                                 ──→ Pattern 10 (Reactive compact)

Pattern 2 (Cost tracking) ──→ Pattern 7 (Budget enforcement)

Pattern 4 (Skills) ──→ extends existing AgentRegistry

Pattern 5 (File cache) ──→ improves all file-reading tools
```

---

## Success Criteria

After Phase 5, Octopus-Agent should:

1. Clear stale tool results automatically based on time and turn distance
2. Display per-turn and per-session cost in USD
3. Validate tool inputs before execution, classify destructiveness
4. Support markdown-based skills with argument substitution
5. Cache file reads to avoid redundant disk I/O
6. Extract memories before compacting conversations
7. Enforce cost/turn/token budgets with graceful shutdown
8. Mark compaction boundaries for session resume
9. Run background worker agents with per-worker budgets
10. Handle prompt-too-long errors with escalating compaction strategies
