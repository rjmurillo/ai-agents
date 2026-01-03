#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Import Claude-Mem memory snapshots from .claude-mem/memories/

.DESCRIPTION
    Idempotent import of all JSON memory files from the memories directory.
    Automatically prevents duplicates using composite keys.

    See .claude-mem/memories/README.md for complete workflow documentation.

.EXAMPLE
    pwsh .claude-mem/scripts/Import-ClaudeMemMemories.ps1

.NOTES
    Calls the claude-mem plugin import script directly at:
    ~/.claude/plugins/marketplaces/thedotmack/scripts/import-memories.ts

    LIMITATION: Only imports .json files from the top-level memories directory.
    Files in subdirectories are NOT imported. Organize exports at the root level.
#>

[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$MemoriesDir = Join-Path $PSScriptRoot '..' 'memories'
$PluginScript = Join-Path $env:HOME '.claude' 'plugins' 'marketplaces' 'thedotmack' 'scripts' 'import-memories.ts'

if (-not (Test-Path $PluginScript)) {
    Write-Error "Claude-Mem plugin script not found at: $PluginScript"
    Write-Error ""
    Write-Error "Install the claude-mem plugin:"
    Write-Error "  1. Visit: https://github.com/thedotmack/claude-mem"
    Write-Error "  2. Follow installation instructions for Claude Code MCP plugins"
    exit 1
}

if (-not (Test-Path $MemoriesDir)) {
    Write-Host "No memories directory found at: $MemoriesDir" -ForegroundColor Yellow
    Write-Host "Creating directory..." -ForegroundColor Yellow
    New-Item -ItemType Directory -Path $MemoriesDir -Force | Out-Null
    Write-Host "No memory files to import" -ForegroundColor Cyan
    exit 0
}

# NOTE: Only top-level .json files are imported (no subdirectory scanning)
# WHY: Prevents accidental imports from backup/temp subdirectories
# LIMITATION: Organize all import files at the root of .claude-mem/memories/
$Files = @(Get-ChildItem -Path $MemoriesDir -Filter '*.json' -File)
if ($Files.Count -eq 0) {
    Write-Host "No memory files to import from: $MemoriesDir" -ForegroundColor Cyan
    exit 0
}

Write-Host "🔄 Importing $($Files.Count) memory file(s) from .claude-mem/memories/" -ForegroundColor Green
Write-Host ""

$ImportCount = 0
$FailedFiles = @()

# Philosophy: Partial import success is acceptable - some files may fail while others succeed
# We track failures but continue processing remaining files for maximum data recovery
foreach ($File in $Files) {
    Write-Host "  📁 $($File.Name)" -ForegroundColor Gray

    try {
        # SECURITY: Quote all variables to prevent command injection (CWE-77)
        # WHY: Unquoted variables allow shell metacharacters to inject commands
        npx tsx "$PluginScript" "$($File.FullName)"

        # Check exit code to detect silent failures
        if ($LASTEXITCODE -ne 0) {
            $FailedFiles += [PSCustomObject]@{
                File = $File.Name
                Reason = "Plugin exited with code $LASTEXITCODE"
            }
            Write-Warning "Import failed for $($File.Name): Plugin returned exit code $LASTEXITCODE"
        }
        else {
            $ImportCount++
        }
    }
    catch {
        $FailedFiles += [PSCustomObject]@{
            File = $File.Name
            Reason = $_.Exception.Message
        }
        Write-Warning "Failed to import $($File.Name): $_"
    }
}

Write-Host ""

if ($FailedFiles.Count -eq 0) {
    Write-Host "✅ Import complete: $ImportCount file(s) processed successfully" -ForegroundColor Green
    Write-Host "   Duplicates automatically skipped via composite key matching" -ForegroundColor Gray
}
else {
    Write-Host "⚠️  Import completed with failures: $ImportCount succeeded, $($FailedFiles.Count) failed" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "Failed files:" -ForegroundColor Red
    foreach ($Failed in $FailedFiles) {
        Write-Host "  ❌ $($Failed.File): $($Failed.Reason)" -ForegroundColor Red
    }
    Write-Host ""
    Write-Host "Troubleshooting:" -ForegroundColor Yellow
    Write-Host "  1. Verify JSON file syntax is valid" -ForegroundColor Gray
    Write-Host "  2. Check plugin is installed: Test-Path $PluginScript" -ForegroundColor Gray
    Write-Host "  3. Ensure no file locks or permission issues" -ForegroundColor Gray
    Write-Host "  4. Check disk space availability" -ForegroundColor Gray
    exit 1
}
