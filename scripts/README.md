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

## Full Documentation

See [docs/installation.md](../docs/installation.md) for complete installation documentation including:

- Installation paths for each environment
- Upgrade process
- Troubleshooting guide
- Known issues
