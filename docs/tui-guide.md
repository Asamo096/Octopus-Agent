# Octopus TUI Guide

## Overview

Octopus provides a full terminal UI (TUI) mode using Textual as an alternative to the Rich+prompt_toolkit CLI. The TUI works in headless environments, SSH sessions, and tmux where the GUI cannot run.

## Launching the TUI

```bash
# Launch TUI mode
octopus cli --tui

# With specific model
octopus cli --tui --model gpt-4o

# With custom permission mode
octopus cli --tui --permission-mode full_auto
```

## Keyboard Shortcuts

| Key | Action |
|-----|--------|
| `Ctrl+C` | Quit |
| `Ctrl+P` | Cycle permission mode (default -> accept_edits -> auto -> plan) |
| `Ctrl+S` | Focus sidebar |
| `Ctrl+L` | Focus chat input |
| `Ctrl+/` | Slash command mode (inserts `/`) |
| `Enter` | Submit message |
| `Shift+Enter` | New line in input |
| `Escape` | Cancel / interrupt |
| `Up/Down` | Navigate input history (when input is empty) |

## Slash Commands

All CLI slash commands work in TUI mode:

| Command | Description |
|---------|-------------|
| `/help` | Show available commands |
| `/init` | Generate OCTOPUS.md with project docs |
| `/cd <path>` | Change working directory |
| `/clear` | Clear conversation, start new session |
| `/compact` | Force conversation compaction |
| `/config show` | Show current configuration |
| `/context` | Show context usage breakdown |
| `/model` | Fetch and select model |
| `/tokens` | Show estimated token count |
| `/reset` | Reset conversation history |
| `/exit` | Exit Octopus |

## TUI Widgets

### Chat Log
Displays the conversation with role-specific styling:
- User messages in bold blue
- Assistant messages in default text (markdown rendered)
- System messages in dim italic
- Tool calls in cyan with arguments
- Errors in bold red

### Sidebar
Three tabs provide session context:
- **Info**: current model, permission mode, workspace path, session ID
- **Sessions**: list of saved sessions
- **Agents**: active agent workers and their status

### Status Bar
Bottom bar showing:
- Current permission mode (color-coded)
- Token usage count
- API cost in USD
- Tool call count
- Keyboard shortcut hints

## Configuration

TUI uses the same configuration as the CLI (`~/.octopus/config.toml` and `~/.octopus/auth.json`). No additional configuration is required.

## Requirements

Install the `textual` optional dependency:

```bash
pip install octopus-agent[textual]
```

## Differences from CLI Mode

| Feature | CLI (Rich+prompt_toolkit) | TUI (Textual) |
|---------|--------------------------|---------------|
| Interface | Line-based, scrolls up | Full-screen, persistent widgets |
| Output | Rich rendering | Rich markup in Textual widgets |
| History | Up/down arrow in input | Up/down arrow when input empty |
| Sidebar | Not available | File tree, sessions, agents |
| Status bar | Bottom toolbar | Persistent bottom bar |
| SSH/headless | Works | Works (same environment) |
