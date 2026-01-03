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
        Returns exit code 0 if all pass, exit code 1 if any fail
    #>

    $files = Get-ChildItem -Path '.claude/commands' -Filter '*.md' -Recurse

    if ($files.Count -eq 0) {
        Write-Host "No slash command files found, skipping validation"
        return 0
    }

    Write-Host "Found $($files.Count) slash command file(s) to validate"

    $failedFiles = @()
    $validationScript = './.claude/skills/slashcommandcreator/scripts/Validate-SlashCommand.ps1'

    foreach ($file in $files) {
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
