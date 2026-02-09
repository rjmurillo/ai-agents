# Installation Guide

This guide covers installation of the AI Agents system using [skill-installer](https://github.com/rjmurillo/skill-installer), a Python-based TUI tool.

## Prerequisites

- Python 3.10+
- [UV](https://docs.astral.sh/uv/) package manager

### Installing UV

**macOS/Linux:**

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

**Windows (PowerShell):**

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

## Quick Start (Try Without Installing)

Run skill-installer directly without installing it:

```bash
# Latest version
uvx --from git+https://github.com/rjmurillo/skill-installer skill-installer interactive

# Specific version (e.g., v0.2.0)
uvx --from git+https://github.com/rjmurillo/skill-installer@v0.2.0 skill-installer interactive

# Older version (e.g., v0.1.0)
uvx --from git+https://github.com/rjmurillo/skill-installer@v0.1.0 skill-installer interactive
```

This launches the TUI where you can browse and install agents.

## Global Installation

Install skill-installer as a tool for repeated use:

```bash
# Latest version (main branch)
uv tool install git+https://github.com/rjmurillo/skill-installer

# Specific version (e.g., v0.2.0)
uv tool install git+https://github.com/rjmurillo/skill-installer@v0.2.0

# Older version (e.g., v0.1.0)
uv tool install git+https://github.com/rjmurillo/skill-installer@v0.1.0
```

**Note:** Installing a specific version provides stability and reproducibility. Use latest for bleeding-edge features.

## Adding This Repository as a Source

Add ai-agents as a source for discovering agents:

```bash
skill-installer source add rjmurillo/ai-agents
```

## Using the TUI

Launch the interactive interface:

```bash
skill-installer interactive
```

**Navigation:**

1. Navigate to the **Discover** tab
2. Browse available plugins (claude-agents, copilot-cli-agents, vscode-agents)
3. Select platform(s) to install
4. Press `i` to install

## CLI Installation (Non-Interactive)

Install specific items without the TUI:

```bash
# Install Claude agents
skill-installer install claude-agents --platform claude

# Install Copilot CLI agents
skill-installer install copilot-cli-agents --platform copilot

# Install VS Code agents
skill-installer install vscode-agents --platform vscode
```

## Installation Paths

### Global Installation Paths

| Platform | Agents | Skills |
|----------|--------|--------|
| Claude Code | `~/.claude/agents/` | `~/.claude/skills/` |
| Copilot CLI | `~/.copilot/agents/` | N/A |
| VS Code | `~/.vscode/prompts/` | N/A |

### Repository Installation Paths

| Platform | Agent Files | Instructions File |
|----------|-------------|-------------------|
| Claude Code | `.claude/agents/` | `CLAUDE.md` |
| Copilot CLI | `.github/agents/` | `.github/copilot-instructions.md` |
| VS Code | `.github/agents/` | `.github/copilot-instructions.md` |

## Uninstallation

Remove installed items:

```bash
skill-installer uninstall claude-agents
```

## Troubleshooting

### UV Not Found

Ensure UV is installed and in your PATH:

```bash
which uv  # macOS/Linux
where.exe uv  # Windows
```

If not found, install UV using the commands in the Prerequisites section.

### Python Version

skill-installer requires Python 3.10+. Check your version:

```bash
python --version
```

### Network Issues

If downloads fail, check internet connectivity and try again. The tool downloads from GitHub.

### Worktrunk Setup (Optional)

For parallel agent workflows using git worktrees, install Worktrunk:

**Homebrew (macOS and Linux):**

```bash
brew install max-sixty/worktrunk/wt && wt config shell install
```

**Cargo:**

```bash
cargo install worktrunk && wt config shell install
```

**Shell integration** is required for `wt switch` command.

**Claude Code Plugin:**

```bash
claude plugin marketplace add max-sixty/worktrunk
claude plugin install worktrunk@worktrunk
```

The repository includes `.config/wt.toml` with lifecycle hooks that:

- Configure git hooks automatically on worktree creation
- Copy dependencies (node_modules, .cache) from main worktree
- Run markdown linting before merge

**See**: [Worktrunk Documentation](https://worktrunk.dev/) and `.config/wt.toml` for complete workflow configuration.

## Post-Installation

### Restart Your Editor

After installation, restart your editor/CLI to load new agents:

- **Claude Code**: Restart Claude Code
- **VS Code**: Restart VS Code or reload window (`Ctrl+Shift+P` -> "Developer: Reload Window")
- **Copilot CLI**: No restart needed

### Verify Installation

**Claude Code:**

```python
# In Claude Code, verify agents are available
Task(subagent_type="analyst", prompt="Hello, are you available?")
```

**VS Code:**

```text
# In VS Code chat
@orchestrator Hello, are you available?
```

**Copilot CLI:**

```bash
# List available agents
copilot --list-agents

# Test an agent
copilot --agent analyst --prompt "Hello, are you available?"
```

## Related Documentation

- [USING-AGENTS.md](../USING-AGENTS.md) - How to use the agent system
- [CLAUDE.md](../CLAUDE.md) - Claude Code specific instructions
- [copilot-instructions.md](../copilot-instructions.md) - GitHub Copilot instructions
