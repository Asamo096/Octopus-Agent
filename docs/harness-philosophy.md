# Harness Governance: The Octopus Philosophy

## Why Harness Governance

AI agents can write code, execute shell commands, and modify files. Without guardrails, this is dangerous. Harness governance ensures every action passes through a structured pipeline before execution — making AI agents safe for real-world use.

## The Pipeline

Every agent action flows through four stages:

```
Agent requests action
    │
    ▼
┌─ 1. PERMISSION ──────────────────────────────────────────┐
│ Is this action allowed?                                   │
│ - Sensitive paths blocked (~/.ssh, .env, id_rsa)         │
│ - Dangerous commands require approval (rm -rf, sudo)      │
│ - Mode: manual / accept_edits / plan / auto               │
└──────────────────────────────────────────────────────────┘
    │ allowed
    ▼
┌─ 2. SANDBOX ─────────────────────────────────────────────┐
│ Where should this run?                                    │
│ - Local: subprocess on host                               │
│ - Cube: KVM MicroVM (hardware isolation)                  │
│ - Path validation, command safety check                   │
└──────────────────────────────────────────────────────────┘
    │ safe
    ▼
┌─ 3. AUDIT ───────────────────────────────────────────────┐
│ Record what happened.                                     │
│ - Timestamp, tool, args, result, duration, decision       │
│ - Full audit trail searchable via /audit                  │
│ - Export to JSON/CSV                                      │
└──────────────────────────────────────────────────────────┘
    │ logged
    ▼
┌─ 4. ROLLBACK ────────────────────────────────────────────┐
│ Undo if needed.                                           │
│ - Pre-execution snapshot before writes                    │
│ - Diff view of changes                                    │
│ - One-click restore to any checkpoint                     │
└──────────────────────────────────────────────────────────┘
```

## Permission Modes

| Mode | Shell | Write | Read | Use Case |
|------|-------|-------|------|----------|
| **manual** (default) | Ask approval | Ask approval | Allow | Untrusted code — review everything |
| **accept_edits** | Block | Allow | Allow | Code review — allow edits, no shell |
| **plan** | Block | Allow | Allow | Planning — file ops ok, no execution |
| **auto** | Allow | Allow | Allow | Trusted environment — full automation |

Switch modes with `Ctrl+P` during interactive sessions.

## Configuration

```toml
# ~/.octopus/config.toml
[permissions]
mode = "default"
allowed_paths = ["~/projects/*", "/tmp/*"]
sensitive_paths = ["~/secrets/*"]

[sandbox]
backend = "local"  # or "cube" for KVM isolation
```

## Audit Trail

Every action is logged. View with `/audit`:

```
14:32:01  read_file   main.py         ALLOWED        12ms
14:32:05  shell       npm test        APPROVED       1.2s
14:32:19  write_file  test_main.py    BLOCKED        0ms
```

Export: `octopus code logs` or `/audit export`

## Rollback

Before each destructive operation, Octopus snapshots file state. View with `/rollback list` and restore with `/rollback restore <id>`.

## Why This Matters

- **Trust**: Users can see exactly what the agent did and why
- **Safety**: Sensitive paths and dangerous commands are blocked by default
- **Accountability**: Full audit trail for compliance and debugging
- **Control**: Fine-grained permission rules adapt to any workflow
