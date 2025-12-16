<#
.SYNOPSIS
    Install Claude Code agents to a repository.

.DESCRIPTION
    Wrapper script for backward compatibility.
    Calls the unified install.ps1 with -Environment Claude -RepoPath.

    DEPRECATED: This script is maintained for backward compatibility.
    Prefer using: .\install.ps1 -Environment Claude -RepoPath <path>

.PARAMETER RepoPath
    Target repository path. Defaults to current directory.

.PARAMETER Force
    Overwrite existing files without prompting.

.EXAMPLE
    .\install-claude-repo.ps1
    .\install-claude-repo.ps1 -RepoPath "C:\Projects\MyRepo"
    .\install-claude-repo.ps1 -Force
#>

param(
    [string]$RepoPath = (Get-Location).Path,
    [switch]$Force
)

$ErrorActionPreference = "Stop"

# Call unified installer
$InstallScript = Join-Path $PSScriptRoot "install.ps1"
& $InstallScript -Environment Claude -RepoPath $RepoPath -Force:$Force
