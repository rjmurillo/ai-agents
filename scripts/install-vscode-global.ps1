<#
.SYNOPSIS
    Install VSCode agents globally.

.DESCRIPTION
    Wrapper script for backward compatibility.
    Calls the unified install.ps1 with -Environment VSCode -Global.

    DEPRECATED: This script is maintained for backward compatibility.
    Prefer using: .\install.ps1 -Environment VSCode -Global

.PARAMETER Force
    Overwrite existing files without prompting.

.EXAMPLE
    .\install-vscode-global.ps1
    .\install-vscode-global.ps1 -Force

.NOTES
    EXIT CODES:
    0  - Success: Installation completed (exit code from install.ps1)
    1  - Error: Installation failed (exit code from install.ps1)

    See: ADR-035 Exit Code Standardization
#>

param(
    [switch]$Force
)

$ErrorActionPreference = "Stop"

# Call unified installer
$InstallScript = Join-Path $PSScriptRoot "install.ps1"
& $InstallScript -Environment VSCode -Global -Force:$Force
