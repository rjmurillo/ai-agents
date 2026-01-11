<#
.SYNOPSIS
    Check GitHub API rate limits before workflow execution.

.DESCRIPTION
    Wrapper script for Test-WorkflowRateLimit from GitHubCore module.
    Designed for GitHub Actions workflow integration per ADR-006
    (thin workflows, testable modules).

    Outputs GitHub Actions environment variables and step summary.

.PARAMETER CoreThreshold
    Minimum remaining core API calls required. Default: 100.

.PARAMETER GraphQLThreshold
    Minimum remaining GraphQL API calls required. Default: 50.

.EXAMPLE
    # In GitHub Actions workflow:
    pwsh .github/scripts/Test-RateLimitForWorkflow.ps1

.EXAMPLE
    # With custom thresholds:
    pwsh .github/scripts/Test-RateLimitForWorkflow.ps1 -CoreThreshold 200 -GraphQLThreshold 100

.NOTES
  EXIT CODES:
  0  - Success: Sufficient rate limit remaining to proceed
  1  - Error: Rate limit too low to proceed or failed to check rate limits

  See: ADR-035 Exit Code Standardization
  Created per issue #273 (DRY rate limit code).
  Uses Test-WorkflowRateLimit from GitHubCore.psm1.

.OUTPUTS
    Sets GITHUB_OUTPUT: core_remaining=N
    Writes to GITHUB_STEP_SUMMARY: Rate limit status table
    Exit code 0 = sufficient rate limit, 1 = rate limit too low
#>

[CmdletBinding()]
param(
    [int]$CoreThreshold = 100,
    [int]$GraphQLThreshold = 50
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

# Import the shared module
$modulePath = Join-Path $PSScriptRoot ".." ".." ".claude" "skills" "github" "modules" "GitHubCore.psm1"
if (-not (Test-Path $modulePath)) {
    Write-Error "GitHubCore module not found at: $modulePath"
    exit 1
}

Import-Module $modulePath -Force

# Check rate limits with specified thresholds
$thresholds = @{
    'core'    = $CoreThreshold
    'graphql' = $GraphQLThreshold
}

try {
    $result = Test-WorkflowRateLimit -ResourceThresholds $thresholds
}
catch {
    Write-Error "Failed to check rate limits: $_"
    exit 1
}

# Output status
Write-Output "Rate limits - Core: $($result.CoreRemaining), Thresholds: core=$CoreThreshold, graphql=$GraphQLThreshold"
Write-Output $result.SummaryMarkdown

# Write to GitHub Actions outputs if available
if ($env:GITHUB_OUTPUT) {
    "core_remaining=$($result.CoreRemaining)" | Out-File $env:GITHUB_OUTPUT -Append
}

# Write to step summary if available
if ($env:GITHUB_STEP_SUMMARY) {
    $result.SummaryMarkdown | Out-File $env:GITHUB_STEP_SUMMARY -Append
}

# Exit with appropriate code
if (-not $result.Success) {
    Write-Error "Rate limit too low to proceed"
    exit 1
}

exit 0
