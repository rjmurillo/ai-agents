# scripts/modules/SlashCommandValidator.psm1

#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Module for slash command validation (ADR-006: logic in modules, not workflows)
#>

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Invoke-SlashCommandValidation {
    <#
    .SYNOPSIS
        Validate all slash command files in .claude/commands/
    .DESCRIPTION
        Runs Validate-SlashCommand.ps1 on each .md file in .claude/commands/
        Skips catalog files (README.md, index files) that don't require frontmatter.
        Returns exit code 0 if all pass, exit code 1 if any fail
    #>

    $files = @(Get-ChildItem -Path '.claude/commands' -Filter '*.md' -Recurse -ErrorAction SilentlyContinue)

    if ($files.Count -eq 0) {
        Write-Host "No slash command files found, skipping validation"
        return 0
    }

    # Exclude catalog/reference files that don't need frontmatter
    $catalogFiles = @('README.md', 'INDEX.md', 'CATALOG.md')
    $commandFiles = @($files | Where-Object { $_.Name -notin $catalogFiles })

    if ($commandFiles.Count -eq 0) {
        Write-Host "No slash command files found (only catalog files), skipping validation"
        return 0
    }

    Write-Host "Found $($commandFiles.Count) slash command file(s) to validate (excluding catalog files)"

    $failedFiles = @()
    $validationScript = './.claude/skills/slashcommandcreator/scripts/Validate-SlashCommand.ps1'

    foreach ($file in $commandFiles) {
        Write-Host "`nValidating: $($file.FullName)"

        & $validationScript -Path $file.FullName

        if ($LASTEXITCODE -ne 0) {
            $failedFiles += $file.Name
        }
    }

    if ($failedFiles.Count -gt 0) {
        Write-Host "`n[FAIL] VALIDATION FAILED: $($failedFiles.Count) file(s) failed" -ForegroundColor Red
        Write-Host "`nFailed files:" -ForegroundColor Yellow
        $failedFiles | ForEach-Object { Write-Host "  - $_" }
        return 1
    } else {
        Write-Host "`n[PASS] All slash commands passed quality gates" -ForegroundColor Green
        return 0
    }
}

Export-ModuleMember -Function Invoke-SlashCommandValidation
