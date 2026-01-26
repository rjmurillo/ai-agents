<#
.SYNOPSIS
    Bulk update spec references in the traceability graph.

.DESCRIPTION
    Updates multiple spec references in one atomic operation. Useful for:
    - Replacing all references to an old spec with a new one
    - Adding a new reference to multiple specs
    - Removing a reference from multiple specs

.PARAMETER SourceId
    The spec ID whose references will be updated (e.g., "DESIGN-001")

.PARAMETER AddReferences
    Array of spec IDs to add to the related list

.PARAMETER RemoveReferences
    Array of spec IDs to remove from the related list

.PARAMETER ReplaceReference
    Hashtable with 'Old' and 'New' keys for replacing a single reference

.PARAMETER SpecsPath
    Path to the specs directory. Default: ".agents/specs"

.PARAMETER DryRun
    Show what would be changed without making actual changes.

.PARAMETER Force
    Skip confirmation prompts (use with caution).

.EXAMPLE
    .\Update-SpecReferences.ps1 -SourceId "DESIGN-001" -AddReferences @("REQ-005", "REQ-006")

    Add REQ-005 and REQ-006 to DESIGN-001's related list

.EXAMPLE
    .\Update-SpecReferences.ps1 -SourceId "TASK-010" -RemoveReferences @("DESIGN-002") -DryRun

    Show what would be removed without making changes

.EXAMPLE
    .\Update-SpecReferences.ps1 -SourceId "DESIGN-003" -ReplaceReference @{Old="REQ-001"; New="REQ-100"}

    Replace REQ-001 with REQ-100 in DESIGN-003's references

.NOTES
    Exit codes:
    0 = Success (update completed or validated in dry-run)
    1 = Error (ID not found, invalid format, file operation failed)
    2 = User cancelled operation

    Atomic operation: All changes are applied together or not at all.
    If any validation fails, no changes are made.

    See: ADR-035 Exit Code Standardization
#>

[CmdletBinding(DefaultParameterSetName='Add')]
param(
    [Parameter(Mandatory)]
    [string]$SourceId,

    [Parameter(ParameterSetName='Add')]
    [string[]]$AddReferences = @(),

    [Parameter(ParameterSetName='Remove')]
    [string[]]$RemoveReferences = @(),

    [Parameter(ParameterSetName='Replace')]
    [hashtable]$ReplaceReference,

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

if (-not (Test-SpecIdFormat -Id $SourceId)) {
    Write-Error "Invalid source ID format: $SourceId"
    exit 1
}

# Validate add references
foreach ($id in $AddReferences) {
    if (-not (Test-SpecIdFormat -Id $id)) {
        Write-Error "Invalid reference ID format: $id"
        exit 1
    }
}

# Validate remove references
foreach ($id in $RemoveReferences) {
    if (-not (Test-SpecIdFormat -Id $id)) {
        Write-Error "Invalid reference ID format: $id"
        exit 1
    }
}

# Validate replace reference
if ($ReplaceReference) {
    if (-not $ReplaceReference.Old -or -not $ReplaceReference.New) {
        Write-Error "ReplaceReference must have 'Old' and 'New' keys"
        exit 1
    }
    if (-not (Test-SpecIdFormat -Id $ReplaceReference.Old)) {
        Write-Error "Invalid old reference ID format: $($ReplaceReference.Old)"
        exit 1
    }
    if (-not (Test-SpecIdFormat -Id $ReplaceReference.New)) {
        Write-Error "Invalid new reference ID format: $($ReplaceReference.New)"
        exit 1
    }
}
#endregion

#region Helper Functions
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

function Get-YamlFrontMatter {
    param([string]$FilePath)

    $content = Get-Content -Path $FilePath -Raw -ErrorAction SilentlyContinue
    if (-not $content) { return $null }

    if ($content -match '(?s)^(---\r?\n.+?\r?\n---\r?\n)(.*)$') {
        $frontmatter = $Matches[1]
        $body = $Matches[2]

        $yaml = $frontmatter -replace '^---\r?\n', '' -replace '\r?\n---\r?\n$', ''
        $related = @()

        if ($yaml -match '(?s)related:\s*\r?\n((?:\s+-\s+.+\r?\n?)+)') {
            $relatedBlock = $Matches[1]
            $related = [regex]::Matches($relatedBlock, '-\s+([A-Z]+-[A-Z0-9]+)') |
                ForEach-Object { $_.Groups[1].Value }
        }

        return @{
            frontmatter = $frontmatter
            body = $body
            related = $related
            content = $content
        }
    }

    return $null
}

function Update-YamlReferences {
    param(
        [string]$FilePath,
        [string[]]$CurrentReferences,
        [string[]]$NewReferences
    )

    $content = Get-Content -Path $FilePath -Raw

    # Build new related block
    $relatedBlock = "related:`r`n"
    foreach ($ref in ($NewReferences | Sort-Object)) {
        $relatedBlock += "  - $ref`r`n"
    }

    # Replace the related block
    if ($content -match '(?s)(^---\r?\n.+?)related:\s*\r?\n(?:\s+-\s+.+\r?\n?)+(.+---\r?\n.*)$') {
        $before = $Matches[1]
        $after = $Matches[2]
        $newContent = "${before}${relatedBlock}${after}"
    }
    else {
        # No existing related block - add before closing ---
        if ($content -match '(?s)(^---\r?\n.+?)(\r?\n---\r?\n.*)$') {
            $before = $Matches[1]
            $after = $Matches[2]
            $newContent = "${before}`r`n${relatedBlock}${after}"
        }
        else {
            Write-Error "Could not parse YAML frontmatter in $FilePath"
            return $false
        }
    }

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

# Find the source spec file
$sourceFile = Get-SpecFilePath -Id $SourceId -BasePath $resolvedPath.Path
if (-not $sourceFile) {
    Write-Error "Source spec not found: $SourceId"
    exit 1
}

# Parse current references
$spec = Get-YamlFrontMatter -FilePath $sourceFile
if (-not $spec) {
    Write-Error "Could not parse spec file: $sourceFile"
    exit 1
}

$currentRefs = [System.Collections.ArrayList]::new()
foreach ($ref in $spec.related) {
    [void]$currentRefs.Add($ref)
}

# Calculate new references based on operation
$newRefs = [System.Collections.ArrayList]::new()
foreach ($ref in $currentRefs) {
    [void]$newRefs.Add($ref)
}

if ($AddReferences.Count -gt 0) {
    $operation = "Add"
    foreach ($ref in $AddReferences) {
        if (-not $newRefs.Contains($ref)) {
            [void]$newRefs.Add($ref)
        }
    }
}
elseif ($RemoveReferences.Count -gt 0) {
    $operation = "Remove"
    foreach ($ref in $RemoveReferences) {
        [void]$newRefs.Remove($ref)
    }
}
elseif ($ReplaceReference) {
    $operation = "Replace"
    $oldRef = $ReplaceReference.Old
    $newRef = $ReplaceReference.New

    if (-not $currentRefs.Contains($oldRef)) {
        Write-Error "Reference to replace not found: $oldRef in $SourceId"
        exit 1
    }

    [void]$newRefs.Remove($oldRef)
    if (-not $newRefs.Contains($newRef)) {
        [void]$newRefs.Add($newRef)
    }
}
else {
    Write-Error "No operation specified (use -AddReferences, -RemoveReferences, or -ReplaceReference)"
    exit 1
}

# Display plan
Write-Host "Update Plan:" -ForegroundColor Cyan
Write-Host "  Operation: $operation" -ForegroundColor Yellow
Write-Host "  Source: $SourceId" -ForegroundColor Yellow
Write-Host ""
Write-Host "Current references:" -ForegroundColor Cyan
foreach ($ref in ($currentRefs | Sort-Object)) {
    Write-Host "  - $ref"
}
Write-Host ""
Write-Host "New references:" -ForegroundColor Green
foreach ($ref in ($newRefs | Sort-Object)) {
    $marker = if ($currentRefs.Contains($ref)) { "" } else { " (NEW)" }
    Write-Host "  - $ref$marker" -ForegroundColor Green
}

# Check for removed references
foreach ($ref in $currentRefs) {
    if (-not $newRefs.Contains($ref)) {
        Write-Host "  Removing: $ref" -ForegroundColor Red
    }
}
Write-Host ""

if ($DryRun) {
    Write-Host "DRY RUN: No changes will be made" -ForegroundColor Magenta
    exit 0
}

# Confirm unless -Force
if (-not $Force) {
    $confirmation = Read-Host "Proceed with update? (y/N)"
    if ($confirmation -ne 'y') {
        Write-Host "Operation cancelled" -ForegroundColor Yellow
        exit 2
    }
}

# Execute update atomically
try {
    # Create backup
    Write-Host "Creating backup..." -ForegroundColor Cyan
    Copy-Item -Path $sourceFile -Destination "$sourceFile.bak" -Force

    # Update references
    Write-Host "Updating references..." -ForegroundColor Cyan
    if (-not (Update-YamlReferences -FilePath $sourceFile -CurrentReferences $currentRefs -NewReferences $newRefs)) {
        throw "Failed to update references"
    }

    # Clean up backup
    Write-Host "Cleaning up..." -ForegroundColor Cyan
    Remove-Item -Path "$sourceFile.bak" -Force -ErrorAction SilentlyContinue

    # Clear cache
    Clear-TraceabilityCache

    Write-Host "Update completed successfully!" -ForegroundColor Green
    exit 0
}
catch {
    Write-Error "Update failed: $_"

    # Rollback
    Write-Host "Rolling back changes..." -ForegroundColor Red
    if (Test-Path "$sourceFile.bak") {
        Copy-Item -Path "$sourceFile.bak" -Destination $sourceFile -Force
        Remove-Item -Path "$sourceFile.bak" -Force
    }

    exit 1
}
#endregion
