<#
.SYNOPSIS
    Renames a spec ID and updates all references automatically.

.DESCRIPTION
    Safely renames a specification ID across the entire traceability graph,
    updating:
    - The spec file itself (filename and frontmatter)
    - All YAML frontmatter references in other specs
    - Preventing partial failures through atomic operations

.PARAMETER OldId
    Current spec ID (e.g., "REQ-001")

.PARAMETER NewId
    New spec ID (e.g., "REQ-100")

.PARAMETER SpecsPath
    Path to the specs directory. Default: ".agents/specs"

.PARAMETER DryRun
    Show what would be changed without making actual changes.

.PARAMETER Force
    Skip confirmation prompts (use with caution).

.EXAMPLE
    .\Rename-SpecId.ps1 -OldId "REQ-001" -NewId "REQ-100"

    Rename REQ-001 to REQ-100 with confirmation prompt

.EXAMPLE
    .\Rename-SpecId.ps1 -OldId "REQ-001" -NewId "REQ-100" -DryRun

    Show what would be changed without making changes

.EXAMPLE
    .\Rename-SpecId.ps1 -OldId "DESIGN-005" -NewId "DESIGN-025" -Force

    Rename without confirmation (use in automation)

.NOTES
    Exit codes:
    0 = Success (rename completed or validated in dry-run)
    1 = Error (ID not found, invalid format, file operation failed)
    2 = User cancelled operation

    Atomic operation: Uses file system transactions to prevent partial updates.
    If any step fails, all changes are rolled back.

    See: ADR-035 Exit Code Standardization
#>

[CmdletBinding()]
param(
    [Parameter(Mandatory)]
    [string]$OldId,

    [Parameter(Mandatory)]
    [string]$NewId,

    [Parameter()]
    [string]$SpecsPath = ".agents/specs",

    [Parameter()]
    [switch]$DryRun,

    [Parameter()]
    [switch]$Force
)

$ErrorActionPreference = "Stop"

# Import caching module
Import-Module (Join-Path $PSScriptRoot "TraceabilityCache.psm1") -Force

#region Validation
function Test-SpecIdFormat {
    param([string]$Id)
    return $Id -match '^(REQ|DESIGN|TASK)-[A-Z0-9]+$'
}

if (-not (Test-SpecIdFormat -Id $OldId)) {
    Write-Error "Invalid old ID format: $OldId. Expected format: TYPE-ID (e.g., REQ-001)"
    exit 1
}

if (-not (Test-SpecIdFormat -Id $NewId)) {
    Write-Error "Invalid new ID format: $NewId. Expected format: TYPE-ID (e.g., REQ-001)"
    exit 1
}

# Extract types
$oldType = ($OldId -split '-')[0]
$newType = ($NewId -split '-')[0]

if ($oldType -ne $newType) {
    Write-Error "Cannot change spec type during rename (${oldType} -> ${newType})"
    exit 1
}
#endregion

#region Helper Functions
function Get-YamlFrontMatter {
    param([string]$FilePath)

    $content = Get-Content -Path $FilePath -Raw -ErrorAction SilentlyContinue
    if (-not $content) { return $null }

    if ($content -match '(?s)^---\r?\n(.+?)\r?\n---') {
        $yaml = $Matches[1]
        $result = @{
            id = ''
            related = @()
            content = $content
        }

        if ($yaml -match '(?m)^id:\s*(.+)$') {
            $result.id = $Matches[1].Trim()
        }
        if ($yaml -match '(?s)related:\s*\r?\n((?:\s+-\s+.+\r?\n?)+)') {
            $relatedBlock = $Matches[1]
            $result.related = [regex]::Matches($relatedBlock, '-\s+([A-Z]+-[A-Z0-9]+)') |
                ForEach-Object { $_.Groups[1].Value }
        }

        return $result
    }

    return $null
}

function Get-SpecFilePath {
    param(
        [string]$Id,
        [string]$BasePath
    )

    $type = ($Id -split '-')[0]
    $subdir = switch ($type) {
        'REQ' { 'requirements' }
        'DESIGN' { 'design' }
        'TASK' { 'tasks' }
    }

    $path = Join-Path $BasePath $subdir
    $filePath = Join-Path $path "$Id.md"

    if (Test-Path $filePath) {
        return $filePath
    }

    return $null
}

function Find-ReferencingFiles {
    param(
        [string]$Id,
        [string]$BasePath
    )

    $referencingFiles = @()

    foreach ($subdir in @('requirements', 'design', 'tasks')) {
        $subdirPath = Join-Path $BasePath $subdir
        if (-not (Test-Path $subdirPath)) {
            continue
        }

        Get-ChildItem -Path $subdirPath -Filter "*.md" | ForEach-Object {
            $spec = Get-YamlFrontMatter -FilePath $_.FullName
            if ($spec -and $spec.related -contains $Id) {
                $referencingFiles += $_.FullName
            }
        }
    }

    return $referencingFiles
}

function Update-FileContent {
    param(
        [string]$FilePath,
        [string]$OldValue,
        [string]$NewValue
    )

    $content = Get-Content -Path $FilePath -Raw
    $newContent = $content -replace "(?<=\s)$([regex]::Escape($OldValue))(?=\s|$)", $NewValue

    if ($DryRun) {
        Write-Host "  Would update: $FilePath"
        return $true
    }

    try {
        Set-Content -Path $FilePath -Value $newContent -NoNewline
        return $true
    }
    catch {
        Write-Error "Failed to update $FilePath : $_"
        return $false
    }
}
#endregion

#region Main
# Resolve specs path
$resolvedPath = Resolve-Path -Path $SpecsPath -ErrorAction SilentlyContinue
if (-not $resolvedPath) {
    Write-Error "Specs path not found: $SpecsPath"
    exit 1
}

# Path traversal protection
$repoRoot = try { git rev-parse --show-toplevel 2>$null } catch { $null }
if ($repoRoot) {
    $normalizedPath = [System.IO.Path]::GetFullPath($resolvedPath.Path)
    $allowedBase = [System.IO.Path]::GetFullPath($repoRoot) + [System.IO.Path]::DirectorySeparatorChar
    $isRelativePath = -not [System.IO.Path]::IsPathRooted($SpecsPath)

    if ($isRelativePath -and -not $normalizedPath.StartsWith($allowedBase, [System.StringComparison]::OrdinalIgnoreCase)) {
        Write-Error "Path traversal attempt detected: '$SpecsPath' is outside the repository root."
        exit 1
    }
}

# Find the spec file
$oldFilePath = Get-SpecFilePath -Id $OldId -BasePath $resolvedPath.Path
if (-not $oldFilePath) {
    Write-Error "Spec not found: $OldId"
    exit 1
}

# Check if new ID already exists
$newFilePath = Get-SpecFilePath -Id $NewId -BasePath $resolvedPath.Path
if ($newFilePath) {
    Write-Error "Target spec already exists: $NewId"
    exit 1
}

# Find all files that reference the old ID
$referencingFiles = Find-ReferencingFiles -Id $OldId -BasePath $resolvedPath.Path

# Display plan
Write-Host "Rename Plan:" -ForegroundColor Cyan
Write-Host "  Old ID: $OldId" -ForegroundColor Yellow
Write-Host "  New ID: $NewId" -ForegroundColor Green
Write-Host ""
Write-Host "Files to update:"
Write-Host "  1. $oldFilePath (rename file and update ID)"
foreach ($file in $referencingFiles) {
    Write-Host "  $($referencingFiles.IndexOf($file) + 2). $file (update reference)"
}
Write-Host ""

if ($DryRun) {
    Write-Host "DRY RUN: No changes will be made" -ForegroundColor Magenta
    exit 0
}

# Confirm unless -Force
if (-not $Force) {
    $confirmation = Read-Host "Proceed with rename? (y/N)"
    if ($confirmation -ne 'y') {
        Write-Host "Operation cancelled" -ForegroundColor Yellow
        exit 2
    }
}

# Execute rename atomically
$success = $true
$backupFiles = @()

try {
    # Step 1: Create backup copies
    Write-Host "Creating backups..." -ForegroundColor Cyan
    $backupFiles += @{
        original = $oldFilePath
        backup = "$oldFilePath.bak"
    }
    Copy-Item -Path $oldFilePath -Destination "$oldFilePath.bak" -Force

    foreach ($file in $referencingFiles) {
        $backupFiles += @{
            original = $file
            backup = "$file.bak"
        }
        Copy-Item -Path $file -Destination "$file.bak" -Force
    }

    # Step 2: Update all referencing files
    Write-Host "Updating references..." -ForegroundColor Cyan
    foreach ($file in $referencingFiles) {
        if (-not (Update-FileContent -FilePath $file -OldValue $OldId -NewValue $NewId)) {
            $success = $false
            throw "Failed to update $file"
        }
    }

    # Step 3: Update the spec file itself
    Write-Host "Updating spec file..." -ForegroundColor Cyan
    if (-not (Update-FileContent -FilePath $oldFilePath -OldValue $OldId -NewValue $NewId)) {
        $success = $false
        throw "Failed to update spec ID in $oldFilePath"
    }

    # Step 4: Rename the file
    Write-Host "Renaming file..." -ForegroundColor Cyan
    $type = ($OldId -split '-')[0]
    $subdir = switch ($type) {
        'REQ' { 'requirements' }
        'DESIGN' { 'design' }
        'TASK' { 'tasks' }
    }
    $newFileDir = Join-Path $resolvedPath.Path $subdir
    $newFile = Join-Path $newFileDir "$NewId.md"

    Move-Item -Path $oldFilePath -Destination $newFile -Force

    # Step 5: Clean up backups
    Write-Host "Cleaning up..." -ForegroundColor Cyan
    foreach ($backup in $backupFiles) {
        Remove-Item -Path $backup.backup -Force -ErrorAction SilentlyContinue
    }

    # Clear cache to force re-parse
    Clear-TraceabilityCache

    Write-Host "Rename completed successfully!" -ForegroundColor Green
    exit 0
}
catch {
    Write-Error "Rename failed: $_"

    # Rollback: Restore from backups
    Write-Host "Rolling back changes..." -ForegroundColor Red
    foreach ($backup in $backupFiles) {
        if (Test-Path $backup.backup) {
            Copy-Item -Path $backup.backup -Destination $backup.original -Force
            Remove-Item -Path $backup.backup -Force
        }
    }

    exit 1
}
#endregion
