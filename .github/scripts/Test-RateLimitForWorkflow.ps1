<#
.SYNOPSIS
    Check GitHub API rate limits before workflow execution.

.DESCRIPTION
    Wrapper script for Test-WorkflowRateLimit from GitHubHelpers module.
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

.OUTPUTS
    Sets GITHUB_OUTPUT: core_remaining=N
    Writes to GITHUB_STEP_SUMMARY: Rate limit status table
    Exit code 0 = sufficient rate limit, 1 = rate limit too low

.NOTES
    Created per issue #273 (DRY rate limit code).
    Uses Test-WorkflowRateLimit from GitHubHelpers.psm1.
#>

[CmdletBinding()]
param(
    [int]$CoreThreshold = 100,
    [int]$GraphQLThreshold = 50
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

# Import the shared module
$modulePath = Join-Path $PSScriptRoot ".." ".." ".claude" "skills" "github" "modules" "GitHubHelpers.psm1"
if (-not (Test-Path $modulePath)) {
    Write-Error "GitHubHelpers module not found at: $modulePath"
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
    Write-Host "::error::Failed to check rate limits: $_"
    exit 1
}

# Output status
Write-Host "Rate limits - Core: $($result.CoreRemaining), Thresholds: core=$CoreThreshold, graphql=$GraphQLThreshold"
Write-Host $result.SummaryMarkdown

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
    Write-Host "::error::Rate limit too low to proceed"
    exit 1
}

exit 0
