# Phase 8: Production Hardening

> Generated: 2026-07-26
> Goal: Production-ready packaging, sandbox integration, and ecosystem foundations

---

## Executive Summary

Phase 7 completes the GUI. Phase 8 focuses on making Octopus production-ready: proper CubeSandbox integration, cross-platform packaging, plugin ecosystem, and performance optimization.

### Patterns to Adopt

| # | Pattern | Effort | Priority |
|---|---------|--------|----------|
| 1 | CubeSandbox full integration | ~300 lines | P0 |
| 2 | Cross-platform packaging | ~200 lines | P0 |
| 3 | Plugin marketplace | ~300 lines | P1 |
| 4 | MCP server discovery | ~200 lines | P1 |
| 5 | Auto-update mechanism | ~150 lines | P1 |
| 6 | Performance optimization | ~200 lines | P2 |
| 7 | Team collaboration | ~400 lines | P2 |
| 8 | System tray & notifications | ~150 lines | P2 |
| 9 | Crash reporting | ~100 lines | P2 |
| 10 | Documentation site | ~200 lines | P2 |

---

## Pattern 1: CubeSandbox Full Integration

Wire CubeSandbox into the kernel's permission pipeline for hardware-isolated execution.

**Key changes:**
- `kernel._sandbox_check()` routes to CubeSandbox via `cube.py` adapter
- Shell commands execute in isolated MicroVM
- File operations use sandbox filesystem API
- Snapshots for pre-execution rollback points
- Network access control per sandbox

**Config:**
```toml
[sandbox]
backend = "cube"                    # local | cube
cube_api_url = "http://127.0.0.1:3000"
cube_template_id = "tpl-xxx"
cube_api_key = ""
auto_pause_timeout = 300
allow_internet = true
```

**Effort:** ~300 lines | **Priority:** P0

---

## Pattern 2: Cross-Platform Packaging

Create installers for Linux (AppImage/deb), macOS (DMG), Windows (MSI).

**Key changes:**
- PyInstaller spec for Python backend bundle
- Tauri bundler configuration per platform
- CI/CD pipeline for automated builds
- Windows: handle Python sidecar as embedded exe
- macOS: code signing and notarization
- Linux: AppImage with bundled dependencies

**Effort:** ~200 lines | **Priority:** P0

---

## Pattern 3: Plugin Marketplace

Enable community plugins with discovery, installation, and lifecycle management.

**Key changes:**
- Plugin registry with search/discovery
- One-click install from marketplace
- Plugin sandboxing (permissions per plugin)
- Plugin update checking
- Plugin rating and reviews

**Effort:** ~300 lines | **Priority:** P1

---

## Pattern 4: MCP Server Discovery

Auto-discover and connect to MCP servers in the local environment.

**Key changes:**
- Scan common paths for MCP server configs
- Auto-connect to known MCP servers
- Server health monitoring
- Reconnection on disconnect
- Tool listing per server

**Effort:** ~200 lines | **Priority:** P1

---

## Pattern 5: Auto-Update Mechanism

Check for updates and apply them seamlessly.

**Key changes:**
- Version check against GitHub releases
- Background download of updates
- Tauri updater integration
- Rollback on failed update
- Release notes display

**Effort:** ~150 lines | **Priority:** P1

---

## Pattern 6-10: Polish & Ecosystem

| # | Pattern | Description |
|---|---------|-------------|
| 6 | Performance optimization | Token counting, prompt caching, parallel tool execution |
| 7 | Team collaboration | Shared sessions, team memory vault, permission sync |
| 8 | System tray & notifications | Background mode, desktop notifications |
| 9 | Crash reporting | Sentry/telemetry integration, error reporting |
| 10 | Documentation site | Mintlify/Docusaurus docs with API reference |

---

## Implementation Roadmap

### Phase 8A: Production Core (Weeks 38-39)

| Week | Tasks | Effort |
|------|-------|--------|
| 38 | Pattern 1 (CubeSandbox) + Pattern 5 (Auto-update) | ~450 lines |
| 39 | Pattern 2 (Packaging) + cross-platform testing | ~200 lines |

### Phase 8B: Ecosystem (Weeks 40-42)

| Week | Tasks | Effort |
|------|-------|--------|
| 40 | Pattern 3 (Plugin marketplace) + Pattern 4 (MCP) | ~500 lines |
| 41 | Pattern 6 (Performance) + Pattern 9 (Crash reporting) | ~300 lines |
| 42 | Pattern 7 (Team) + Pattern 8 (Tray) + Pattern 10 (Docs) | ~750 lines |

---

## Total Project Timeline

| Phase | Weeks | Status |
|-------|-------|--------|
| Phase 1: MVP Core | 1-4 | Done |
| Phase 2: Enhanced | 5-8 | Done |
| Phase 3: Full | 9-14 | Done |
| Phase 4: Gap Analysis | 15-20 | Done |
| Phase 5: claude-code Patterns | 21-26 | Done |
| Phase 6: CLI UI Polish | 27-30 | Planned (~840 lines) |
| Phase 7: GUI Completion | 31-37 | Planned (~2,350 lines) |
| Phase 8: Production Hardening | 38-42 | Planned (~2,200 lines) |

**Total: 42 weeks, ~20,000+ lines**
