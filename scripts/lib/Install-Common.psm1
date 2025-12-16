<#
.SYNOPSIS
    Common functions for ai-agents installation scripts.

.DESCRIPTION
    Provides shared functionality for installing Claude, Copilot CLI, and VSCode agents.
    This module is used by install.ps1 and can be imported by legacy scripts.

.NOTES
    Part of the ai-agents installer consolidation (CVA plan Phase 1).
#>

#region Configuration Loading

function Get-InstallConfig {
    <#
    .SYNOPSIS
        Loads and returns configuration for specified environment and scope.

    .PARAMETER Environment
        Target environment: Claude, Copilot, VSCode

    .PARAMETER Scope
        Installation scope: Global, Repo

    .PARAMETER ConfigPath
        Optional path to Config.psd1. Defaults to sibling of this module.

    .OUTPUTS
        [hashtable] Configuration for the specified environment/scope combination.
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)]
        [ValidateSet("Claude", "Copilot", "VSCode")]
        [string]$Environment,

        [Parameter(Mandatory)]
        [ValidateSet("Global", "Repo")]
        [string]$Scope,

        [string]$ConfigPath
    )

    if (-not $ConfigPath) {
        $ModuleDir = Split-Path -Parent $PSCommandPath
        $ConfigPath = Join-Path $ModuleDir "Config.psd1"
    }

    if (-not (Test-Path $ConfigPath)) {
        throw "Configuration file not found: $ConfigPath"
    }

    $Config = Import-PowerShellDataFile -Path $ConfigPath

    # Build combined config for environment/scope
    $EnvConfig = $Config[$Environment]
    if (-not $EnvConfig) {
        throw "Unknown environment: $Environment"
    }

    $ScopeConfig = $EnvConfig[$Scope]
    if (-not $ScopeConfig) {
        throw "Unknown scope '$Scope' for environment '$Environment'"
    }

    # Return merged config
    return @{
        Environment      = $Environment
        Scope            = $Scope
        DisplayName      = $EnvConfig.DisplayName
        SourceDir        = $EnvConfig.SourceDir
        FilePattern      = $EnvConfig.FilePattern
        KnownBug         = $EnvConfig.KnownBug
        DestDir          = $ScopeConfig.DestDir
        InstructionsFile = $ScopeConfig.InstructionsFile
        InstructionsDest = $ScopeConfig.InstructionsDest
        BeginMarker      = $Config._Common.BeginMarker
        EndMarker        = $Config._Common.EndMarker
        AgentsDirs       = $Config._Common.AgentsDirs
    }
}

function Resolve-DestinationPath {
    <#
    .SYNOPSIS
        Resolves path expressions from configuration to actual paths.

    .DESCRIPTION
        Handles variable expansion for paths containing $HOME, $env:APPDATA, etc.
        For Repo scope, combines with RepoPath parameter.

    .PARAMETER PathExpression
        Path expression from config (e.g., '$HOME/.claude/agents', '.github/agents')

    .PARAMETER RepoPath
        Repository path for Repo scope paths.

    .OUTPUTS
        [string] Resolved absolute path.
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)]
        [AllowEmptyString()]
        [string]$PathExpression,

        [string]$RepoPath
    )

    if ([string]::IsNullOrEmpty($PathExpression)) {
        if ($RepoPath) {
            return $RepoPath
        }
        return $null
    }

    # If it's a relative path (doesn't start with $ or drive letter), combine with RepoPath
    if (-not ($PathExpression -match '^(\$|[A-Za-z]:)')) {
        if ($RepoPath) {
            return Join-Path $RepoPath $PathExpression
        }
        return $PathExpression
    }

    # Expand environment variable expressions
    $ResolvedPath = $ExecutionContext.InvokeCommand.ExpandString($PathExpression)

    # Normalize path separators for the current OS
    $ResolvedPath = $ResolvedPath -replace '[/\\]', [System.IO.Path]::DirectorySeparatorChar

    return $ResolvedPath
}

#endregion

#region Source Validation

function Test-SourceDirectory {
    <#
    .SYNOPSIS
        Validates that source directory exists.

    .PARAMETER Path
        Path to the source directory.

    .OUTPUTS
        [bool] True if directory exists, throws error otherwise.
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)]
        [string]$Path
    )

    if (-not (Test-Path $Path -PathType Container)) {
        throw "Source directory not found: $Path"
    }

    return $true
}

function Get-AgentFiles {
    <#
    .SYNOPSIS
        Returns agent files matching the specified pattern.

    .PARAMETER SourceDir
        Path to the source directory.

    .PARAMETER FilePattern
        File pattern to match (e.g., '*.md', '*.agent.md')

    .PARAMETER ExcludeFiles
        Array of filenames to exclude from results (e.g., instruction files).

    .OUTPUTS
        [System.IO.FileInfo[]] Array of matching files.
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)]
        [string]$SourceDir,

        [Parameter(Mandatory)]
        [string]$FilePattern,

        [string[]]$ExcludeFiles = @()
    )

    $Files = Get-ChildItem -Path $SourceDir -Filter $FilePattern -File

    # Exclude specified files (e.g., instruction files that match the pattern)
    if ($ExcludeFiles.Count -gt 0) {
        $Files = $Files | Where-Object { $_.Name -notin $ExcludeFiles }
    }

    if ($Files.Count -eq 0) {
        Write-Warning "No agent files found matching '$FilePattern' in: $SourceDir"
    }

    return $Files
}

#endregion

#region Destination Management

function Initialize-Destination {
    <#
    .SYNOPSIS
        Creates destination directory if it doesn't exist.

    .PARAMETER Path
        Path to the destination directory.

    .PARAMETER Description
        Human-readable description for output messages.

    .OUTPUTS
        [bool] True if created, false if already existed.
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)]
        [string]$Path,

        [string]$Description = "destination"
    )

    if (-not (Test-Path $Path)) {
        Write-Host "Creating $Description directory..." -ForegroundColor Yellow
        New-Item -ItemType Directory -Path $Path -Force | Out-Null
        return $true
    }

    return $false
}

function Test-GitRepository {
    <#
    .SYNOPSIS
        Validates that path is a git repository.

    .PARAMETER Path
        Path to check for .git directory.

    .PARAMETER PromptToContinue
        If true, prompts user to continue if not a git repository.

    .OUTPUTS
        [bool] True if is a git repository or user chose to continue.
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)]
        [string]$Path,

        [switch]$PromptToContinue
    )

    $GitDir = Join-Path $Path ".git"

    if (Test-Path $GitDir) {
        return $true
    }

    Write-Warning "Target path does not appear to be a git repository: $Path"

    if ($PromptToContinue) {
        $Response = Read-Host "Continue anyway? (y/N)"
        if ($Response -eq 'y' -or $Response -eq 'Y') {
            return $true
        }
        return $false
    }

    return $false
}

function Initialize-AgentsDirectories {
    <#
    .SYNOPSIS
        Creates .agents subdirectories with .gitkeep files.

    .PARAMETER RepoPath
        Path to the repository root.

    .PARAMETER Directories
        Array of relative directory paths to create.

    .OUTPUTS
        [int] Number of directories created.
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)]
        [string]$RepoPath,

        [Parameter(Mandatory)]
        [string[]]$Directories
    )

    $Created = 0

    foreach ($Dir in $Directories) {
        $FullPath = Join-Path $RepoPath $Dir

        if (-not (Test-Path $FullPath)) {
            New-Item -ItemType Directory -Path $FullPath -Force | Out-Null

            # Create .gitkeep to preserve empty directories in git
            $GitKeep = Join-Path $FullPath ".gitkeep"
            "" | Out-File -FilePath $GitKeep -Encoding utf8

            Write-Host "  Created $Dir" -ForegroundColor Green
            $Created++
        }
    }

    return $Created
}

#endregion

#region File Operations

function Copy-AgentFile {
    <#
    .SYNOPSIS
        Copies a single agent file with overwrite handling.

    .PARAMETER File
        FileInfo object for the source file.

    .PARAMETER DestDir
        Destination directory path.

    .PARAMETER Force
        Skip overwrite prompting.

    .OUTPUTS
        [string] Status: "Installed", "Updated", or "Skipped"
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)]
        [System.IO.FileInfo]$File,

        [Parameter(Mandatory)]
        [string]$DestDir,

        [switch]$Force
    )

    $DestPath = Join-Path $DestDir $File.Name
    $Exists = Test-Path $DestPath

    if ($Exists -and -not $Force) {
        $Response = Read-Host "  $($File.Name) exists. Overwrite? (y/N)"
        if ($Response -ne 'y' -and $Response -ne 'Y') {
            Write-Host "  Skipping $($File.Name)" -ForegroundColor Yellow
            return "Skipped"
        }
    }

    Copy-Item -Path $File.FullName -Destination $DestPath -Force
    $Status = if ($Exists) { "Updated" } else { "Installed" }
    Write-Host "  $Status $($File.Name)" -ForegroundColor Green
    return $Status
}

function Install-InstructionsFile {
    <#
    .SYNOPSIS
        Installs or updates an instructions file with upgradeable content blocks.

    .DESCRIPTION
        Uses markdown-compatible HTML comments (BEGIN/END markers) to create
        upgradeable content blocks. On first install, appends the block.
        On subsequent runs, replaces the existing block content (upgrade).

    .PARAMETER SourcePath
        Path to source instructions file.

    .PARAMETER DestPath
        Destination path for instructions file.

    .PARAMETER BeginMarker
        HTML comment marking start of managed content block.

    .PARAMETER EndMarker
        HTML comment marking end of managed content block.

    .PARAMETER Force
        Replace entire file instead of using content blocks.

    .OUTPUTS
        [string] Status: "Installed", "Upgraded", "Appended", "Replaced", or "NotFound"
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)]
        [string]$SourcePath,

        [Parameter(Mandatory)]
        [string]$DestPath,

        [string]$BeginMarker = "<!-- BEGIN: ai-agents installer -->",
        [string]$EndMarker = "<!-- END: ai-agents installer -->",

        [switch]$Force
    )

    if (-not (Test-Path $SourcePath)) {
        Write-Warning "Instructions file not found: $SourcePath"
        return "NotFound"
    }

    $NewContent = Get-Content -Path $SourcePath -Raw
    $DestExists = Test-Path $DestPath

    # Ensure destination directory exists
    $DestDir = Split-Path -Parent $DestPath
    if ($DestDir -and -not (Test-Path $DestDir)) {
        New-Item -ItemType Directory -Path $DestDir -Force | Out-Null
    }

    if ($DestExists -and -not $Force) {
        $ExistingContent = Get-Content -Path $DestPath -Raw

        if ($ExistingContent -match [regex]::Escape($BeginMarker)) {
            # Upgrade: Replace existing content block
            $Pattern = "(?s)$([regex]::Escape($BeginMarker)).*?$([regex]::Escape($EndMarker))"
            $Replacement = "$BeginMarker`n$NewContent`n$EndMarker"
            $UpdatedContent = $ExistingContent -replace $Pattern, $Replacement
            Set-Content -Path $DestPath -Value $UpdatedContent -Encoding utf8 -NoNewline
            Write-Host "  Upgraded existing ai-agents content block" -ForegroundColor Green
            return "Upgraded"
        }
        else {
            # First install: Append content block
            Add-Content -Path $DestPath -Value "`n`n$BeginMarker`n" -Encoding utf8 -NoNewline
            Add-Content -Path $DestPath -Value $NewContent -Encoding utf8 -NoNewline
            Add-Content -Path $DestPath -Value "`n$EndMarker`n" -Encoding utf8 -NoNewline
            Write-Host "  Appended ai-agents content block" -ForegroundColor Green
            return "Appended"
        }
    }
    else {
        # New file or Force: Write with content block wrapper
        $WrappedContent = "$BeginMarker`n$NewContent`n$EndMarker`n"
        Set-Content -Path $DestPath -Value $WrappedContent -Encoding utf8 -NoNewline
        $Status = if ($DestExists) { "Replaced" } else { "Installed" }
        Write-Host "  $Status instructions file" -ForegroundColor Green
        return $Status
    }
}

#endregion

#region Output Formatting

function Write-InstallHeader {
    <#
    .SYNOPSIS
        Writes consistent installation header.

    .PARAMETER Title
        Title text for the header.
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)]
        [string]$Title
    )

    $Separator = "=" * $Title.Length
    Write-Host $Title -ForegroundColor Cyan
    Write-Host $Separator -ForegroundColor Cyan
    Write-Host ""
}

function Write-InstallComplete {
    <#
    .SYNOPSIS
        Writes consistent completion message.

    .PARAMETER Environment
        The environment that was installed (Claude, Copilot, VSCode).

    .PARAMETER Scope
        The installation scope (Global, Repo).

    .PARAMETER RepoPath
        Repository path (for Repo scope).

    .PARAMETER KnownBug
        Known bug information hashtable (optional).
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)]
        [string]$Environment,

        [Parameter(Mandatory)]
        [ValidateSet("Global", "Repo")]
        [string]$Scope,

        [string]$RepoPath,

        [hashtable]$KnownBug
    )

    Write-Host ""
    Write-Host "Installation complete!" -ForegroundColor Cyan

    if ($Scope -eq "Global") {
        Write-Host "Agents are now available globally." -ForegroundColor Cyan
    }
    else {
        Write-Host "Agents are now available in this repository." -ForegroundColor Cyan
    }

    Write-Host ""

    # Show known bug warning if applicable
    if ($KnownBug -and $Scope -eq "Global") {
        Write-Host "WARNING: Known Bug $($KnownBug.Id)" -ForegroundColor Yellow
        Write-Host "  $($KnownBug.Description)" -ForegroundColor Yellow
        if ($KnownBug.Url) {
            Write-Host "  See: $($KnownBug.Url)" -ForegroundColor Yellow
        }
        Write-Host ""
    }

    # Environment-specific restart/usage instructions
    switch ($Environment) {
        "Claude" {
            Write-Host "IMPORTANT: Restart Claude Code to load new agents." -ForegroundColor Yellow
            Write-Host ""
            Write-Host "Usage: Task(subagent_type='agent-name', prompt='...')" -ForegroundColor Gray
        }
        "Copilot" {
            Write-Host "Usage:" -ForegroundColor Gray
            Write-Host "  copilot --agent analyst --prompt 'your task'" -ForegroundColor Gray
            Write-Host "  copilot --agent implementer --prompt 'implement feature X'" -ForegroundColor Gray
            Write-Host ""
            Write-Host "Interactive mode:" -ForegroundColor Gray
            Write-Host "  copilot" -ForegroundColor Gray
            Write-Host "  /agent analyst" -ForegroundColor Gray
        }
        "VSCode" {
            Write-Host "IMPORTANT: Restart VS Code to load new agents." -ForegroundColor Yellow
            Write-Host ""
            Write-Host "Usage: @workspace /agent-name 'your prompt'" -ForegroundColor Gray
        }
    }

    # Commit guidance for Repo scope
    if ($Scope -eq "Repo") {
        Write-Host ""
        Write-Host "Remember to commit the new files:" -ForegroundColor Gray

        switch ($Environment) {
            "Claude" {
                Write-Host "  git add .claude CLAUDE.md .agents" -ForegroundColor Gray
                Write-Host "  git commit -m 'feat(agents): add Claude agent system'" -ForegroundColor Gray
            }
            "Copilot" {
                Write-Host "  git add .github/agents .agents" -ForegroundColor Gray
                Write-Host "  git commit -m 'feat(agents): add Copilot CLI agent system'" -ForegroundColor Gray
            }
            "VSCode" {
                Write-Host "  git add .github/agents .agents" -ForegroundColor Gray
                Write-Host "  git commit -m 'feat(agents): add VS Code agent system'" -ForegroundColor Gray
            }
        }
    }
}

#endregion

#region Module Exports

# Export all public functions
Export-ModuleMember -Function @(
    'Get-InstallConfig'
    'Resolve-DestinationPath'
    'Test-SourceDirectory'
    'Get-AgentFiles'
    'Initialize-Destination'
    'Test-GitRepository'
    'Initialize-AgentsDirectories'
    'Copy-AgentFile'
    'Install-InstructionsFile'
    'Write-InstallHeader'
    'Write-InstallComplete'
)

#endregion
