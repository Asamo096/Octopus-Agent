# Getting Started with Octopus Agent

## Install

```bash
pip install -e .
pip install textual  # required for TUI
```

## Configure

Create `~/.octopus/auth.json`:
```json
{
  "OPENAI_API_KEY": "sk-..."
}
```

Create `~/.octopus/config.toml`:
```toml
model_provider = "openai"
model = "gpt-4o"

[model_providers.openai]
name = "OpenAI"
base_url = "https://api.openai.com/v1"
```

## Launch

```bash
octopus
```

This opens the TUI. Type your prompt and press Enter.

## Basic Commands

| Command | Description |
|---------|-------------|
| `/help` | Show all commands |
| `/model` | Select AI model |
| `/config` | Show configuration |
| `/audit` | View action history |
| `/clear` | Start new session |
| `/exit` | Quit |

## Keyboard Shortcuts

| Key | Action |
|-----|--------|
| `Ctrl+P` | Cycle permission mode |
| `Ctrl+Shift+C` | Copy last response |
| `Ctrl+C` | Quit |
| `Escape` | Interrupt generation |
| `Enter` | Submit message |
| `Shift+Enter` | New line |

## Permission Modes

Press `Ctrl+P` to cycle:

- **manual** — approve each action
- **accept_edits** — allow file edits, block shell
- **plan** — read only, all writes blocked
- **auto** — full automation

## Non-interactive Mode

```bash
octopus cli "Write a Python sorting function"
octopus code init    # Initialize workspace
octopus code fix     # Auto-detect and fix bugs
octopus code test    # Generate tests
```
