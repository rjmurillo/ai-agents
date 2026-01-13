<#
.SYNOPSIS
    Orchestrates memory cross-reference scripts for pre-commit hook integration.

.DESCRIPTION
    Unified entry point for all three memory cross-reference scripts.
    Executes in correct order:
    1. Convert-IndexTableLinks (tables first)
    2. Convert-MemoryReferences (backticks second)
    3. Improve-MemoryGraphDensity (related sections last)

    Designed for use in git hooks with non-blocking error handling.

.PARAMETER FilesToProcess
    Specific memory files to process. If not provided, processes all files.

.PARAMETER MemoriesPath
    Path to the memories directory. Defaults to .serena/memories.

.PARAMETER OutputJson
    Output machine-parseable JSON statistics instead of human-readable output.

.PARAMETER SkipPathValidation
    Skip CWE-22 path validation (for testing purposes only).

.EXAMPLE
    # From pre-commit hook
    .\Invoke-MemoryCrossReference.ps1 -FilesToProcess $stagedFiles

.EXAMPLE
    # Process all memory files
    .\Invoke-MemoryCrossReference.ps1

.EXAMPLE
    # Get JSON statistics
    .\Invoke-MemoryCrossReference.ps1 -OutputJson
#>

[CmdletBinding()]
param(
    [string[]]$FilesToProcess,

    [string]$MemoriesPath,

    [switch]$OutputJson,

    [switch]$SkipPathValidation
)

$ErrorActionPreference = 'Stop'

# Determine script directory
$scriptDir = $PSScriptRoot

# Track aggregate statistics
$aggregateStats = @{
    IndexLinksAdded      = 0
    BacktickLinksAdded   = 0
    RelatedSectionsAdded = 0
    FilesModified        = 0
    Errors               = @()
}

# Build common parameters
$commonParams = @{}
if ($MemoriesPath) {
    $commonParams['MemoriesPath'] = $MemoriesPath
}
if ($FilesToProcess -and $FilesToProcess.Count -gt 0) {
    $commonParams['FilesToProcess'] = $FilesToProcess
}
if ($SkipPathValidation) {
    $commonParams['SkipPathValidation'] = $true
}

# Script 1: Convert-IndexTableLinks
if (-not $OutputJson) {
    Write-Host "=== Step 1/3: Converting index table links ===" -ForegroundColor Cyan
}

try {
    $indexScript = Join-Path $scriptDir 'Convert-IndexTableLinks.ps1'
    $indexResult = & $indexScript @commonParams -OutputJson | ConvertFrom-Json

    $aggregateStats.IndexLinksAdded = $indexResult.LinksAdded
    if ($indexResult.FilesModified -gt 0) {
        $aggregateStats.FilesModified += $indexResult.FilesModified
    }
    if ($indexResult.Errors -and $indexResult.Errors.Count -gt 0) {
        $aggregateStats.Errors += $indexResult.Errors
    }
} catch {
    $aggregateStats.Errors += "Convert-IndexTableLinks: $($_.Exception.Message)"
    if (-not $OutputJson) {
        Write-Warning "Convert-IndexTableLinks failed: $($_.Exception.Message)"
    }
}

# Script 2: Convert-MemoryReferences
if (-not $OutputJson) {
    Write-Host "`n=== Step 2/3: Converting backtick references ===" -ForegroundColor Cyan
}

try {
    $refsScript = Join-Path $scriptDir 'Convert-MemoryReferences.ps1'
    $refsResult = & $refsScript @commonParams -OutputJson | ConvertFrom-Json

    $aggregateStats.BacktickLinksAdded = $refsResult.LinksAdded
    if ($refsResult.FilesModified -gt 0) {
        $aggregateStats.FilesModified += $refsResult.FilesModified
    }
    if ($refsResult.Errors -and $refsResult.Errors.Count -gt 0) {
        $aggregateStats.Errors += $refsResult.Errors
    }
} catch {
    $aggregateStats.Errors += "Convert-MemoryReferences: $($_.Exception.Message)"
    if (-not $OutputJson) {
        Write-Warning "Convert-MemoryReferences failed: $($_.Exception.Message)"
    }
}

# Script 3: Improve-MemoryGraphDensity
if (-not $OutputJson) {
    Write-Host "`n=== Step 3/3: Adding Related sections ===" -ForegroundColor Cyan
}

try {
    $densityScript = Join-Path $scriptDir 'Improve-MemoryGraphDensity.ps1'
    $densityResult = & $densityScript @commonParams -OutputJson | ConvertFrom-Json

    $aggregateStats.RelatedSectionsAdded = $densityResult.RelationshipsAdded
    if ($densityResult.FilesModified -gt 0) {
        $aggregateStats.FilesModified += $densityResult.FilesModified
    }
    if ($densityResult.Errors -and $densityResult.Errors.Count -gt 0) {
        $aggregateStats.Errors += $densityResult.Errors
    }
} catch {
    $aggregateStats.Errors += "Improve-MemoryGraphDensity: $($_.Exception.Message)"
    if (-not $OutputJson) {
        Write-Warning "Improve-MemoryGraphDensity failed: $($_.Exception.Message)"
    }
}

# Output results
if ($OutputJson) {
    [PSCustomObject]@{
        IndexLinksAdded      = $aggregateStats.IndexLinksAdded
        BacktickLinksAdded   = $aggregateStats.BacktickLinksAdded
        RelatedSectionsAdded = $aggregateStats.RelatedSectionsAdded
        FilesModified        = $aggregateStats.FilesModified
        Errors               = $aggregateStats.Errors
        Success              = $aggregateStats.Errors.Count -eq 0
    } | ConvertTo-Json -Compress
} else {
    Write-Host "`n=== Summary ===" -ForegroundColor Green
    Write-Host "Index table links added: $($aggregateStats.IndexLinksAdded)"
    Write-Host "Backtick references converted: $($aggregateStats.BacktickLinksAdded)"
    Write-Host "Related sections added: $($aggregateStats.RelatedSectionsAdded)"
    Write-Host "Total files modified: $($aggregateStats.FilesModified)"

    if ($aggregateStats.Errors.Count -gt 0) {
        Write-Host "`nWarnings/Errors:" -ForegroundColor Yellow
        foreach ($error in $aggregateStats.Errors) {
            Write-Host "  - $error" -ForegroundColor Yellow
        }
    }
}

# Exit with success (non-blocking for hooks)
exit 0
