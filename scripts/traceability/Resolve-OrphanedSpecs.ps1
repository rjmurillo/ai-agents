<#
.SYNOPSIS
    Identifies and helps resolve orphaned specs in the traceability graph.

.DESCRIPTION
    Scans the traceability graph to find orphaned specifications:
    - Requirements with no designs referencing them
    - Designs with no requirements or no tasks referencing them
    - Tasks with no design references

    Provides options to resolve orphans through linking, deletion, or archival.

.PARAMETER SpecsPath
    Path to the specs directory. Default: ".agents/specs"

.PARAMETER Action
    Action to take on orphans:
    - list: Show all orphaned specs (default)
    - link: Interactive wizard to create missing links
    - archive: Move orphaned specs to an archive folder
    - delete: Delete orphaned specs (requires -Force)

.PARAMETER Type
    Filter by spec type: "all", "requirements", "designs", "tasks"
    Default: "all"

.PARAMETER DryRun
    Show what would be changed without making actual changes.

.PARAMETER Force
    Skip confirmation prompts (use with caution).

.PARAMETER NoCache
    Bypass cache and force full re-parse of all spec files.

.EXAMPLE
    .\Resolve-OrphanedSpecs.ps1

    List all orphaned specs

.EXAMPLE
    .\Resolve-OrphanedSpecs.ps1 -Type designs

    List only orphaned design specs

.EXAMPLE
    .\Resolve-OrphanedSpecs.ps1 -Action archive -DryRun

    Show what specs would be archived without archiving

.EXAMPLE
    .\Resolve-OrphanedSpecs.ps1 -Action delete -Force

    Delete orphaned specs without confirmation (DANGEROUS)

.NOTES
    Exit codes:
    0 = Success (no orphans or action completed)
    1 = Error (invalid path, file operation failed)
    2 = Orphans found (when -Action list)

    See: ADR-035 Exit Code Standardization
#>

[CmdletBinding()]
param(
    [Parameter()]
    [string]$SpecsPath = ".agents/specs",

    [Parameter()]
    [ValidateSet("list", "link", "archive", "delete")]
    [string]$Action = "list",

    [Parameter()]
    [ValidateSet("all", "requirements", "designs", "tasks")]
    [string]$Type = "all",

    [Parameter()]
    [switch]$DryRun,

    [Parameter()]
    [switch]$Force,

    [Parameter()]
    [switch]$NoCache
)

$ErrorActionPreference = "Stop"

# Import caching module
$cacheModulePath = Join-Path $PSScriptRoot "TraceabilityCache.psm1"
if (Test-Path $cacheModulePath) {
    Import-Module $cacheModulePath -Force
    $CachingEnabled = -not $NoCache
}
else {
    $CachingEnabled = $false
}

#region Color Output
$ColorReset = "`e[0m"
$ColorRed = "`e[31m"
$ColorYellow = "`e[33m"
$ColorGreen = "`e[32m"
$ColorCyan = "`e[36m"

function Write-ColorOutput {
    param([string]$Message, [string]$Color = $ColorReset)
    Write-Host "${Color}${Message}${ColorReset}"
}
#endregion

#region YAML Parsing
function Get-YamlFrontMatter {
    param([string]$FilePath)

    if ($CachingEnabled) {
        $fileHash = Get-TraceabilityFileHash -FilePath $FilePath
        if ($fileHash) {
            $cached = Get-CachedSpec -FilePath $FilePath -CurrentHash $fileHash
            if ($cached) {
                return $cached
            }
        }
    }

    $content = Get-Content -Path $FilePath -Raw -ErrorAction SilentlyContinue
    if (-not $content) { return $null }

    if ($content -match '(?s)^---\r?\n(.+?)\r?\n---') {
        $yaml = $Matches[1]
        $result = @{
            type = ''
            id = ''
            status = ''
            related = @()
            filePath = $FilePath
        }

        if ($yaml -match '(?m)^type:\s*(.+)$') {
            $result.type = $Matches[1].Trim()
        }

        if ($yaml -match '(?m)^id:\s*(.+)$') {
            $result.id = $Matches[1].Trim()
        }

        if ($yaml -match '(?m)^status:\s*(.+)$') {
            $result.status = $Matches[1].Trim()
        }

        if ($yaml -match '(?s)related:\s*\r?\n((?:\s+-\s+.+\r?\n?)+)') {
            $relatedBlock = $Matches[1]
            $result.related = [regex]::Matches($relatedBlock, '-\s+([A-Z]+-[A-Z0-9]+)') |
                ForEach-Object { $_.Groups[1].Value }
        }

        if ($CachingEnabled -and $fileHash) {
            Set-CachedSpec -FilePath $FilePath -FileHash $fileHash -Spec $result
        }

        return $result
    }

    return $null
}
#endregion

#region Spec Loading
function Get-AllSpecs {
    param([string]$BasePath)

    $specs = @{
        requirements = @{}
        designs = @{}
        tasks = @{}
        all = @{}
    }

    $reqPath = Join-Path $BasePath "requirements"
    if (Test-Path $reqPath) {
        Get-ChildItem -Path $reqPath -Filter "REQ-*.md" | ForEach-Object {
            $spec = Get-YamlFrontMatter -FilePath $_.FullName
            if ($spec -and $spec.id) {
                $specs.requirements[$spec.id] = $spec
                $specs.all[$spec.id] = $spec
            }
        }
    }

    $designPath = Join-Path $BasePath "design"
    if (Test-Path $designPath) {
        Get-ChildItem -Path $designPath -Filter "DESIGN-*.md" | ForEach-Object {
            $spec = Get-YamlFrontMatter -FilePath $_.FullName
            if ($spec -and $spec.id) {
                $specs.designs[$spec.id] = $spec
                $specs.all[$spec.id] = $spec
            }
        }
    }

    $taskPath = Join-Path $BasePath "tasks"
    if (Test-Path $taskPath) {
        Get-ChildItem -Path $taskPath -Filter "TASK-*.md" | ForEach-Object {
            $spec = Get-YamlFrontMatter -FilePath $_.FullName
            if ($spec -and $spec.id) {
                $specs.tasks[$spec.id] = $spec
                $specs.all[$spec.id] = $spec
            }
        }
    }

    return $specs
}
#endregion

#region Orphan Detection
function Find-OrphanedSpecs {
    param([hashtable]$Specs)

    $orphans = @{
        requirements = @()
        designs = @()
        tasks = @()
    }

    # Build reference indices
    $reqRefs = @{}   # REQ-ID -> [DESIGN-IDs that reference it]
    $designRefs = @{} # DESIGN-ID -> [TASK-IDs that reference it]

    foreach ($reqId in $Specs.requirements.Keys) {
        $reqRefs[$reqId] = @()
    }
    foreach ($designId in $Specs.designs.Keys) {
        $designRefs[$designId] = @()
    }

    # Build forward references from designs to requirements
    foreach ($designId in $Specs.designs.Keys) {
        $design = $Specs.designs[$designId]
        foreach ($relatedId in $design.related) {
            if ($relatedId -match '^REQ-' -and $reqRefs.ContainsKey($relatedId)) {
                $reqRefs[$relatedId] += $designId
            }
        }
    }

    # Build forward references from tasks to designs
    foreach ($taskId in $Specs.tasks.Keys) {
        $task = $Specs.tasks[$taskId]
        foreach ($relatedId in $task.related) {
            if ($relatedId -match '^DESIGN-' -and $designRefs.ContainsKey($relatedId)) {
                $designRefs[$relatedId] += $taskId
            }
        }
    }

    # Find orphaned requirements (no designs reference them)
    foreach ($reqId in $Specs.requirements.Keys) {
        if ($reqRefs[$reqId].Count -eq 0) {
            $orphans.requirements += @{
                id = $reqId
                spec = $Specs.requirements[$reqId]
                reason = "No design references this requirement"
            }
        }
    }

    # Find orphaned designs
    foreach ($designId in $Specs.designs.Keys) {
        $design = $Specs.designs[$designId]
        $hasReqRef = ($design.related | Where-Object { $_ -match '^REQ-' }).Count -gt 0
        $hasTaskRef = $designRefs[$designId].Count -gt 0

        if (-not $hasReqRef -and -not $hasTaskRef) {
            $orphans.designs += @{
                id = $designId
                spec = $design
                reason = "No requirement reference and no tasks reference this design"
            }
        }
        elseif (-not $hasReqRef) {
            $orphans.designs += @{
                id = $designId
                spec = $design
                reason = "No requirement reference"
            }
        }
        elseif (-not $hasTaskRef) {
            $orphans.designs += @{
                id = $designId
                spec = $design
                reason = "No tasks reference this design"
            }
        }
    }

    # Find orphaned tasks (no design reference)
    foreach ($taskId in $Specs.tasks.Keys) {
        $task = $Specs.tasks[$taskId]
        $hasDesignRef = ($task.related | Where-Object { $_ -match '^DESIGN-' }).Count -gt 0

        if (-not $hasDesignRef) {
            $orphans.tasks += @{
                id = $taskId
                spec = $task
                reason = "No design reference"
            }
        }
    }

    return $orphans
}
#endregion

#region Actions
function Show-Orphans {
    param(
        [hashtable]$Orphans,
        [string]$TypeFilter
    )

    $totalOrphans = 0

    if ($TypeFilter -eq "all" -or $TypeFilter -eq "requirements") {
        if ($Orphans.requirements.Count -gt 0) {
            Write-ColorOutput "Orphaned Requirements:" $ColorYellow
            foreach ($orphan in ($Orphans.requirements | Sort-Object { $_.id })) {
                Write-ColorOutput "  $($orphan.id): $($orphan.reason)" $ColorYellow
                Write-ColorOutput "    File: $($orphan.spec.filePath)"
            }
            Write-Host ""
            $totalOrphans += $Orphans.requirements.Count
        }
    }

    if ($TypeFilter -eq "all" -or $TypeFilter -eq "designs") {
        if ($Orphans.designs.Count -gt 0) {
            Write-ColorOutput "Orphaned Designs:" $ColorYellow
            foreach ($orphan in ($Orphans.designs | Sort-Object { $_.id })) {
                Write-ColorOutput "  $($orphan.id): $($orphan.reason)" $ColorYellow
                Write-ColorOutput "    File: $($orphan.spec.filePath)"
            }
            Write-Host ""
            $totalOrphans += $Orphans.designs.Count
        }
    }

    if ($TypeFilter -eq "all" -or $TypeFilter -eq "tasks") {
        if ($Orphans.tasks.Count -gt 0) {
            Write-ColorOutput "Orphaned Tasks:" $ColorYellow
            foreach ($orphan in ($Orphans.tasks | Sort-Object { $_.id })) {
                Write-ColorOutput "  $($orphan.id): $($orphan.reason)" $ColorYellow
                Write-ColorOutput "    File: $($orphan.spec.filePath)"
            }
            Write-Host ""
            $totalOrphans += $Orphans.tasks.Count
        }
    }

    if ($totalOrphans -eq 0) {
        Write-ColorOutput "No orphaned specs found." $ColorGreen
        return 0
    }
    else {
        Write-ColorOutput "Total orphaned specs: $totalOrphans" $ColorCyan
        return 2
    }
}

function Invoke-ArchiveOrphans {
    param(
        [hashtable]$Orphans,
        [string]$TypeFilter,
        [string]$BasePath,
        [switch]$DryRun,
        [switch]$Force
    )

    $archivePath = Join-Path $BasePath ".archive"

    # Collect specs to archive
    $specsToArchive = @()

    if ($TypeFilter -eq "all" -or $TypeFilter -eq "requirements") {
        $specsToArchive += $Orphans.requirements
    }
    if ($TypeFilter -eq "all" -or $TypeFilter -eq "designs") {
        $specsToArchive += $Orphans.designs
    }
    if ($TypeFilter -eq "all" -or $TypeFilter -eq "tasks") {
        $specsToArchive += $Orphans.tasks
    }

    if ($specsToArchive.Count -eq 0) {
        Write-ColorOutput "No orphaned specs to archive." $ColorGreen
        return 0
    }

    Write-ColorOutput "Specs to archive:" $ColorCyan
    foreach ($spec in $specsToArchive) {
        Write-Host "  $($spec.id)"
    }
    Write-Host ""

    if ($DryRun) {
        Write-ColorOutput "DRY RUN: No files will be moved" $ColorYellow
        return 0
    }

    if (-not $Force) {
        $confirmation = Read-Host "Archive $($specsToArchive.Count) spec(s)? (y/N)"
        if ($confirmation -ne 'y') {
            Write-ColorOutput "Operation cancelled" $ColorYellow
            return 0
        }
    }

    # Create archive directory structure
    $reqArchive = Join-Path $archivePath "requirements"
    $designArchive = Join-Path $archivePath "design"
    $taskArchive = Join-Path $archivePath "tasks"

    if (-not (Test-Path $reqArchive)) { New-Item -Path $reqArchive -ItemType Directory -Force | Out-Null }
    if (-not (Test-Path $designArchive)) { New-Item -Path $designArchive -ItemType Directory -Force | Out-Null }
    if (-not (Test-Path $taskArchive)) { New-Item -Path $taskArchive -ItemType Directory -Force | Out-Null }

    # Move files
    foreach ($spec in $specsToArchive) {
        $targetDir = switch -Regex ($spec.id) {
            '^REQ-' { $reqArchive }
            '^DESIGN-' { $designArchive }
            '^TASK-' { $taskArchive }
        }

        $targetPath = Join-Path $targetDir (Split-Path $spec.spec.filePath -Leaf)
        Move-Item -Path $spec.spec.filePath -Destination $targetPath -Force
        Write-Host "  Archived: $($spec.id) -> $targetPath"
    }

    Write-ColorOutput "Archived $($specsToArchive.Count) spec(s)." $ColorGreen

    # Clear cache since files moved
    if ($CachingEnabled) {
        Clear-TraceabilityCache
    }

    return 0
}

function Invoke-DeleteOrphans {
    param(
        [hashtable]$Orphans,
        [string]$TypeFilter,
        [switch]$DryRun,
        [switch]$Force
    )

    # Collect specs to delete
    $specsToDelete = @()

    if ($TypeFilter -eq "all" -or $TypeFilter -eq "requirements") {
        $specsToDelete += $Orphans.requirements
    }
    if ($TypeFilter -eq "all" -or $TypeFilter -eq "designs") {
        $specsToDelete += $Orphans.designs
    }
    if ($TypeFilter -eq "all" -or $TypeFilter -eq "tasks") {
        $specsToDelete += $Orphans.tasks
    }

    if ($specsToDelete.Count -eq 0) {
        Write-ColorOutput "No orphaned specs to delete." $ColorGreen
        return 0
    }

    Write-ColorOutput "Specs to DELETE:" $ColorRed
    foreach ($spec in $specsToDelete) {
        Write-Host "  $($spec.id): $($spec.spec.filePath)"
    }
    Write-Host ""

    if ($DryRun) {
        Write-ColorOutput "DRY RUN: No files will be deleted" $ColorYellow
        return 0
    }

    if (-not $Force) {
        Write-ColorOutput "WARNING: This action cannot be undone!" $ColorRed
        $confirmation = Read-Host "Type 'DELETE' to confirm deletion of $($specsToDelete.Count) spec(s)"
        if ($confirmation -ne 'DELETE') {
            Write-ColorOutput "Operation cancelled" $ColorYellow
            return 0
        }
    }

    # Delete files
    foreach ($spec in $specsToDelete) {
        Remove-Item -Path $spec.spec.filePath -Force
        Write-Host "  Deleted: $($spec.id)"
    }

    Write-ColorOutput "Deleted $($specsToDelete.Count) spec(s)." $ColorGreen

    # Clear cache since files deleted
    if ($CachingEnabled) {
        Clear-TraceabilityCache
    }

    return 0
}

function Invoke-LinkWizard {
    param(
        [hashtable]$Orphans,
        [hashtable]$Specs,
        [string]$TypeFilter,
        [string]$BasePath,
        [switch]$DryRun
    )

    Write-ColorOutput "Interactive Link Wizard" $ColorCyan
    Write-ColorOutput "=======================" $ColorCyan
    Write-Host ""

    # Collect orphans to process
    $orphansToProcess = @()

    if ($TypeFilter -eq "all" -or $TypeFilter -eq "tasks") {
        # Tasks need design links, most actionable
        foreach ($orphan in $Orphans.tasks) {
            $orphansToProcess += @{
                orphan = $orphan
                suggestType = 'DESIGN'
            }
        }
    }

    if ($TypeFilter -eq "all" -or $TypeFilter -eq "designs") {
        foreach ($orphan in $Orphans.designs) {
            # Check which link is missing
            $design = $orphan.spec
            $hasReqRef = ($design.related | Where-Object { $_ -match '^REQ-' }).Count -gt 0

            if (-not $hasReqRef) {
                $orphansToProcess += @{
                    orphan = $orphan
                    suggestType = 'REQ'
                }
            }
        }
    }

    if ($orphansToProcess.Count -eq 0) {
        Write-ColorOutput "No orphans can be resolved through linking." $ColorYellow
        Write-Host "Orphaned requirements need designs to reference them, not the other way around."
        return 0
    }

    Write-Host "Found $($orphansToProcess.Count) orphan(s) that can be resolved through linking."
    Write-Host ""

    foreach ($item in $orphansToProcess) {
        $orphan = $item.orphan
        $suggestType = $item.suggestType

        Write-ColorOutput "Processing: $($orphan.id)" $ColorYellow
        Write-Host "  Reason: $($orphan.reason)"
        Write-Host "  Suggested link type: $suggestType"
        Write-Host ""

        # Show available targets
        $targets = @()
        if ($suggestType -eq 'DESIGN') {
            $targets = $Specs.designs.Keys | Sort-Object
        }
        elseif ($suggestType -eq 'REQ') {
            $targets = $Specs.requirements.Keys | Sort-Object
        }

        if ($targets.Count -eq 0) {
            Write-Host "  No $suggestType specs available to link."
            Write-Host ""
            continue
        }

        Write-Host "  Available targets:"
        $i = 1
        foreach ($target in $targets | Select-Object -First 10) {
            Write-Host "    [$i] $target"
            $i++
        }
        if ($targets.Count -gt 10) {
            Write-Host "    ... ($($targets.Count - 10) more)"
        }
        Write-Host "    [s] Skip"
        Write-Host ""

        if ($DryRun) {
            Write-ColorOutput "  DRY RUN: Would prompt for link selection" $ColorYellow
            Write-Host ""
            continue
        }

        $selection = Read-Host "  Select target number or enter ID directly (s to skip)"
        if ($selection -eq 's' -or [string]::IsNullOrWhiteSpace($selection)) {
            Write-Host "  Skipped."
            Write-Host ""
            continue
        }

        # Determine target ID
        $targetId = $null
        if ($selection -match '^\d+$') {
            $index = [int]$selection - 1
            if ($index -ge 0 -and $index -lt $targets.Count) {
                $targetId = $targets[$index]
            }
        }
        else {
            $targetId = $selection.Trim().ToUpper()
        }

        if (-not $targetId -or -not $Specs.all.ContainsKey($targetId)) {
            Write-ColorOutput "  Invalid selection: $selection" $ColorRed
            Write-Host ""
            continue
        }

        # Add the link using Update-SpecReferences
        $updateScript = Join-Path $PSScriptRoot "Update-SpecReferences.ps1"
        $updateParams = @{
            SourceId = $orphan.id
            AddReferences = @($targetId)
            SpecsPath = $BasePath
            Force = $true
        }

        try {
            & $updateScript @updateParams
            Write-ColorOutput "  Linked $($orphan.id) -> $targetId" $ColorGreen
        }
        catch {
            Write-ColorOutput "  Failed to link: $_" $ColorRed
        }

        Write-Host ""
    }

    return 0
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

# Load all specs
$specs = Get-AllSpecs -BasePath $resolvedPath.Path

# Find orphans
$orphans = Find-OrphanedSpecs -Specs $specs

# Execute action
$exitCode = switch ($Action) {
    "list" {
        Show-Orphans -Orphans $orphans -TypeFilter $Type
    }
    "archive" {
        Invoke-ArchiveOrphans -Orphans $orphans -TypeFilter $Type -BasePath $resolvedPath.Path -DryRun:$DryRun -Force:$Force
    }
    "delete" {
        Invoke-DeleteOrphans -Orphans $orphans -TypeFilter $Type -DryRun:$DryRun -Force:$Force
    }
    "link" {
        Invoke-LinkWizard -Orphans $orphans -Specs $specs -TypeFilter $Type -BasePath $resolvedPath.Path -DryRun:$DryRun
    }
}

exit $exitCode
#endregion
