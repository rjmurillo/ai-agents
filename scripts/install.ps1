<#
.SYNOPSIS
    Unified agent installer for Claude, Copilot CLI, and VSCode.

.DESCRIPTION
    Installs AI coding agents to the appropriate location based on environment and scope.
    Supports both global (user-level) and repository-level installations.
    Can be invoked remotely via iex (Invoke-Expression) for easy installation.

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

.EXAMPLE
    # Remote installation (interactive mode):
    Set-ExecutionPolicy Bypass -Scope Process -Force; iex ((New-Object System.Net.WebClient).DownloadString('https://raw.githubusercontent.com/rjmurillo/ai-agents/main/scripts/install.ps1'))

.NOTES
    Part of the ai-agents installer consolidation (CVA plan Phase 4).
    Supports both local and remote execution via iex.
    Requires Install-Common.psm1 module from scripts/lib directory.
#>

[CmdletBinding()]
param(
    [ValidateSet("Claude", "Copilot", "VSCode")]
    [string]$Environment,

    [switch]$Global,

    [string]$RepoPath,

    [switch]$Force
)

$ErrorActionPreference = "Stop"

#region Remote Execution Detection and Bootstrap

# Detect execution context: $PSScriptRoot is empty when running via iex
$IsRemoteExecution = -not $PSScriptRoot

if ($IsRemoteExecution) {
    # Bootstrap: Download required files to temp directory
    $TempDir = Join-Path $env:TEMP "ai-agents-install-$(Get-Random)"
    New-Item -ItemType Directory -Path $TempDir -Force | Out-Null

    $BaseUrl = "https://raw.githubusercontent.com/rjmurillo/ai-agents/main"

    Write-Host ""
    Write-Host "AI Agents Installer (Remote)" -ForegroundColor Cyan
    Write-Host "============================" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "Downloading installer components..." -ForegroundColor Gray

    try {
        # Create lib directory structure
        $LibDir = Join-Path $TempDir "lib"
        New-Item -ItemType Directory -Path $LibDir -Force | Out-Null

        # Download module and config using WebClient for compatibility
        $WebClient = New-Object System.Net.WebClient
        $WebClient.DownloadFile("$BaseUrl/scripts/lib/Install-Common.psm1", "$LibDir/Install-Common.psm1")
        $WebClient.DownloadFile("$BaseUrl/scripts/lib/Config.psd1", "$LibDir/Config.psd1")

        Write-Host "  Downloaded Install-Common.psm1" -ForegroundColor Green
        Write-Host "  Downloaded Config.psd1" -ForegroundColor Green
    }
    catch {
        Write-Error "Failed to download installer components: $_"
        if (Test-Path $TempDir) {
            Remove-Item -Path $TempDir -Recurse -Force -ErrorAction SilentlyContinue
        }
        exit 1
    }

    $ScriptRoot = $TempDir
}
else {
    $ScriptRoot = $PSScriptRoot
}

#endregion

#region Interactive Mode (for parameter-less invocation)

if (-not $Environment) {
    Write-Host ""
    Write-Host "AI Agents Installer" -ForegroundColor Cyan
    Write-Host "===================" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "Select Environment:" -ForegroundColor Yellow
    Write-Host "  1. Claude Code"
    Write-Host "  2. GitHub Copilot CLI"
    Write-Host "  3. VS Code / Copilot Chat"
    Write-Host ""
    $choice = Read-Host "Enter choice (1-3)"
    $Environment = switch ($choice) {
        "1" { "Claude" }
        "2" { "Copilot" }
        "3" { "VSCode" }
        default {
            Write-Error "Invalid choice: $choice. Please enter 1, 2, or 3."
            if ($IsRemoteExecution -and (Test-Path $TempDir)) {
                Remove-Item -Path $TempDir -Recurse -Force -ErrorAction SilentlyContinue
            }
            exit 1
        }
    }
}

if (-not $Global -and -not $RepoPath) {
    Write-Host ""
    Write-Host "Select Scope:" -ForegroundColor Yellow
    Write-Host "  1. Global (all projects - user-level installation)"
    Write-Host "  2. Repository (specific project)"
    Write-Host ""
    $choice = Read-Host "Enter choice (1-2)"
    if ($choice -eq "1") {
        $Global = $true
    }
    elseif ($choice -eq "2") {
        $RepoPath = Read-Host "Enter repository path (or press Enter for current directory)"
        if (-not $RepoPath) {
            $RepoPath = (Get-Location).Path
        }
    }
    else {
        Write-Error "Invalid choice: $choice. Please enter 1 or 2."
        if ($IsRemoteExecution -and (Test-Path $TempDir)) {
            Remove-Item -Path $TempDir -Recurse -Force -ErrorAction SilentlyContinue
        }
        exit 1
    }
}

#endregion

#region Module Loading

$ModulePath = Join-Path $ScriptRoot "lib\Install-Common.psm1"

if (-not (Test-Path $ModulePath)) {
    Write-Error "Required module not found: $ModulePath"
    if ($IsRemoteExecution -and (Test-Path $TempDir)) {
        Remove-Item -Path $TempDir -Recurse -Force -ErrorAction SilentlyContinue
    }
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

#region Download Source Files (Remote Execution)

if ($IsRemoteExecution) {
    # Create source directory structure in temp
    $SourceDir = Join-Path $ScriptRoot $Config.SourceDir
    New-Item -ItemType Directory -Path $SourceDir -Force | Out-Null

    Write-Host ""
    Write-Host "Downloading $($Config.DisplayName) agents..." -ForegroundColor Gray

    try {
        # Get file list from GitHub API
        $ApiUrl = "https://api.github.com/repos/rjmurillo/ai-agents/contents/$($Config.SourceDir)"

        # Use Invoke-RestMethod with appropriate headers
        $Headers = @{
            "User-Agent" = "ai-agents-installer"
            "Accept"     = "application/vnd.github.v3+json"
        }

        $Files = Invoke-RestMethod -Uri $ApiUrl -Headers $Headers -ErrorAction Stop

        # Filter files by pattern
        $PatternRegex = "^" + ($Config.FilePattern -replace "\*", ".*" -replace "\.", "\.") + "$"
        $MatchingFiles = $Files | Where-Object { $_.name -match $PatternRegex -and $_.type -eq "file" }

        if ($MatchingFiles.Count -eq 0) {
            Write-Warning "No agent files found matching pattern: $($Config.FilePattern)"
        }

        foreach ($File in $MatchingFiles) {
            $DestFile = Join-Path $SourceDir $File.name
            $WebClient.DownloadFile($File.download_url, $DestFile)
            Write-Host "  Downloaded $($File.name)" -ForegroundColor Green
        }

        # Download instructions file if applicable
        if ($Config.InstructionsFile) {
            $InstructionsUrl = "$BaseUrl/$($Config.SourceDir)/$($Config.InstructionsFile)"
            $InstructionsLocal = Join-Path $SourceDir $Config.InstructionsFile

            try {
                $WebClient.DownloadFile($InstructionsUrl, $InstructionsLocal)
                Write-Host "  Downloaded $($Config.InstructionsFile)" -ForegroundColor Green
            }
            catch {
                Write-Host "  Note: Instructions file not found (optional)" -ForegroundColor Yellow
            }
        }
    }
    catch {
        Write-Error "Failed to download agent files: $_"
        Remove-Item -Path $TempDir -Recurse -Force -ErrorAction SilentlyContinue
        exit 1
    }
}
else {
    # Local execution: Source directory is relative to scripts/../src/<env>
    $RootDir = Split-Path -Parent $ScriptRoot
    $SourceDir = Join-Path $RootDir $Config.SourceDir
}

#endregion

#region Resolve Source and Destination Paths

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

# Get agent files (excluding instruction files that may match the pattern)
$ExcludeFiles = @()
if ($Config.InstructionsFile) {
    $ExcludeFiles += $Config.InstructionsFile
}
$AgentFiles = Get-AgentFiles -SourceDir $SourceDir -FilePattern $Config.FilePattern -ExcludeFiles $ExcludeFiles

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

# Install command files (if configured)
if ($Config.CommandsDir -and $Config.CommandFiles -and $Config.CommandFiles.Count -gt 0) {
    Write-Host "Installing Claude commands..." -ForegroundColor Cyan

    $CommandsDir = Resolve-DestinationPath -PathExpression $Config.CommandsDir -RepoPath $RepoPath

    $CommandStats = Install-CommandFiles `
        -SourceDir $SourceDir `
        -CommandsDir $CommandsDir `
        -CommandFiles $Config.CommandFiles `
        -Force:$Force

    Write-Host ""
    Write-Host "Commands: $($CommandStats.Installed) installed, $($CommandStats.Updated) updated, $($CommandStats.Skipped) skipped" -ForegroundColor Gray
    Write-Host ""
}

# Install prompt files (if configured) - copies .agent.md files as .prompt.md
if ($Config.PromptFiles -and $Config.PromptFiles.Count -gt 0) {
    Write-Host "Installing prompt files..." -ForegroundColor Cyan

    $PromptStats = Install-PromptFiles `
        -SourceDir $SourceDir `
        -DestDir $DestDir `
        -PromptFiles $Config.PromptFiles `
        -Force:$Force

    Write-Host ""
    Write-Host "Prompts: $($PromptStats.Installed) installed, $($PromptStats.Updated) updated, $($PromptStats.Skipped) skipped" -ForegroundColor Gray
    Write-Host ""
}

# Install skills (if configured) - Claude-specific PowerShell modules
if ($Config.Skills -and $Config.Skills.Count -gt 0 -and $Config.SkillsDir) {
    Write-Host "Installing skills..." -ForegroundColor Cyan

    # Resolve skills source and destination paths
    $SkillsSourceDir = if ($IsRemoteExecution) {
        # For remote: skills need to be downloaded separately
        Write-Host "  Note: Skills require local installation (not available via remote)" -ForegroundColor Yellow
        $null
    }
    else {
        Join-Path $RootDir $Config.SkillsSourceDir
    }

    if ($SkillsSourceDir -and (Test-Path $SkillsSourceDir)) {
        $SkillsDestDir = Resolve-DestinationPath -PathExpression $Config.SkillsDir -RepoPath $RepoPath

        $SkillStats = Install-SkillFiles `
            -SourceDir $SkillsSourceDir `
            -SkillsDir $SkillsDestDir `
            -Skills $Config.Skills `
            -Force:$Force

        Write-Host ""
        Write-Host "Skills: $($SkillStats.Installed) installed, $($SkillStats.Updated) updated, $($SkillStats.Skipped) skipped" -ForegroundColor Gray
        Write-Host ""
    }
}

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

#region Cleanup (Remote Execution)

if ($IsRemoteExecution -and (Test-Path $TempDir)) {
    # Clean up temp directory
    Remove-Item -Path $TempDir -Recurse -Force -ErrorAction SilentlyContinue
    Write-Host ""
    Write-Host "Cleaned up temporary files." -ForegroundColor Gray
}

#endregion
