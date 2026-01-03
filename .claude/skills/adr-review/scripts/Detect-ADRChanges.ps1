<#
.SYNOPSIS
    Detects ADR file changes (create, update, delete) for automatic skill triggering.

.DESCRIPTION
    Monitors ADR file patterns in designated directories and detects changes
    since the last check. Returns structured output for skill orchestration.

    Patterns monitored:
    - .agents/architecture/ADR-*.md
    - docs/architecture/ADR-*.md

.PARAMETER BasePath
    The repository root path. Defaults to current directory.

.PARAMETER SinceCommit
    Git commit SHA to compare against. Defaults to HEAD~1.

.PARAMETER IncludeUntracked
    Include untracked new ADR files in detection.

.OUTPUTS
    PSCustomObject with properties:
    - Created: Array of newly created ADR file paths
    - Modified: Array of modified ADR file paths
    - Deleted: Array of deleted ADR file paths
    - HasChanges: Boolean indicating if any changes detected
    - RecommendedAction: Suggested workflow (review/archive/none)

.EXAMPLE
    & .claude/skills/adr-review/scripts/Detect-ADRChanges.ps1

.EXAMPLE
    & .claude/skills/adr-review/scripts/Detect-ADRChanges.ps1 -SinceCommit "abc123"

.NOTES
    Exit codes per ADR-035:
    0 - Success, changes may or may not exist
    1 - Logic or unexpected error
    2 - Config/user error (e.g., invalid commit SHA, missing file)
    3 - External error (e.g., I/O failure, git command failure)
#>
[CmdletBinding()]
param(
    [Parameter()]
    [string]$BasePath = ".",

    [Parameter()]
    [string]$SinceCommit = "HEAD~1",

    [Parameter()]
    [switch]$IncludeUntracked
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

# ADR patterns to monitor
$ADRPatterns = @(
    ".agents/architecture/ADR-*.md",
    "docs/architecture/ADR-*.md"
)

# ADR directories
$ADRDirectories = @(
    ".agents/architecture",
    "docs/architecture"
)

function Get-ADRStatus {
    <#
    .SYNOPSIS
        Extracts status from ADR frontmatter.
    #>
    param([string]$FilePath)

    if (-not (Test-Path $FilePath)) {
        return "unknown"
    }

    $content = Get-Content $FilePath -Raw -ErrorAction SilentlyContinue
    if ($content -match '(?m)^status:\s*(.+)$') {
        return $Matches[1].Trim().ToLower()
    }
    return "proposed"  # Default status
}

function Get-DependentADRs {
    <#
    .SYNOPSIS
        Finds ADRs that reference a given ADR.
    #>
    param([string]$ADRName)

    $dependents = @()
    foreach ($dir in $ADRDirectories) {
        $dirPath = Join-Path $BasePath $dir
        if (Test-Path $dirPath) {
            Get-ChildItem -Path $dirPath -Filter "ADR-*.md" -ErrorAction SilentlyContinue | ForEach-Object {
                $content = Get-Content $_.FullName -Raw -ErrorAction SilentlyContinue
                if ($content -match [regex]::Escape($ADRName)) {
                    $dependents += $_.FullName
                }
            }
        }
    }
    return $dependents
}

try {
    Push-Location $BasePath

    # Verify git repository
    if (-not (Test-Path ".git")) {
        Write-Error "Not a git repository: $BasePath"
        exit 1
    }

    # Get changes from git
    $created = @()
    $modified = @()
    $deleted = @()

    # Check git diff for each pattern
    foreach ($pattern in $ADRPatterns) {
        # Get diff status with error capture
        $diffOutput = git diff --name-status "$SinceCommit" -- $pattern 2>&1
        if ($LASTEXITCODE -ne 0) {
            throw "git diff failed for pattern '$pattern': $diffOutput"
        }

        if ($diffOutput) {
            foreach ($line in $diffOutput -split "`n") {
                if ($line -match '^([AMD])\s+(.+)$') {
                    $status = $Matches[1]
                    $file = $Matches[2]

                    switch ($status) {
                        'A' { $created += $file }
                        'M' { $modified += $file }
                        'D' { $deleted += $file }
                    }
                }
            }
        }
    }

    # Include untracked files if requested
    if ($IncludeUntracked) {
        foreach ($dir in $ADRDirectories) {
            $dirPath = Join-Path $BasePath $dir
            if (Test-Path $dirPath) {
                $untracked = git ls-files --others --exclude-standard -- "$($dir)/ADR-*.md" 2>&1
                if ($LASTEXITCODE -ne 0) {
                    Write-Warning "git ls-files failed for directory '$dir': $untracked"
                    continue  # Non-fatal, continue with other directories
                }
                if ($untracked) {
                    $created += ($untracked -split "`n" | Where-Object { $_ })
                }
            }
        }
    }

    # Remove duplicates and ensure arrays
    $created = @($created | Select-Object -Unique | Where-Object { $_ })
    $modified = @($modified | Select-Object -Unique | Where-Object { $_ })
    $deleted = @($deleted | Select-Object -Unique | Where-Object { $_ })

    # Determine recommended action
    $recommendedAction = "none"
    if ($created.Count -gt 0) {
        $recommendedAction = "review"
    }
    elseif ($modified.Count -gt 0) {
        $recommendedAction = "review"
    }
    elseif ($deleted.Count -gt 0) {
        $recommendedAction = "archive"
    }

    # Build detailed output for deleted files
    $deletedDetails = @()
    foreach ($file in $deleted) {
        $adrName = [System.IO.Path]::GetFileNameWithoutExtension($file)
        $dependents = Get-DependentADRs -ADRName $adrName

        $deletedDetails += [PSCustomObject]@{
            Path       = $file
            ADRName    = $adrName
            Status     = "deleted"
            Dependents = $dependents
        }
    }

    # Build result object
    $result = [PSCustomObject]@{
        Created           = $created
        Modified          = $modified
        Deleted           = $deleted
        DeletedDetails    = $deletedDetails
        HasChanges        = ($created.Count + $modified.Count + $deleted.Count) -gt 0
        RecommendedAction = $recommendedAction
        Timestamp         = Get-Date -Format "o"
        SinceCommit       = $SinceCommit
    }

    # Output as JSON for easy parsing
    $result | ConvertTo-Json -Depth 5

    exit 0
}
catch [System.Management.Automation.ItemNotFoundException] {
    # File or directory not found - config/user error per ADR-035
    Write-Error "Error: File or directory not found: $($_.Exception.Message)"
    exit 2
}
catch [System.IO.IOException] {
    # I/O failure - external error per ADR-035
    Write-Error "Error: I/O failure: $($_.Exception.Message)"
    exit 3
}
catch [System.Management.Automation.CommandNotFoundException] {
    # Missing external command (git) - external error per ADR-035
    Write-Error "Error: External dependency not found (git): $($_.Exception.Message)"
    exit 3
}
catch {
    # Logic or unexpected error per ADR-035
    Write-Error "Error detecting ADR changes: $($_.Exception.Message)"
    exit 1
}
finally {
    Pop-Location
}
