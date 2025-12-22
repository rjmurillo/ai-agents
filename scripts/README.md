# AI Agents Installation Scripts

PowerShell scripts for installing the AI Agents system to Claude Code, GitHub Copilot CLI, and VS Code.

## Overview

The installation system provides:

- **Unified installer** (`install.ps1`) - Single script for all environments
- **Remote execution support** - Install directly from GitHub without cloning
- **Legacy scripts** - Individual scripts for backward compatibility

## Directory Structure

```text
scripts/
├── install.ps1                      # Unified entry point
├── lib/
│   ├── Install-Common.psm1          # Shared functions module
│   └── Config.psd1                  # Environment configurations
├── tests/
│   ├── Install-Common.Tests.ps1     # Module unit tests
│   ├── Config.Tests.ps1             # Configuration validation tests
│   └── install.Tests.ps1            # Entry point tests
└── [legacy scripts]                 # Backward compatibility wrappers
```

## Quick Reference

### Remote Installation

```powershell
Set-ExecutionPolicy Bypass -Scope Process -Force
iex ((New-Object System.Net.WebClient).DownloadString('https://raw.githubusercontent.com/rjmurillo/ai-agents/main/scripts/install.ps1'))
```

### Local Installation

```powershell
# Claude Code
.\install.ps1 -Environment Claude -Global
.\install.ps1 -Environment Claude -RepoPath "C:\MyRepo"

# GitHub Copilot CLI
.\install.ps1 -Environment Copilot -Global
.\install.ps1 -Environment Copilot -RepoPath "."

# VS Code
.\install.ps1 -Environment VSCode -Global
.\install.ps1 -Environment VSCode -RepoPath "C:\MyRepo" -Force
```

### Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `-Environment` | String | `Claude`, `Copilot`, or `VSCode` |
| `-Global` | Switch | Install to user-level location |
| `-RepoPath` | String | Install to specified repository |
| `-Force` | Switch | Overwrite without prompting |

## Legacy Scripts

For backward compatibility, individual scripts are available:

| Script | Equivalent |
|--------|------------|
| `install-claude-global.ps1` | `install.ps1 -Environment Claude -Global` |
| `install-claude-repo.ps1` | `install.ps1 -Environment Claude -RepoPath <path>` |
| `install-copilot-cli-global.ps1` | `install.ps1 -Environment Copilot -Global` |
| `install-copilot-cli-repo.ps1` | `install.ps1 -Environment Copilot -RepoPath <path>` |
| `install-vscode-global.ps1` | `install.ps1 -Environment VSCode -Global` |
| `install-vscode-repo.ps1` | `install.ps1 -Environment VSCode -RepoPath <path>` |

## Module Functions

The `Install-Common.psm1` module exports these functions:

| Function | Purpose |
|----------|---------|
| `Get-InstallConfig` | Load configuration for environment/scope |
| `Resolve-DestinationPath` | Expand path expressions with variables |
| `Test-SourceDirectory` | Validate source directory exists |
| `Get-AgentFiles` | Find agent files matching pattern |
| `Initialize-Destination` | Create destination directory |
| `Test-GitRepository` | Check if path is a git repository |
| `Initialize-AgentsDirectories` | Create .agents subdirectories |
| `Copy-AgentFile` | Copy single agent file with prompting |
| `Install-InstructionsFile` | Install/upgrade instructions file |
| `Write-InstallHeader` | Display installation header |
| `Write-InstallComplete` | Display completion message |

## Configuration

`Config.psd1` contains environment-specific settings:

```powershell
@{
    _Common = @{
        BeginMarker = "<!-- BEGIN: ai-agents installer -->"
        EndMarker = "<!-- END: ai-agents installer -->"
        AgentsDirs = @(".agents/analysis", ...)
    }

    Claude = @{
        DisplayName = "Claude Code"
        SourceDir = "src/claude"
        FilePattern = "*.md"
        Global = @{ DestDir = '$HOME/.claude/agents' }
        Repo = @{ DestDir = '.claude/agents' }
    }

    # Copilot, VSCode...
}
```

## Running Tests

Requires [Pester](https://pester.dev/) 5.x:

```powershell
# Install Pester
Install-Module -Name Pester -Force -Scope CurrentUser

# Run all tests
Invoke-Pester -Path .\scripts\tests

# Run specific test file
Invoke-Pester -Path .\scripts\tests\Install-Common.Tests.ps1

# Run with detailed output
Invoke-Pester -Path .\scripts\tests -Output Detailed
```

## GitHub Actions

Tests run automatically on PR/push to `scripts/**` via `.github/workflows/pester-tests.yml`.

## Validation Scripts

The repository includes validation scripts for enforcing protocol compliance and code quality. These implement the technical guardrails from Issue #230.

### Session Protocol Validation

#### Validate-SessionEnd.ps1

Validates Session End protocol compliance for a single session log.

**Usage**:

```powershell
.\scripts\Validate-SessionEnd.ps1 -SessionLogPath ".agents/sessions/2025-12-22-session-01.md"
```

**Called By**: Pre-commit hook, orchestrator, CI

#### Validate-SessionProtocol.ps1

Validates session protocol compliance across multiple sessions.

**Usage**:

```powershell
# Validate specific session
.\scripts\Validate-SessionProtocol.ps1 -SessionPath ".agents/sessions/2025-12-17-session-01.md"

# Validate all recent sessions
.\scripts\Validate-SessionProtocol.ps1 -All

# CI mode
.\scripts\Validate-SessionProtocol.ps1 -All -CI
```

### PR and Code Quality

#### Validate-PRDescription.ps1

Validates PR description matches actual code changes (prevents Analyst CRITICAL_FAIL).

**Usage**:

```powershell
.\scripts\Validate-PRDescription.ps1 -PRNumber 226 -CI
```

**Called By**: CI workflow (`.github/workflows/pr-validation.yml`)

#### Detect-SkillViolation.ps1

Detects raw `gh` command usage when GitHub skills exist (WARNING, non-blocking).

**Usage**:

```powershell
# Check staged files
.\scripts\Detect-SkillViolation.ps1 -StagedOnly

# Check entire repo
.\scripts\Detect-SkillViolation.ps1
```

**Called By**: Pre-commit hook

#### Detect-TestCoverageGaps.ps1

Detects PowerShell files without corresponding test files (WARNING, non-blocking).

**Usage**:

```powershell
# Check staged files
.\scripts\Detect-TestCoverageGaps.ps1 -StagedOnly

# Check with ignore file
.\scripts\Detect-TestCoverageGaps.ps1 -IgnoreFile ".testignore"
```

**Called By**: Pre-commit hook

### PR Creation

#### New-ValidatedPR.ps1

Creates a PR with all guardrails enforced.

**Usage**:

```powershell
# Normal PR (runs validations)
.\scripts\New-ValidatedPR.ps1 -Title "feat: Add feature" -Body "Description"

# Draft PR
.\scripts\New-ValidatedPR.ps1 -Title "WIP: Feature" -Draft

# Force mode (creates audit trail)
.\scripts\New-ValidatedPR.ps1 -Title "hotfix" -Force

# Interactive mode
.\scripts\New-ValidatedPR.ps1 -Web
```

### Other Validation Scripts

- `Validate-Consistency.ps1` - Cross-document consistency
- `Sync-McpConfig.ps1` - MCP configuration sync
- `Check-SkillExists.ps1` - Skill availability check
- `Invoke-BatchPRReview.ps1` - Batch PR review automation

See [docs/technical-guardrails.md](../docs/technical-guardrails.md) for complete validation documentation.

## Full Documentation

See [docs/installation.md](../docs/installation.md) for complete installation documentation including:

- Installation paths for each environment
- Upgrade process
- Troubleshooting guide
- Known issues

See [docs/technical-guardrails.md](../docs/technical-guardrails.md) for validation and guardrail documentation.
