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

## Installation Scripts

```powershell
# VS Code - Global
.\scripts\install-vscode-global.ps1

# VS Code - Per-repository
.\scripts\install-vscode-repo.ps1 -RepoPath "C:\Path\To\Repo"

# GitHub Copilot CLI - Per-repository (recommended)
.\scripts\install-copilot-cli-repo.ps1 -RepoPath "C:\Path\To\Repo"

# Claude Code - Global
.\scripts\install-claude-global.ps1

# Claude Code - Per-repository
.\scripts\install-claude-repo.ps1 -RepoPath "C:\Path\To\Repo"
```

## Utility Scripts

```powershell
# Fix markdown fences (closing fences with language identifiers)
pwsh .agents/utilities/fix-markdown-fences/fix_fences.ps1

# Python alternative
python .agents/utilities/fix-markdown-fences/fix_fences.py
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
