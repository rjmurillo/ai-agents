<#
.SYNOPSIS
    Check if staged files qualify for investigation-only QA skip.

.DESCRIPTION
    Tests whether the currently staged git files are all within the
    investigation-only allowlist defined in ADR-034. This allows agents
    to check eligibility before committing with "SKIPPED: investigation-only".

.OUTPUTS
    JSON object with:
    - Eligible: boolean indicating if all files are in allowlist
    - StagedFiles: array of all staged file paths
    - Violations: array of files not in allowlist (empty if eligible)
    - AllowedPaths: reference list of allowed path prefixes

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
    Must match exactly with scripts/Validate-Session.ps1 $InvestigationAllowlist

    See: ADR-034 Investigation Session QA Exemption
#>
[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'

# Investigation-only allowlist patterns (must match Validate-Session.ps1)
$investigationAllowlist = @(
    '^\.agents/sessions/',        # Session logs
    '^\.agents/analysis/',        # Investigation outputs
    '^\.agents/retrospective/',   # Learnings
    '^\.serena/memories($|/)',    # Cross-session context
    '^\.agents/security/'         # Security assessments
)

# Human-readable allowed paths (for display)
$allowedPaths = @(
    '.agents/sessions/',
    '.agents/analysis/',
    '.agents/retrospective/',
    '.serena/memories/',
    '.agents/security/'
)

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
    # Normalize path separators
    $normalizedFile = $file -replace '\\', '/'

    $isAllowed = $false
    foreach ($pattern in $investigationAllowlist) {
        if ($normalizedFile -match $pattern) {
            $isAllowed = $true
            break
        }
    }

    if (-not $isAllowed) {
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
