#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Extract session log template from SESSION-PROTOCOL.md

.DESCRIPTION
    Reads SESSION-PROTOCOL.md and extracts the canonical session log template
    from the "Session Log Template" section. Returns the template content
    for use in creating new session logs.

.PARAMETER ProtocolPath
    Path to SESSION-PROTOCOL.md file. Defaults to .agents/SESSION-PROTOCOL.md

.OUTPUTS
    String containing the session log template

.EXAMPLE
    $template = & .claude/skills/session-init/scripts/Extract-SessionTemplate.ps1
    Write-Output $template

.EXAMPLE
    & .claude/skills/session-init/scripts/Extract-SessionTemplate.ps1 -ProtocolPath /custom/path/SESSION-PROTOCOL.md

.NOTES
    Exit Codes:
    - 0: Success
    - 1: Git repository error or protocol file not found
    - 2: Template section not found or other expected errors
#>

[CmdletBinding()]
param(
    [Parameter()]
    [string]$ProtocolPath = ".agents/SESSION-PROTOCOL.md"
)

$ErrorActionPreference = 'Stop'

try {
    # Resolve path relative to repository root
    $repoRootOutput = git rev-parse --show-toplevel 2>&1
    if ($LASTEXITCODE -ne 0) {
        $errorDetails = $repoRootOutput -join "`n"
        throw [System.InvalidOperationException]::new(
            "Not in a git repository. Git error (exit code $LASTEXITCODE): $errorDetails`n`nEnsure you are in a git repository by running 'git status'."
        )
    }
    $repoRoot = $repoRootOutput.Trim()

    $fullPath = Join-Path $repoRoot $ProtocolPath

    if (-not (Test-Path $fullPath)) {
        throw [System.IO.FileNotFoundException]::new(
            "Protocol file not found: $fullPath`n`nEnsure SESSION-PROTOCOL.md exists at $ProtocolPath.`n`nExpected path: $fullPath"
        )
    }

    # Read file content with specific error handling
    try {
        $content = Get-Content -Path $fullPath -Raw -ErrorAction Stop
    } catch [System.UnauthorizedAccessException] {
        throw [System.UnauthorizedAccessException]::new(
            "Permission denied reading protocol file: $fullPath`n`nEnsure you have read permissions on the file.`n`nTry: chmod +r '$fullPath'",
            $_.Exception
        )
    } catch [System.IO.IOException] {
        throw [System.IO.IOException]::new(
            "Failed to read protocol file: $fullPath`n`nPossible causes: file in use, corrupted filesystem, or encoding issues.`n`nError: $($_.Exception.Message)",
            $_.Exception
        )
    }

    # Extract template using regex
    # Pattern: ## Session Log Template ... ```markdown ... ```
    $pattern = '(?s)## Session Log Template.*?```markdown\s*(.*?)\s*```'

    if ($content -match $pattern) {
        $template = $Matches[1]
        
        # Validate extracted template is not empty
        if ([string]::IsNullOrWhiteSpace($template)) {
            throw [System.InvalidOperationException]::new(
                "Extracted template is empty.`n`nProtocol file: $fullPath`n`nThe '## Session Log Template' section exists but contains no content."
            )
        }

        # Output the template
        Write-Output $template
        exit 0
    } else {
        throw [System.InvalidOperationException]::new(
            "Template section not found in $ProtocolPath`n`nProtocol file: $fullPath`n`nExpected section: ## Session Log Template`n`nEnsure the protocol file contains a properly formatted template section with markdown code fence."
        )
    }

} catch [System.InvalidOperationException] {
    # This exception covers both git errors AND template errors
    if ($_.Exception.Message -match "Not in a git repository") {
        # Git repository error - exit code 1
        Write-Host $_.Exception.Message -ForegroundColor Red
        exit 1
    } else {
        # Empty template or template section not found - exit code 2
        Write-Host $_.Exception.Message -ForegroundColor Red
        exit 2
    }
} catch [System.IO.FileNotFoundException] {
    # File not found - exit code 1 per documentation
    Write-Host $_.Exception.Message -ForegroundColor Red
    exit 1
} catch [System.UnauthorizedAccessException], [System.IO.IOException] {
    # File access errors - exit code 2
    Write-Host $_.Exception.Message -ForegroundColor Red
    exit 2
} catch {
    # Unexpected errors - provide full diagnostic information
    Write-Host "UNEXPECTED ERROR in Extract-SessionTemplate" -ForegroundColor Red
    Write-Host "Exception Type: $($_.Exception.GetType().FullName)" -ForegroundColor Red
    Write-Host "Message: $($_.Exception.Message)" -ForegroundColor Red
    Write-Host "Protocol Path: $ProtocolPath" -ForegroundColor Red
    if ($fullPath) {
        Write-Host "Full Path: $fullPath" -ForegroundColor Red
    }
    Write-Host "Stack Trace: $($_.ScriptStackTrace)" -ForegroundColor Red
    Write-Host "" -ForegroundColor Red
    Write-Host "This is a bug. Please report this error with the above details." -ForegroundColor Red
    exit 1
}
