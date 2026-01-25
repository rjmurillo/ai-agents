#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Fixes validation failures in PR #964.

.DESCRIPTION
    Addresses two issues:
    1. Cleans up .md session files that should be archived or removed
    2. Renames skill-prefixed memory files to comply with ADR-017

.PARAMETER WhatIf
    Shows what would be done without making changes.

.EXAMPLE
    ./Fix-PR964-Validation.ps1
    Fixes both session files and memory file naming.

.EXAMPLE
    ./Fix-PR964-Validation.ps1 -WhatIf
    Shows what would be changed without making changes.
#>

[CmdletBinding(SupportsShouldProcess)]
param()

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$repoRoot = Split-Path $PSScriptRoot -Parent
$sessionsDir = Join-Path $repoRoot '.agents/sessions'
$archiveDir = Join-Path $repoRoot '.agents/archive/sessions'
$memoriesDir = Join-Path $repoRoot '.serena/memories'

Write-Host "Starting PR #964 validation fixes..." -ForegroundColor Cyan
Write-Host ""

#region Session File Cleanup

Write-Host "=== Task 1: Session File Cleanup ===" -ForegroundColor Yellow
Write-Host ""

$mdFiles = Get-ChildItem -Path $sessionsDir -Filter '*.md' -File
Write-Host "Found $($mdFiles.Count) .md files in sessions directory"

$toDelete = @()
$toMove = @()

foreach ($mdFile in $mdFiles) {
    $baseName = [System.IO.Path]::GetFileNameWithoutExtension($mdFile.Name)
    $archivePath = Join-Path $archiveDir $mdFile.Name
    $jsonPath = Join-Path $sessionsDir "$baseName.json"

    if (Test-Path $archivePath) {
        # File exists in archive, safe to delete from sessions
        $toDelete += $mdFile
    }
    else {
        # Not in archive, needs to be moved
        if (Test-Path $jsonPath) {
            # JSON equivalent exists, safe to move
            $toMove += $mdFile
        }
        else {
            Write-Warning "Missing JSON equivalent for $($mdFile.Name), skipping"
        }
    }
}

Write-Host "Files to delete (already archived): $($toDelete.Count)" -ForegroundColor Green
Write-Host "Files to move to archive: $($toMove.Count)" -ForegroundColor Green
Write-Host ""

# Delete files already in archive
foreach ($file in $toDelete) {
    if ($PSCmdlet.ShouldProcess($file.FullName, "Delete (already archived)")) {
        Remove-Item -Path $file.FullName -Force
        Write-Host "  Deleted: $($file.Name)" -ForegroundColor Gray
    }
}

# Move files to archive
foreach ($file in $toMove) {
    $destination = Join-Path $archiveDir $file.Name
    if ($PSCmdlet.ShouldProcess($file.FullName, "Move to archive")) {
        Move-Item -Path $file.FullName -Destination $destination -Force
        Write-Host "  Moved: $($file.Name) -> archive/" -ForegroundColor Gray
    }
}

Write-Host ""
Write-Host "Session cleanup complete: $($toDelete.Count) deleted, $($toMove.Count) moved" -ForegroundColor Green
Write-Host ""

#endregion

#region Memory File Renaming

Write-Host "=== Task 2: Memory File Renaming (ADR-017) ===" -ForegroundColor Yellow
Write-Host ""

$skillFiles = Get-ChildItem -Path $memoriesDir -Filter 'skill-*.md' -File
Write-Host "Found $($skillFiles.Count) files with 'skill-' prefix"
Write-Host ""

$renamedFiles = @{}
$deletedDuplicates = @()

foreach ($file in $skillFiles) {
    $oldName = $file.Name
    $newName = $oldName -replace '^skill-', ''
    $newPath = Join-Path $memoriesDir $newName

    if (Test-Path $newPath) {
        # Target file already exists, this is a duplicate from orphaned artifacts
        # Delete the skill- prefixed version
        if ($PSCmdlet.ShouldProcess($file.FullName, "Delete duplicate (non-prefixed version exists)")) {
            Remove-Item -Path $file.FullName -Force
            $deletedDuplicates += $oldName
            Write-Host "  Deleted duplicate: $oldName (keeping $newName)" -ForegroundColor Gray
        }
        continue
    }

    # No duplicate, just rename
    if ($PSCmdlet.ShouldProcess($file.FullName, "Rename to $newName")) {
        Rename-Item -Path $file.FullName -NewName $newName -Force
        $renamedFiles[$oldName] = $newName
        Write-Host "  Renamed: $oldName -> $newName" -ForegroundColor Gray
    }
}

Write-Host ""
Write-Host "Memory files renamed: $($renamedFiles.Count)" -ForegroundColor Green
Write-Host "Duplicate files deleted: $($deletedDuplicates.Count)" -ForegroundColor Green
Write-Host ""

#endregion

#region Update Index Files

if ($renamedFiles.Count -gt 0 -and -not $WhatIfPreference) {
    Write-Host "=== Task 3: Updating Index Files ===" -ForegroundColor Yellow
    Write-Host ""

    $indexFiles = Get-ChildItem -Path $memoriesDir -Filter '*-index.md' -File
    Write-Host "Found $($indexFiles.Count) index files to check"
    Write-Host ""

    $updatedIndexes = 0

    foreach ($indexFile in $indexFiles) {
        $content = Get-Content -Path $indexFile.FullName -Raw
        $originalContent = $content
        $updated = $false

        foreach ($oldName in $renamedFiles.Keys) {
            $newName = $renamedFiles[$oldName]
            if ($content -match [regex]::Escape($oldName)) {
                $content = $content -replace [regex]::Escape($oldName), $newName
                $updated = $true
            }
        }

        if ($updated) {
            if ($PSCmdlet.ShouldProcess($indexFile.FullName, "Update references")) {
                Set-Content -Path $indexFile.FullName -Value $content -NoNewline
                $updatedIndexes++
                Write-Host "  Updated: $($indexFile.Name)" -ForegroundColor Gray
            }
        }
    }

    Write-Host ""
    Write-Host "Index files updated: $updatedIndexes" -ForegroundColor Green
    Write-Host ""
}

#endregion

Write-Host "=== Summary ===" -ForegroundColor Cyan
Write-Host "Session files deleted: $($toDelete.Count)"
Write-Host "Session files moved: $($toMove.Count)"
Write-Host "Memory files renamed: $($renamedFiles.Count)"
Write-Host "Memory files deleted (duplicates): $($deletedDuplicates.Count)"
if ($renamedFiles.Count -gt 0 -and -not $WhatIfPreference) {
    Write-Host "Index files updated: $updatedIndexes"
}
Write-Host ""
Write-Host "PR #964 validation fixes complete!" -ForegroundColor Green
