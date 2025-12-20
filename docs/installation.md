# Installation Guide

This guide covers all installation methods for the AI Agents system across Claude Code, GitHub Copilot CLI, and VS Code environments.

## Quick Installation (Remote)

The easiest way to install is via remote execution. This downloads and runs the installer directly from GitHub.

### Windows PowerShell

```powershell
# Remote installation (interactive)
Set-ExecutionPolicy Bypass -Scope Process -Force
iex ((New-Object System.Net.WebClient).DownloadString('https://raw.githubusercontent.com/rjmurillo/ai-agents/main/scripts/install.ps1'))
```

This will prompt you to select:

1. **Environment**: Claude Code, GitHub Copilot CLI, or VS Code
2. **Scope**: Global (user-level) or Repository (project-specific)

## Local Installation

If you have cloned the repository, you can use the unified installer or legacy scripts.

### Unified Installer (Recommended)

The unified `install.ps1` script supports all environments and scopes:

```powershell
# Claude Code - Global
.\scripts\install.ps1 -Environment Claude -Global

# Claude Code - Repository
.\scripts\install.ps1 -Environment Claude -RepoPath "C:\Path\To\Repo"

# GitHub Copilot CLI - Global
.\scripts\install.ps1 -Environment Copilot -Global

# GitHub Copilot CLI - Repository
.\scripts\install.ps1 -Environment Copilot -RepoPath "."

# VS Code - Global
.\scripts\install.ps1 -Environment VSCode -Global

# VS Code - Repository
.\scripts\install.ps1 -Environment VSCode -RepoPath "C:\Path\To\Repo"
```

#### Parameters

| Parameter | Description | Required |
|-----------|-------------|----------|
| `-Environment` | Target environment: `Claude`, `Copilot`, or `VSCode` | Yes* |
| `-Global` | Install to user-level location | One of these |
| `-RepoPath` | Install to specified repository path | One of these |
| `-Force` | Overwrite existing files without prompting | No |

*If not provided, interactive mode prompts for selection.

### Legacy Scripts (Backward Compatible)

Individual scripts are still available for each environment/scope combination:

```powershell
# VS Code
.\scripts\install-vscode-global.ps1
.\scripts\install-vscode-repo.ps1 -RepoPath "C:\Path\To\Repo"

# GitHub Copilot CLI
.\scripts\install-copilot-cli-global.ps1
.\scripts\install-copilot-cli-repo.ps1 -RepoPath "C:\Path\To\Repo"

# Claude Code
.\scripts\install-claude-global.ps1
.\scripts\install-claude-repo.ps1 -RepoPath "C:\Path\To\Repo"
```

## Installation Paths

### Global Installation Paths

| Environment | Agents | Commands/Prompts |
|-------------|--------|------------------|
| Claude Code | `~/.claude/agents/` | `~/.claude/commands/` |
| Copilot CLI | `~/.copilot/agents/` | (same directory as agents) |
| VS Code | `%APPDATA%/Code/User/prompts/` | (same directory as agents) |

### Repository Installation Paths

| Environment | Agent Files | Commands/Prompts | Instructions File |
|-------------|-------------|------------------|-------------------|
| Claude Code | `.claude/agents/` | `.claude/commands/` | `CLAUDE.md` (repo root) |
| Copilot CLI | `.github/agents/` | (same directory) | `.github/copilot-instructions.md` |
| VS Code | `.github/agents/` | (same directory) | `.github/copilot-instructions.md` |

### .agents Directory (Repository Only)

Repository installations also create the `.agents/` artifact directory:

```text
.agents/
├── analysis/        # Analyst findings
├── architecture/    # ADRs and design decisions
├── planning/        # Plans and PRDs
├── critique/        # Plan reviews
├── qa/              # Test reports
├── retrospective/   # Learning extractions
├── roadmap/         # Roadmap documents
├── devops/          # CI/CD artifacts
├── security/        # Security reviews
└── sessions/        # Session logs
```

### What Gets Installed

The installer copies different file types depending on the environment:

**Claude Code:**

| File Type | Extension | Location | Purpose |
|-----------|-----------|----------|---------|
| Agent files | `*.md` | `agents/` | Full agent definitions for Task tool invocation |
| Command files | `*.md` | `commands/` | Slash commands (e.g., `/pr-comment-responder`) |

**VS Code / Copilot CLI:**

| File Type | Extension | Location | Purpose |
|-----------|-----------|----------|---------|
| Agent files | `*.agent.md` | `agents/` or `prompts/` | Full agent definitions with tools |
| Prompt files | `*.prompt.md` | Same as agents | Reusable prompts for quick actions |

**Note**: Prompt files are auto-generated from selected agent files during installation (e.g., `pr-comment-responder.agent.md` → `pr-comment-responder.prompt.md`).

## Upgrade Process

The installer supports upgrading existing installations:

1. **Existing files**: Prompts before overwriting (use `-Force` to skip)
2. **Instructions file**: Uses content blocks for clean upgrades

### Instructions File Content Blocks

The installer wraps content in HTML comment markers:

```markdown
<!-- BEGIN: ai-agents installer -->
[Agent system content]
<!-- END: ai-agents installer -->
```

On upgrade:

- If markers exist: Content between markers is replaced (upgrade)
- If no markers: Content is appended with markers (first install)
- With `-Force`: Entire file is replaced

## Known Issues

### GitHub Copilot CLI Global Installation

There is a known issue with user-level agent loading in Copilot CLI.

- **Issue**: [#452 - User-level agents not loaded](https://github.com/github/copilot-cli/issues/452)
- **Workaround**: Use repository-level installation instead

The installer displays a warning when using Copilot CLI global installation.

## Troubleshooting

### PowerShell Execution Policy

If you receive an execution policy error:

```powershell
# Option 1: Bypass for current session
Set-ExecutionPolicy Bypass -Scope Process -Force

# Option 2: Set policy permanently (Admin required)
Set-ExecutionPolicy RemoteSigned -Scope CurrentUser
```

### Source Directory Not Found

Error: `Source directory not found: src/claude`

Ensure you are running from the repository root or provide the full path.

### Module Not Found (Remote Execution)

Error: `Failed to download installer components`

- Check internet connectivity
- Verify GitHub is accessible
- Try again (transient network issue)

### Permission Denied

Error when writing to destination directory:

- **Windows**: Run PowerShell as Administrator for global installation
- **macOS/Linux**: Check directory permissions

### File Already Exists

When prompted about existing files:

- Enter `y` to overwrite
- Enter `n` to skip
- Use `-Force` flag to skip all prompts

## Post-Installation

### Restart Your Editor

After installation, restart your editor/CLI to load new agents:

- **Claude Code**: Restart Claude Code
- **VS Code**: Restart VS Code or reload window (`Ctrl+Shift+P` -> "Developer: Reload Window")
- **Copilot CLI**: No restart needed

### Verify Installation

#### Claude Code

```python
# In Claude Code, verify agents are available
Task(subagent_type="analyst", prompt="Hello, are you available?")
```

#### VS Code

```text
# In VS Code chat
@orchestrator Hello, are you available?
```

#### Copilot CLI

```bash
# List available agents
copilot --list-agents

# Test an agent
copilot --agent analyst --prompt "Hello, are you available?"
```

### Commit Changes (Repository Installation)

For repository installations, commit the new files:

```bash
# Claude Code
git add .claude CLAUDE.md .agents
git commit -m "feat: add Claude agent system"

# Copilot CLI / VS Code
git add .github/agents .github/copilot-instructions.md .agents
git commit -m "feat: add Copilot agent system"
```

## Uninstallation

To remove the agent system, delete the installed files:

### Global

```powershell
# Claude Code
Remove-Item -Recurse -Force "~/.claude/agents"
Remove-Item -Recurse -Force "~/.claude/commands"

# Copilot CLI
Remove-Item -Recurse -Force "~/.copilot/agents"

# VS Code
Remove-Item -Recurse -Force "$env:APPDATA/Code/User/prompts"
```

### Repository

```bash
# Remove agent files and artifacts
git rm -r .claude/agents .claude/commands .agents  # For Claude
git rm -r .github/agents .agents                    # For Copilot/VSCode
git commit -m "chore: remove agent system"
```

For instructions files, either:

- Delete the entire file, or
- Remove the content between `<!-- BEGIN: ai-agents installer -->` and `<!-- END: ai-agents installer -->`

## Related Documentation

- [USING-AGENTS.md](../USING-AGENTS.md) - How to use the agent system
- [CLAUDE.md](../CLAUDE.md) - Claude Code specific instructions
- [copilot-instructions.md](../copilot-instructions.md) - GitHub Copilot instructions
