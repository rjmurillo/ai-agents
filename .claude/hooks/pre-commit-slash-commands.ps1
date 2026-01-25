#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Pre-commit hook to validate staged slash command files
#>

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

Write-Host "Validating staged slash commands..." -ForegroundColor Cyan

# Get staged .md files in .claude/commands/
# WHY: Wrap with @() to handle null/single result as array (PowerShell gotcha)
$stagedFiles = @(git diff --cached --name-only --diff-filter=ACM |
    Where-Object { $_ -like '.claude/commands/*.md' })

if ($stagedFiles.Count -eq 0) {
    Write-Host "[SKIP] No slash command files staged, skipping validation" -ForegroundColor Gray
    exit 0
}

Write-Host "Found $($stagedFiles.Count) staged slash command(s)" -ForegroundColor Gray

$validationScript = "$PSScriptRoot/../skills/slashcommandcreator/scripts/Validate-SlashCommand.ps1"
$failedFiles = @()

foreach ($file in $stagedFiles) {
    Write-Host "`nValidating: $file" -ForegroundColor Cyan

    & $validationScript -Path $file

    if ($LASTEXITCODE -ne 0) {
        $failedFiles += $file
    }
}

if ($failedFiles.Count -gt 0) {
    Write-Host "`n[FAIL] COMMIT BLOCKED: $($failedFiles.Count) file(s) failed validation" -ForegroundColor Red
    Write-Host "`nFailed files:" -ForegroundColor Yellow
    $failedFiles | ForEach-Object { Write-Host "  - $_" }
    Write-Host "`nFix violations and try again." -ForegroundColor Yellow
    Write-Host "Emergency bypass (if validation script has bugs): git commit --no-verify" -ForegroundColor Gray
    exit 1
} else {
    Write-Host "`n[PASS] All slash commands passed validation" -ForegroundColor Green
    exit 0
}
