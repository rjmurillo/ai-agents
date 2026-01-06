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
    $template = & .claude/skills/session/init/scripts/Extract-SessionTemplate.ps1
    Write-Output $template

.EXAMPLE
    & .claude/skills/session/init/scripts/Extract-SessionTemplate.ps1 -ProtocolPath /custom/path/SESSION-PROTOCOL.md

.NOTES
    Exit Codes:
    - 0: Success
    - 1: Protocol file not found
    - 2: Template section not found
#>

[CmdletBinding()]
param(
    [Parameter()]
    [string]$ProtocolPath = ".agents/SESSION-PROTOCOL.md"
)

$ErrorActionPreference = 'Continue'

# Resolve path relative to repository root
$repoRoot = git rev-parse --show-toplevel 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Error "Not in a git repository"
    exit 1
}

$fullPath = Join-Path $repoRoot $ProtocolPath

if (-not (Test-Path $fullPath)) {
    Write-Error "Protocol file not found: $fullPath"
    exit 1
}

# Read file content
$content = Get-Content -Path $fullPath -Raw -ErrorAction Stop

# Extract template using regex
# Pattern: ## Session Log Template ... ```markdown ... ```
$pattern = '(?s)## Session Log Template.*?```markdown\s*(.*?)\s*```'

if ($content -match $pattern) {
    $template = $Matches[1]

    # Output the template
    Write-Output $template
    exit 0
} else {
    Write-Error "Template section not found in $ProtocolPath"
    exit 2
}
