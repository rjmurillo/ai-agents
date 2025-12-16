<#
.SYNOPSIS
    Unified agent installer for Claude, Copilot CLI, and VSCode.

.DESCRIPTION
    Installs AI coding agents to the appropriate location based on environment and scope.
    Supports both global (user-level) and repository-level installations.

.PARAMETER Environment
    Target environment: Claude, Copilot, or VSCode

.PARAMETER Global
    Install to global/user-level location (well-known paths)

.PARAMETER RepoPath
    Install to specified repository path

.PARAMETER Force
    Overwrite existing files without prompting

.EXAMPLE
    .\install.ps1 -Environment Claude -Global
    # Installs Claude agents to ~/.claude/agents

.EXAMPLE
    .\install.ps1 -Environment Copilot -RepoPath "C:\MyRepo"
    # Installs Copilot agents to C:\MyRepo\.github\agents

.EXAMPLE
    .\install.ps1 -Environment VSCode -RepoPath "." -Force
    # Installs VSCode agents to current repo, overwriting existing

.NOTES
    Part of the ai-agents installer consolidation (CVA plan Phase 2).
    Requires Install-Common.psm1 module from scripts/lib directory.
#>

[CmdletBinding()]
param(
    [Parameter(Mandatory)]
    [ValidateSet("Claude", "Copilot", "VSCode")]
    [string]$Environment,

    [Parameter(Mandatory, ParameterSetName = "Global")]
    [switch]$Global,

    [Parameter(Mandatory, ParameterSetName = "Repo")]
    [string]$RepoPath,

    [switch]$Force
)

$ErrorActionPreference = "Stop"

#region Module Loading

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ModulePath = Join-Path $ScriptDir "lib\Install-Common.psm1"

if (-not (Test-Path $ModulePath)) {
    Write-Error "Required module not found: $ModulePath"
    exit 1
}

Import-Module $ModulePath -Force

#endregion

#region Determine Scope and Paths

$Scope = if ($Global) { "Global" } else { "Repo" }

# Resolve RepoPath to absolute path for Repo scope
if ($Scope -eq "Repo") {
    $RepoPath = (Resolve-Path -Path $RepoPath -ErrorAction Stop).Path
}

#endregion

#region Load Configuration

$Config = Get-InstallConfig -Environment $Environment -Scope $Scope

#endregion

#region Resolve Source and Destination Paths

# Source directory is relative to scripts/../src/<env>
$RootDir = Split-Path -Parent $ScriptDir
$SourceDir = Join-Path $RootDir $Config.SourceDir

# Resolve destination path
$DestDir = Resolve-DestinationPath -PathExpression $Config.DestDir -RepoPath $RepoPath

# Resolve instructions file paths (if applicable)
$InstructionsSourcePath = $null
$InstructionsDestPath = $null

if ($Config.InstructionsFile) {
    $InstructionsSourcePath = Join-Path $SourceDir $Config.InstructionsFile
    $InstructionsDestDir = Resolve-DestinationPath -PathExpression $Config.InstructionsDest -RepoPath $RepoPath
    $InstructionsDestPath = Join-Path $InstructionsDestDir $Config.InstructionsFile
}

#endregion

#region Installation Flow

# Display header
$Title = "Installing $($Config.DisplayName) Agents ($Scope)"
Write-InstallHeader -Title $Title

# Validate source directory
Test-SourceDirectory -Path $SourceDir | Out-Null
Write-Host "Source: $SourceDir" -ForegroundColor Gray

# For Repo scope: validate git repository
if ($Scope -eq "Repo") {
    $IsGitRepo = Test-GitRepository -Path $RepoPath -PromptToContinue
    if (-not $IsGitRepo) {
        Write-Host "Installation cancelled." -ForegroundColor Yellow
        exit 0
    }
    Write-Host "Target Repository: $RepoPath" -ForegroundColor Gray
}

Write-Host "Destination: $DestDir" -ForegroundColor Gray
Write-Host ""

# Create destination directory
Initialize-Destination -Path $DestDir -Description "agents" | Out-Null

# Get agent files
$AgentFiles = Get-AgentFiles -SourceDir $SourceDir -FilePattern $Config.FilePattern

if ($AgentFiles.Count -eq 0) {
    Write-Host "No agent files to install." -ForegroundColor Yellow
    exit 0
}

Write-Host "Installing $($AgentFiles.Count) agent files..." -ForegroundColor Cyan
Write-Host ""

# Copy each agent file
$Stats = @{
    Installed = 0
    Updated   = 0
    Skipped   = 0
}

foreach ($File in $AgentFiles) {
    $Status = Copy-AgentFile -File $File -DestDir $DestDir -Force:$Force
    $Stats[$Status]++
}

Write-Host ""

# For Repo scope: create .agents directories
if ($Scope -eq "Repo") {
    Write-Host "Setting up .agents directories..." -ForegroundColor Cyan
    $Created = Initialize-AgentsDirectories -RepoPath $RepoPath -Directories $Config.AgentsDirs

    if ($Created -gt 0) {
        Write-Host "Created $Created agent directories." -ForegroundColor Gray
    }
    else {
        Write-Host "All agent directories already exist." -ForegroundColor Gray
    }
    Write-Host ""
}

# Handle instructions file (if applicable)
if ($InstructionsSourcePath -and (Test-Path $InstructionsSourcePath)) {
    Write-Host "Installing instructions file..." -ForegroundColor Cyan

    $InstructionStatus = Install-InstructionsFile `
        -SourcePath $InstructionsSourcePath `
        -DestPath $InstructionsDestPath `
        -BeginMarker $Config.BeginMarker `
        -EndMarker $Config.EndMarker `
        -Force:$Force
}

# Display completion message (includes known bug warning for Copilot Global)
Write-InstallComplete `
    -Environment $Environment `
    -Scope $Scope `
    -RepoPath $RepoPath `
    -KnownBug $Config.KnownBug

#endregion

#region Summary

Write-Host ""
Write-Host "Summary: $($Stats.Installed) installed, $($Stats.Updated) updated, $($Stats.Skipped) skipped" -ForegroundColor Gray

#endregion
