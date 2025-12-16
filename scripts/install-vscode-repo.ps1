<#
.SYNOPSIS
    Install VSCode agents to a repository.

.DESCRIPTION
    Wrapper script for backward compatibility.
    Calls the unified install.ps1 with -Environment VSCode -RepoPath.

    DEPRECATED: This script is maintained for backward compatibility.
    Prefer using: .\install.ps1 -Environment VSCode -RepoPath <path>

.PARAMETER RepoPath
    Target repository path. Defaults to current directory.

.PARAMETER Force
    Overwrite existing files without prompting.

.EXAMPLE
    .\install-vscode-repo.ps1
    .\install-vscode-repo.ps1 -RepoPath "C:\Projects\MyRepo"
    .\install-vscode-repo.ps1 -Force
#>

param(
    [string]$RepoPath = (Get-Location).Path,
    [switch]$Force
)

$ErrorActionPreference = "Stop"

# Call unified installer
$InstallScript = Join-Path $PSScriptRoot "install.ps1"
& $InstallScript -Environment VSCode -RepoPath $RepoPath -Force:$Force
