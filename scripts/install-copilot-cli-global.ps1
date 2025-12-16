<#
.SYNOPSIS
    Install GitHub Copilot CLI agents globally.

.DESCRIPTION
    Wrapper script for backward compatibility.
    Calls the unified install.ps1 with -Environment Copilot -Global.

    DEPRECATED: This script is maintained for backward compatibility.
    Prefer using: .\install.ps1 -Environment Copilot -Global

    WARNING: As of December 2025, there is a known bug (GitHub Issue #452) where
    user-level agents in ~/.copilot/agents/ are not loaded by Copilot CLI.
    Use install-copilot-cli-repo.ps1 for per-repository installation instead.

.PARAMETER Force
    Overwrite existing files without prompting.

.EXAMPLE
    .\install-copilot-cli-global.ps1
    .\install-copilot-cli-global.ps1 -Force
#>

param(
    [switch]$Force
)

$ErrorActionPreference = "Stop"

# Call unified installer
$InstallScript = Join-Path $PSScriptRoot "install.ps1"
& $InstallScript -Environment Copilot -Global -Force:$Force
