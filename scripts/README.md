# AI Agents Installation Scripts

PowerShell scripts for installing the AI Agents system to Claude Code, GitHub Copilot CLI, and VS Code.

## Script Organization

Scripts are organized by **intended audience and execution context**:

- **`scripts/`** - Developer-facing utilities (manual + pre-commit hooks)
- **`.github/scripts/`** - CI/CD automation (GitHub Actions only, not for direct use)
- **`build/scripts/`** - Build system automation
- **`.claude/skills/`** - AI agent skills (internal implementation, wrapped for developer use)
- **`tests/`** - Pester test files (root-level, not under scripts/)

**When to use each location**:

- Creating a tool for developers to run? → `scripts/`
- Building a GitHub Actions workflow helper? → `.github/scripts/`
- Adding AI agent capability? → `.claude/skills/` (with wrapper in `scripts/` if needed)
- Writing tests? → `tests/`

See [ADR-019](../.agents/architecture/ADR-019-script-organization.md) for detailed rationale and guidelines.

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
# Stable release (v0.1.0)
Set-ExecutionPolicy Bypass -Scope Process -Force
iex ((New-Object System.Net.WebClient).DownloadString('https://raw.githubusercontent.com/rjmurillo/ai-agents/v0.1.0/scripts/install.ps1'))

# Bleeding edge (main branch)
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

## CI Verification

The `.github/workflows/verify-install-script.yml` workflow validates install output across
Windows, macOS, and Linux for Claude, Copilot, and VS Code in both Global and Repo scopes.
It uses file-based checks (`scripts/tests/Verify-InstallOutput.ps1`) to confirm expected
files exist without requiring CLI authentication.

### Run Locally

```powershell
# Verify a global install
./scripts/tests/Verify-InstallOutput.ps1 -Environment Claude -Scope Global -CI

# Verify a repo install
./scripts/tests/Verify-InstallOutput.ps1 -Environment Copilot -Scope Repo -RepoPath . -CI
```

## Validation Scripts

The repository includes validation scripts for enforcing protocol compliance and code quality. These implement the technical guardrails from Issue #230.

### Session Protocol Validation

#### Validate-SessionJson.ps1

Validates session protocol compliance for session logs.

**Usage**:

```powershell
# Validate specific session
.\scripts\Validate-SessionJson.ps1 -SessionPath ".agents/sessions/2025-12-17-session-01.json"

# Validate all recent sessions
.\scripts\Validate-SessionJson.ps1 -All

# CI mode
.\scripts\Validate-SessionJson.ps1 -All -CI
```

**Called By**: Pre-commit hook, orchestrator, CI

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

#### Sync-McpConfig.ps1

Syncs MCP configuration from Claude Code's `.mcp.json` to Factory Droid and VS Code formats.

**Usage**:

```powershell
# Sync to VS Code (default behavior)
.\scripts\Sync-McpConfig.ps1

# Sync to Factory Droid
.\scripts\Sync-McpConfig.ps1 -Target factory

# Sync to both Factory and VS Code
.\scripts\Sync-McpConfig.ps1 -SyncAll

# Check what would change without making changes
.\scripts\Sync-McpConfig.ps1 -WhatIf

# Return boolean indicating whether sync occurred
$synced = .\scripts\Sync-McpConfig.ps1 -PassThru
if ($synced) { Write-Host "Configuration was synced" }
```

**Parameters**:

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `-SourcePath` | String | `.mcp.json` | Source Claude .mcp.json path |
| `-DestinationPath` | String | Auto-detected | Custom destination path (not used with SyncAll) |
| `-Target` | String | `vscode` | `vscode` or `factory` (mutually exclusive with SyncAll) |
| `-SyncAll` | Switch | `$false` | Generate both Factory and VS Code configs |
| `-Force` | Switch | `$false` | Overwrite even if content identical |
| `-WhatIf` | Switch | `$false` | Show what would change without making changes |
| `-PassThru` | Switch | `$false` | Return `$true` if files synced, `$false` otherwise |

**Output Formats**:

- Factory (`.factory/mcp.json`): Uses `mcpServers` root key (same as Claude)
- VS Code (`.vscode/mcp.json`): Uses `servers` root key, transforms serena config

**Note**: This script generates `.factory/mcp.json` for Factory Droid compatibility. For more information on Factory Droid MCP configuration, see <https://docs.factory.ai/cli/configuration/mcp>

See [docs/technical-guardrails.md](../docs/technical-guardrails.md) for complete validation documentation.

## Full Documentation

See [docs/installation.md](../docs/installation.md) for complete installation documentation including:

- Installation paths for each environment
- Upgrade process
- Troubleshooting guide
- Known issues

See [docs/technical-guardrails.md](../docs/technical-guardrails.md) for validation and guardrail documentation.
