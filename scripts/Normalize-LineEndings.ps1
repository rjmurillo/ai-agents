<#
.SYNOPSIS
    Normalizes line endings in the repository to LF.

.DESCRIPTION
    This script applies the .gitattributes rules to all existing files in the repository
    by renormalizing line endings. It should be run once after updating .gitattributes
    to enforce LF line endings repository-wide.

.PARAMETER WhatIf
    Shows what changes would be made without actually making them.

.EXAMPLE
    .\Normalize-LineEndings.ps1
    Normalizes all line endings in the repository.

.EXAMPLE
    .\Normalize-LineEndings.ps1 -WhatIf
    Shows what files would be modified without actually changing them.

.NOTES
    This script requires Git to be installed and the current directory to be a Git repository.

    Related:
    - Issue #896: Enforce LF line endings for agent files
    - PR #895: ADR-040 amendment (inline array syntax fix)
    - GitHub Copilot CLI Issue #694: CRLF line ending YAML parsing errors
#>

[CmdletBinding(SupportsShouldProcess)]
param()

#Requires -Version 7.0

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Test-GitRepository {
    <#
    .SYNOPSIS
        Checks if the current directory is a Git repository.
    #>
    try {
        git rev-parse --is-inside-work-tree 2>$null | Out-Null
        return $true
    }
    catch {
        return $false
    }
}

function Get-LineEndingStats {
    <#
    .SYNOPSIS
        Gets statistics about line endings in the repository.
    #>
    param(
        [Parameter(Mandatory)]
        [string]$Stage
    )

    Write-Host "`n[$Stage] Line Ending Statistics:" -ForegroundColor Cyan

    $eolOutput = git ls-files --eol

    # Count files by line ending type in index
    $crlfInIndex = ($eolOutput | Select-String 'i/crlf').Count
    $lfInIndex = ($eolOutput | Select-String 'i/lf').Count

    # Count files by line ending type in working directory
    $crlfInWorking = ($eolOutput | Select-String 'w/crlf').Count
    $lfInWorking = ($eolOutput | Select-String 'w/lf').Count

    Write-Host "  Index (staged):      $lfInIndex LF, $crlfInIndex CRLF" -ForegroundColor White
    Write-Host "  Working directory:   $lfInWorking LF, $crlfInWorking CRLF" -ForegroundColor White

    return @{
        IndexLF = $lfInIndex
        IndexCRLF = $crlfInIndex
        WorkingLF = $lfInWorking
        WorkingCRLF = $crlfInWorking
    }
}

function Save-LineEndingAudit {
    <#
    .SYNOPSIS
        Saves a snapshot of current line endings to a file.
    #>
    param(
        [Parameter(Mandatory)]
        [string]$OutputPath
    )

    $dir = Split-Path $OutputPath -Parent
    if (-not (Test-Path $dir)) {
        New-Item -Path $dir -ItemType Directory -Force | Out-Null
    }

    git ls-files --eol | Out-File -FilePath $OutputPath -Encoding utf8
    Write-Host "Saved line ending audit to: $OutputPath" -ForegroundColor Green
}

# Main script execution
try {
    # Verify we're in a Git repository
    if (-not (Test-GitRepository)) {
        Write-Error "Current directory is not a Git repository. Please run this script from the repository root."
        exit 1
    }

    Write-Host "`nLine Ending Normalization Script" -ForegroundColor Cyan
    Write-Host "=================================" -ForegroundColor Cyan
    Write-Host "This script will normalize all line endings in the repository to LF." -ForegroundColor White
    Write-Host ""

    # Get statistics before normalization
    $beforeStats = Get-LineEndingStats -Stage "BEFORE"

    # Save before audit
    $beforeAuditPath = ".agents/analysis/line-endings-before.txt"
    Save-LineEndingAudit -OutputPath $beforeAuditPath

    # Check if normalization is needed
    if ($beforeStats.IndexCRLF -eq 0 -and $beforeStats.WorkingCRLF -eq 0) {
        Write-Host "`n✓ No line ending normalization needed. All files already use LF." -ForegroundColor Green
        return
    }

    # Perform normalization
    Write-Host "`nNormalizing line endings..." -ForegroundColor Yellow

    if ($PSCmdlet.ShouldProcess("Repository files", "Normalize line endings to LF")) {
        # Step 1: Remove all files from Git's index (does not delete files)
        Write-Host "  [1/3] Removing files from index..." -ForegroundColor Gray
        git rm --cached -r . 2>&1 | Out-Null

        # Step 2: Re-add all files, applying new .gitattributes rules
        Write-Host "  [2/3] Re-adding files with normalized line endings..." -ForegroundColor Gray
        git add --renormalize . 2>&1 | Out-Null

        # Step 3: Verify changes
        Write-Host "  [3/3] Verifying normalization..." -ForegroundColor Gray

        # Get statistics after normalization
        $afterStats = Get-LineEndingStats -Stage "AFTER"

        # Save after audit
        $afterAuditPath = ".agents/analysis/line-endings-after.txt"
        Save-LineEndingAudit -OutputPath $afterAuditPath

        # Calculate changes
        $normalizedCount = $beforeStats.IndexCRLF

        Write-Host "`n✓ Normalization complete!" -ForegroundColor Green
        Write-Host "  Normalized $normalizedCount files from CRLF to LF" -ForegroundColor White

        # Show git status
        Write-Host "`nGit Status:" -ForegroundColor Cyan
        git status --short | Out-String | Write-Host

        Write-Host "`nNext Steps:" -ForegroundColor Cyan
        Write-Host "  1. Review the changes: git diff --stat" -ForegroundColor White
        Write-Host "  2. Compare audits: diff $beforeAuditPath $afterAuditPath" -ForegroundColor White
        Write-Host "  3. Commit the normalized files:" -ForegroundColor White
        Write-Host "     git commit -m 'chore: normalize line endings to LF'" -ForegroundColor Gray
        Write-Host ""
    }
}
catch {
    Write-Error "An error occurred during line ending normalization: $_"
    exit 1
}
