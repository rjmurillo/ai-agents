<#
.SYNOPSIS
    Auto-lints markdown files after Write/Edit operations.

.DESCRIPTION
    Claude Code PostToolUse hook that automatically runs markdownlint-cli2 --fix
    on .md files after they are written or edited. This ensures consistent markdown
    formatting across the project without manual intervention.

    Part of the hooks expansion implementation (Issue #773, Phase 1).

.NOTES
    Hook Type: PostToolUse
    Matcher: Write|Edit
    Filter: .md files only (NOT .ps1!)
    Exit Codes:
        0 = Always (non-blocking hook, all errors are warnings)

.LINK
    .agents/analysis/claude-code-hooks-opportunity-analysis.md
#>
[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Continue'  # Non-blocking hook

function Get-FilePathFromInput {
    param($HookInput)

    if ($HookInput.PSObject.Properties['tool_input'] -and
        $HookInput.tool_input.PSObject.Properties['file_path']) {
        return $HookInput.tool_input.file_path
    }
    return $null
}

function Get-ProjectDirectory {
    param($HookInput)

    if (-not [string]::IsNullOrWhiteSpace($env:CLAUDE_PROJECT_DIR)) {
        return $env:CLAUDE_PROJECT_DIR
    }
    return $HookInput.cwd
}

function Test-ShouldLintFile {
    param([string]$FilePath)

    if ([string]::IsNullOrWhiteSpace($FilePath)) {
        return $false
    }

    if (-not $FilePath.EndsWith('.md', [StringComparison]::OrdinalIgnoreCase)) {
        return $false
    }

    if (-not (Test-Path $FilePath)) {
        Write-Warning "Markdown file does not exist: $FilePath"
        return $false
    }

    return $true
}

try {
    if (-not [Console]::IsInputRedirected) {
        exit 0
    }

    $inputJson = [Console]::In.ReadToEnd()
    if ([string]::IsNullOrWhiteSpace($inputJson)) {
        exit 0
    }

    $hookInput = $inputJson | ConvertFrom-Json -ErrorAction Stop
    $filePath = Get-FilePathFromInput -HookInput $hookInput

    if (-not (Test-ShouldLintFile -FilePath $filePath)) {
        exit 0
    }

    $projectDir = Get-ProjectDirectory -HookInput $hookInput
    $previousLocation = Get-Location

    try {
        if (-not [string]::IsNullOrWhiteSpace($projectDir)) {
            Set-Location $projectDir
        }

        $lintOutput = npx markdownlint-cli2 --fix "$filePath" 2>&1
        $lintExitCode = $LASTEXITCODE

        if ($lintExitCode -ne 0) {
            # Validate output before processing
            $outputString = $lintOutput | Out-String
            if ([string]::IsNullOrWhiteSpace($outputString)) {
                Write-Warning "Markdown linting failed for $filePath (exit $lintExitCode) with no output. Linter may not be installed."
                Write-Output "`n**Markdown Auto-Lint WARNING**: Linter failed with no output. Verify installation: ``npm list markdownlint-cli2```n"
            }
            else {
                # Safe substring with length validation
                $errorSummary = $outputString.Substring(0, [Math]::Min(200, $outputString.Length))
                Write-Warning "Markdown linting failed for $filePath (exit $lintExitCode): $errorSummary"
                Write-Output "`n**Markdown Auto-Lint WARNING**: Failed to lint ``$filePath``. Exit code: $lintExitCode. Run manually: ``npx markdownlint-cli2 --fix '$filePath'```n"
            }
        }
        else {
            Write-Output "`n**Markdown Auto-Lint**: Fixed formatting in ``$filePath```n"
        }
    }
    finally {
        Set-Location $previousLocation
    }
}
catch [System.ArgumentException], [System.InvalidOperationException] {
    # JSON parsing failures from ConvertFrom-Json
    Write-Warning "Markdown auto-lint: Failed to parse hook input JSON - $($_.Exception.Message)"
}
catch [System.IO.IOException], [System.UnauthorizedAccessException] {
    Write-Warning "Markdown auto-lint: File system error for $filePath - $($_.Exception.Message)"
    Write-Output "`n**Markdown Auto-Lint ERROR**: Cannot access file ``$filePath``. Check permissions.`n"
}
catch {
    Write-Warning "Markdown auto-lint unexpected error: $($_.Exception.GetType().FullName) - $($_.Exception.Message)"
    Write-Output "`n**Markdown Auto-Lint ERROR**: Unexpected error. Hook may need attention.`n"
}

exit 0
