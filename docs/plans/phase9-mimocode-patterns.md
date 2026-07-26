# Phase 9: MiMo-Code Reusable Patterns

> Generated: 2026-07-26
> Reference: ~/MiMo-Code (Xiaomi, TypeScript/Bun, terminal-native AI coding assistant)
> Goal: Extract adoptable patterns from MiMo-Code for Octopus-Agent

---

## Comparison: Octopus vs MiMo-Code

| Dimension | Octopus (Python) | MiMo-Code (TypeScript/Bun) |
|-----------|-----------------|---------------------------|
| **UI** | CLI (Rich+prompt_toolkit) | TUI (React/Ink, terminal-native) |
| **Auth** | API key only | OAuth + API key + import from Claude/Codex |
| **Skills** | Basic (review, explain) | 25+ builtin skills (arxiv, pdf, xlsx, etc.) |
| **Workflows** | None | Deterministic JS scripts for multi-agent orchestration |
| **Compose** | None | Spec-to-ship workflow with grill->spec->implement->verify->review |
| **Goal/Stop** | Max turns | Judge model evaluates completion |
| **Plugins** | Plugin loader skeleton | Full plugin ecosystem (mimo, codex, cloudflare, etc.) |
| **LSP** | None | Language Server Protocol integration |
| **Team** | None | Team collaboration features |
| **Memory** | Memdir-based | Memdir-based (same pattern) |

### Strengths of Octopus
- **Harness governance** — full permission pipeline, audit logging, sandbox (MiMo lacks this)
- **Python ecosystem** — easier to integrate with ML/AI tools
- **Dual-mode** — CLI + GUI (Tauri), MiMo is TUI only
- **CubeSandbox** — hardware-isolated KVM MicroVMs

### Strengths of MiMo-Code
- **Rich plugin ecosystem** — extensible with standardized plugin API
- **Workflow engine** — deterministic multi-agent orchestration
- **Compose workflow** — structured spec-to-ship pipeline
- **Goal evaluation** — judge model prevents premature stops
- **25+ builtin skills** — arxiv, pdf, xlsx, deep-research, etc.
- **Multiple auth methods** — OAuth, API key, clipboard import
- **LSP integration** — code intelligence (autocomplete, diagnostics)
- **TUI native** — full terminal UI with keyboard navigation

---

## Patterns Worth Adopting

### 1. Workflow Engine (High Priority)

**What MiMo-Code does:**
- Deterministic JavaScript scripts that orchestrate multiple agents
- Fixed phase sequences with bounded retries and auto-parallelization
- Built-in workflows: compose, deep-research, fact-check, research-experiment
- Custom workflows via `.mimocode/workflows/*.js` files
- Isolated git worktrees for parallel tasks

**Octopus current state:**
- No workflow engine
- Basic multi-agent coordinator

**Recommendation:** Implement a Python-based workflow engine using the existing AgentCoordinator. Support custom workflow scripts.

**Effort:** ~500 lines | **Priority:** Medium

---

### 2. Compose Workflow (High Priority)

**What MiMo-Code does:**
- `/compose-next` skill: grill -> spec -> workspace -> implement -> verify -> review -> finalize -> finish
- Feature documents at `docs/compose/spec/<feature>.md`
- Designed for frontier models (single compact contract)
- Legacy compose agent with 14 step-by-step skills for weaker models

**Octopus current state:**
- No structured development workflow
- No spec-to-implementation pipeline

**Recommendation:** Implement a simplified compose workflow as a skill. Start with grill->spec->implement->verify.

**Effort:** ~400 lines | **Priority:** Medium

---

### 3. Goal/Stop Condition (Medium Priority)

**What MiMo-Code does:**
- `/goal` command sets a stopping condition
- Independent judge model evaluates if condition is satisfied
- Prevents premature "optimistic stops" during autonomous work

**Octopus current state:**
- Max turns enforcement only
- No semantic completion checking

**Recommendation:** Add `/goal` command and judge evaluation. Simple version: prompt the model to self-evaluate if goals are met.

**Effort:** ~200 lines | **Priority:** Medium

---

### 4. Plugin Ecosystem (Medium Priority)

**What MiMo-Code does:**
- Standardized plugin API (tui, tool, shell exports)
- Plugin marketplace with search/discovery
- Built-in plugins: mimo, codex, cloudflare, xai, github-copilot
- Plugin install/update lifecycle
- Plugin sandboxing

**Octopus current state:**
- Plugin loader skeleton
- No marketplace or standardized API

**Recommendation:** Build on existing plugin skeleton. Implement standardized plugin API with tool export, shell integration, and TUI extensions.

**Effort:** ~600 lines | **Priority:** Medium

---

### 5. Auth Multi-Method (Medium Priority)

**What MiMo-Code does:**
- OAuth login (Xiaomi MiMo, Codex/ChatGPT, xAI)
- API key configuration
- Import from Claude Code/Codex
- Anonymous channel (MiMo Auto, free for limited time)

**Octopus current state:**
- API key only (auth.json)
- No OAuth support

**Recommendation:** Add OAuth flow for major providers. Start with clipboard-based key import.

**Effort:** ~300 lines | **Priority:** Medium

---

### 6. LSP Integration (Medium Priority)

**What MiMo-Code does:**
- Language Server Protocol client
- Code intelligence: autocomplete, diagnostics, hover, go-to-definition
- LSP server process management

**Octopus current state:**
- No LSP integration
- No code intelligence features

**Recommendation:** Implement basic LSP client for diagnostics and hover. Start with Python (pyright/pylsp).

**Effort:** ~400 lines | **Priority:** Medium

---

### 7. Rich Builtin Skills (Lower Priority)

**What MiMo-Code does:**
- 25+ builtin skills: arxiv, deep-research, docx, pdf, xlsx, pptx, html-to-video, learn-everything, super-research, etc.
- Skills searchable by name, alias, and BM25 relevance
- High-confidence matches auto-loaded
- User skills override builtins

**Octopus current state:**
- 2 bundled skills (review, explain)

**Recommendation:** Add 5-10 high-value skills: arxiv search, PDF generation, data analysis, code review, deep research.

**Effort:** ~500 lines | **Priority:** Low

---

### 8. TUI Experience (Lower Priority)

**What MiMo-Code does:**
- Full terminal UI with React/Ink components
- Keyboard-driven navigation
- Sidebar with file tree, session list, agent status
- Transcript view with search
- Theme support

**Octopus current state:**
- CLI with Rich + prompt_toolkit (good but not full TUI)
- Basic keyboard shortcuts

**Recommendation:** Invest in TUI improvements: searchable transcript, toggleable sidebar, better keyboard navigation.

**Effort:** ~500 lines | **Priority:** Low

---

### 9. Team Collaboration (Lower Priority)

**What MiMo-Code does:**
- Shared sessions
- Team memory vault
- Inbox for agent-to-agent messaging
- Permission sync across team members

**Octopus current state:**
- No team features
- Single-user only

**Recommendation:** Implement basic team features: shared memory vault, session sharing.

**Effort:** ~400 lines | **Priority:** Low

---

### 10. Multi-Model Switch (Already Have)

**What MiMo-Code does:**
- Model picker with provider discovery
- Auto-detection of available providers
- OAuth token management

**Octopus current state:**
- Already has `/model` command with model selection
- Config-based provider setup
- Good enough for now

**Recommendation:** Keep current implementation. No changes needed.

---

## Implementation Priority Matrix

| # | Pattern | Value | Complexity | Priority | Effort |
|---|---------|-------|-----------|----------|--------|
| 1 | Workflow engine | High | High | Medium | ~500 |
| 2 | Compose workflow | High | Medium | Medium | ~400 |
| 3 | Goal/Stop condition | Medium | Low | Medium | ~200 |
| 4 | Plugin ecosystem | Medium | High | Medium | ~600 |
| 5 | Auth multi-method | Medium | Medium | Medium | ~300 |
| 6 | LSP integration | Medium | High | Medium | ~400 |
| 7 | Builtin skills | Medium | Low | Low | ~500 |
| 8 | TUI improvements | Low | Medium | Low | ~500 |
| 9 | Team collaboration | Low | High | Low | ~400 |
| 10 | Model switch | — | — | Already Done | 0 |

**Total new effort:** ~3,800 lines

---

## Questions for User

1. **Workflow engine priority?** The workflow engine is the most unique MiMo-Code feature. Should we implement it now or after GUI completion?

2. **Compose workflow?** Do you want the spec-to-ship compose pipeline as a skill?

3. **Plugin ecosystem?** Should we prioritize pluggable architecture over builtin features?

4. **Auth methods?** Is OAuth support important for your use case, or is API key sufficient?

5. **LSP?** Do you need code intelligence (diagnostics, autocomplete) in the CLI?
