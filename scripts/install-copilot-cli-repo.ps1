<#
.SYNOPSIS
    Install GitHub Copilot CLI agents to a repository.

.DESCRIPTION
    Wrapper script for backward compatibility.
    Calls the unified install.ps1 with -Environment Copilot -RepoPath.

    DEPRECATED: This script is maintained for backward compatibility.
    Prefer using: .\install.ps1 -Environment Copilot -RepoPath <path>

    Note: This is the recommended installation method. Global installation
    (~/.copilot/agents/) has a known bug (GitHub Issue #452) that prevents
    user-level agents from loading.

.PARAMETER RepoPath
    Target repository path. Defaults to current directory.

.PARAMETER Force
    Overwrite existing files without prompting.

.EXAMPLE
    .\install-copilot-cli-repo.ps1
    .\install-copilot-cli-repo.ps1 -RepoPath "C:\Projects\MyRepo"
    .\install-copilot-cli-repo.ps1 -Force
#>

param(
    [string]$RepoPath = (Get-Location).Path,
    [switch]$Force
)

$ErrorActionPreference = "Stop"

# Call unified installer
$InstallScript = Join-Path $PSScriptRoot "install.ps1"
& $InstallScript -Environment Copilot -RepoPath $RepoPath -Force:$Force
