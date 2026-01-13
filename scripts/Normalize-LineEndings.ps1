#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Normalize line endings for agent files to LF per .gitattributes rules.

.DESCRIPTION
    This script applies .gitattributes line ending rules to existing files by:
    1. Removing all files from Git's index (without deleting them)
    2. Re-adding all files with --renormalize to apply new attributes
    3. Reporting which files were modified

    This is a one-time operation to fix existing CRLF line endings.
    Future commits will automatically use LF due to .gitattributes rules.

.EXAMPLE
    pwsh scripts/Normalize-LineEndings.ps1

.NOTES
    Issue #896: Enforce LF line endings for agent files
    Evidence: GitHub Copilot CLI issues #694 and #673
#>

[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

Write-Host "Normalizing line endings for agent files..." -ForegroundColor Cyan

try {
    # Step 1: Remove all files from index (does not delete files)
    Write-Host "`nStep 1: Removing files from Git index..." -ForegroundColor Yellow
    git rm --cached -r . 2>&1 | Out-Null

    if ($LASTEXITCODE -ne 0) {
        throw "Failed to remove files from Git index"
    }

    # Step 2: Re-add all files with normalization
    Write-Host "Step 2: Re-adding files with line ending normalization..." -ForegroundColor Yellow
    git add --renormalize . 2>&1 | Out-Null

    if ($LASTEXITCODE -ne 0) {
        throw "Failed to re-add files with normalization"
    }

    # Step 3: Report changes
    Write-Host "`nStep 3: Checking for normalized files..." -ForegroundColor Yellow
    $changedFiles = git diff --cached --name-only

    if ($changedFiles) {
        $fileCount = ($changedFiles | Measure-Object).Count
        Write-Host "`n✓ Normalized $fileCount files:" -ForegroundColor Green
        $changedFiles | ForEach-Object { Write-Host "  - $_" }
    } else {
        Write-Host "`n✓ No files needed normalization (all already LF)" -ForegroundColor Green
    }

    Write-Host "`n✓ Line ending normalization complete!" -ForegroundColor Green
    exit 0
}
catch {
    Write-Error "Line ending normalization failed: $_"
    exit 1
}
