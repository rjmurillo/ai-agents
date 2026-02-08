<#
.SYNOPSIS
    Check if staged files qualify for investigation-only QA skip.

.DESCRIPTION
    Tests whether the currently staged git files are all within the
    investigation-only allowlist defined in ADR-034. This allows agents
    to check eligibility before committing with "SKIPPED: investigation-only".

.EXAMPLE
    pwsh .claude/skills/session/scripts/Test-InvestigationEligibility.ps1

    Returns:
    {
      "Eligible": true,
      "StagedFiles": [".agents/sessions/2025-01-01-session-01.md"],
      "Violations": [],
      "AllowedPaths": [".agents/sessions/", ".agents/analysis/", ...]
    }

.NOTES
    EXIT CODES:
    0 - Success (always returns 0, eligibility is in output)

    ALLOWLIST:
    Source of truth: scripts/modules/InvestigationAllowlist.psm1 (per Issue #840)
    Patterns defined centrally per ADR-034.

    See: .agents/architecture/ADR-034-investigation-session-qa-exemption.md
    See: ADR-035 Exit Code Standardization

.OUTPUTS
    JSON object with:
    - Eligible: boolean indicating if all files are in allowlist
    - StagedFiles: array of all staged file paths
    - Violations: array of files not in allowlist (empty if eligible)
    - AllowedPaths: reference list of allowed path prefixes
#>
[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'

# Import shared allowlist module (single source of truth per Issue #840)
$modulePath = Join-Path $PSScriptRoot '..' '..' '..' '..' 'scripts' 'modules' 'InvestigationAllowlist.psm1'
Import-Module (Resolve-Path $modulePath) -Force

$allowedPaths = Get-InvestigationAllowlistDisplay

# Get staged files - split by newlines to get array of individual file paths
$gitOutput = & git diff --cached --name-only 2>$null
$stagedFiles = @($gitOutput -split "`r?`n" | Where-Object { $_ -and $_.Trim() -ne '' })

if ($LASTEXITCODE -ne 0) {
    # Not in a git repository or other git error
    [PSCustomObject]@{
        Eligible     = $false
        StagedFiles  = @()
        Violations   = @()
        AllowedPaths = $allowedPaths
        Error        = "Not in a git repository or git command failed"
    } | ConvertTo-Json -Depth 3
    exit 0
}

# Check each staged file against allowlist
$violations = [System.Collections.Generic.List[string]]::new()

foreach ($file in $stagedFiles) {
    if (-not (Test-FileMatchesAllowlist -FilePath $file)) {
        $violations.Add($file)
    }
}

# Build result
$result = [PSCustomObject]@{
    Eligible     = ($violations.Count -eq 0)
    StagedFiles  = $stagedFiles
    Violations   = $violations.ToArray()
    AllowedPaths = $allowedPaths
}

# Output JSON
$result | ConvertTo-Json -Depth 3
