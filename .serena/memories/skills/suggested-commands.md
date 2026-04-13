# Suggested Commands

## System Commands (Windows)

```powershell
# List directory contents
dir
Get-ChildItem

# Find files
Get-ChildItem -Recurse -Filter "*.md"

# Search file contents
Select-String -Path "*.md" -Pattern "search-term"

# Git commands (standard)
git status
git diff
git add .
git commit -m "message"
git push
```

## Markdown Linting

```bash
# Check all markdown files
npx markdownlint-cli2 "**/*.md"

# Fix auto-fixable issues
npx markdownlint-cli2 --fix "**/*.md"

# Local installation (if available)
./node_modules/.bin/markdownlint-cli2 "**/*.md"
```

## Pre-commit Hook Setup

```bash
# Enable the git hooks directory
git config core.hooksPath .githooks

# This enables auto-fix of markdown on every commit
```

## Bypass Pre-commit (use sparingly)

```bash
# Skip auto-fix, check only (CI mode)
SKIP_AUTOFIX=1 git commit -m "message"

# Skip hook entirely
git commit --no-verify -m "message"
```

## Agent Installation

Use [skill-installer](https://github.com/rjmurillo/skill-installer) for agent installation:

```bash
# Install skill-installer
uv tool install git+https://github.com/rjmurillo/skill-installer

# Add ai-agents source
skill-installer source add rjmurillo/ai-agents

# Interactive TUI installation
skill-installer interactive

# CLI installation
skill-installer install claude-agents --platform claude
skill-installer install vscode-agents --platform vscode
skill-installer install copilot-cli-agents --platform copilot
```

See [docs/installation.md](../../docs/installation.md) for complete installation documentation.

## Utility Scripts

```powershell
# Fix markdown fences (closing fences with language identifiers)
pwsh .claude/skills/fix-markdown-fences/fix_fences.ps1

# Python alternative
python .claude/skills/fix-markdown-fences/fix_fences.py
```

## Agent Invocation

### Claude Code

```python
Task(subagent_type="analyst", prompt="Investigate why X fails")
Task(subagent_type="implementer", prompt="Implement feature X")
Task(subagent_type="critic", prompt="Validate plan at .agents/planning/...")
```

### GitHub Copilot CLI

```bash
copilot --agent analyst --prompt "investigate issue X"
copilot --agent implementer --prompt "fix the bug"
```

### VS Code

```text
@orchestrator Help me implement a new feature
@implementer Fix the bug in UserService.cs
@analyst Investigate why tests are failing
```
