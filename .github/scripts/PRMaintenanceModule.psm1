<#
.SYNOPSIS
    PowerShell module for PR Maintenance workflow operations.

.DESCRIPTION
    Extracts business logic from pr-maintenance.yml workflow per ADR-006
    (Thin Workflows, Testable Modules). Contains functions for:
    - Rate limit validation with multi-resource thresholds
    - Log parsing and metrics extraction
    - Summary generation for GitHub Actions
    - Alert issue body generation

    For GitHub operations (creating issues, posting comments), use the
    dedicated skill scripts in .claude/skills/github/.

.NOTES
    Import this module in workflow scripts:
    Import-Module ./.github/scripts/PRMaintenanceModule.psm1

    ADR-006: Workflows orchestrate only; all logic in PowerShell modules.
#>

#Requires -Version 7.0

$ErrorActionPreference = 'Stop'

#region Rate Limit Checking

function Test-WorkflowRateLimit {
    <#
    .SYNOPSIS
        Checks GitHub API rate limits before workflow execution.

    .DESCRIPTION
        Validates that all required API resource types have sufficient
        remaining quota. Returns structured results for workflow decisions
        and generates a summary table for GitHub Actions.

    .PARAMETER ResourceThresholds
        Hashtable of resource names to minimum remaining threshold.
        Defaults to conservative values for PR maintenance operations.

    .OUTPUTS
        PSCustomObject with properties:
        - Success: Boolean indicating all thresholds met
        - Resources: Hashtable of resource status details
        - SummaryMarkdown: Formatted markdown table for step summary

    .EXAMPLE
        $result = Test-WorkflowRateLimit
        if (-not $result.Success) {
            Write-Error "Rate limit too low"
            exit 1
        }
        $result.SummaryMarkdown | Out-File $env:GITHUB_STEP_SUMMARY -Append

    .EXAMPLE
        # Custom thresholds
        $result = Test-WorkflowRateLimit -ResourceThresholds @{
            'core' = 200
            'graphql' = 50
        }
    #>
    [CmdletBinding()]
    [OutputType([PSCustomObject])]
    param(
        [hashtable]$ResourceThresholds = @{
            'core'        = 100    # General API calls
            'search'      = 15     # Search API (30/min limit)
            'code_search' = 5      # Code search (10/min limit)
            'graphql'     = 100    # GraphQL API
        }
    )

    # Fetch rate limit data
    $rateLimitJson = gh api rate_limit 2>&1
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to fetch rate limits: $rateLimitJson"
    }

    $rateLimit = $rateLimitJson | ConvertFrom-Json

    # Build results
    $resources = @{}
    $allPassed = $true
    $summaryLines = @(
        "### API Rate Limit Status",
        "",
        "| Resource | Remaining | Threshold | Status |",
        "|----------|-----------|-----------|--------|"
    )

    foreach ($resource in $ResourceThresholds.Keys) {
        $remaining = $rateLimit.resources.$resource.remaining
        $limit = $rateLimit.resources.$resource.limit
        $reset = $rateLimit.resources.$resource.reset
        $threshold = $ResourceThresholds[$resource]
        $passed = $remaining -ge $threshold

        if (-not $passed) {
            $allPassed = $false
        }

        $status = if ($passed) { "OK" } else { "TOO LOW" }
        $statusIcon = if ($passed) { "✅" } else { "❌" }

        $resources[$resource] = @{
            Remaining = $remaining
            Limit     = $limit
            Reset     = $reset
            Threshold = $threshold
            Passed    = $passed
        }

        $summaryLines += "| $resource | $remaining | $threshold | $statusIcon $status |"
    }

    return [PSCustomObject]@{
        Success         = $allPassed
        Resources       = $resources
        SummaryMarkdown = $summaryLines -join "`n"
        CoreRemaining   = $rateLimit.resources.core.remaining
    }
}

#endregion

#region Log Parsing

function Get-MaintenanceResults {
    <#
    .SYNOPSIS
        Parses PR maintenance log file to extract metrics.

    .DESCRIPTION
        Reads the maintenance log and extracts key metrics:
        - PRs processed count
        - Comments acknowledged count
        - Conflicts resolved count
        - List of blocked PRs requiring human action

    .PARAMETER LogPath
        Path to the PR maintenance log file.

    .OUTPUTS
        PSCustomObject with properties:
        - Processed: Number of PRs processed
        - Acknowledged: Number of comments acknowledged
        - Resolved: Number of conflicts resolved
        - BlockedPRs: Array of blocked PR descriptions
        - HasBlocked: Boolean indicating if any PRs are blocked

    .EXAMPLE
        $results = Get-MaintenanceResults -LogPath '.agents/logs/pr-maintenance.log'
        Write-Host "Processed: $($results.Processed) PRs"
    #>
    [CmdletBinding()]
    [OutputType([PSCustomObject])]
    param(
        [Parameter(Mandatory)]
        [string]$LogPath
    )

    if (-not (Test-Path $LogPath)) {
        Write-Warning "Log file not found: $LogPath"
        return [PSCustomObject]@{
            Processed    = 0
            Acknowledged = 0
            Resolved     = 0
            BlockedPRs   = @()
            HasBlocked   = $false
        }
    }

    $log = Get-Content $LogPath -Raw

    # Extract metrics using regex
    $processed = 0
    $acknowledged = 0
    $resolved = 0

    if ($log -match 'PRs Processed:\s*(\d+)') {
        $processed = [int]$Matches[1]
    }

    if ($log -match 'Comments Acknowledged:\s*(\d+)') {
        $acknowledged = [int]$Matches[1]
    }

    if ($log -match 'Conflicts Resolved:\s*(\d+)') {
        $resolved = [int]$Matches[1]
    }

    # Extract blocked PRs section
    $blockedPRs = @()
    # Match from "Blocked PRs" header to end of section (next blank line or end of file)
    if ($log -match '(?s)Blocked PRs[^\n]*:\s*\n(.+?)(?:\n\s*\n|\z)') {
        $blockedSection = $Matches[1]
        $blockedPRs = @($blockedSection -split '\n' |
            Where-Object { $_ -match 'PR\s*#\d+' } |
            ForEach-Object { $_.Trim() } |
            Where-Object { $_ })
    }

    return [PSCustomObject]@{
        Processed    = $processed
        Acknowledged = $acknowledged
        Resolved     = $resolved
        BlockedPRs   = $blockedPRs
        HasBlocked   = $blockedPRs.Count -gt 0
    }
}

#endregion

#region Summary Generation

function New-MaintenanceSummary {
    <#
    .SYNOPSIS
        Generates GitHub Actions step summary for PR maintenance run.

    .DESCRIPTION
        Creates formatted markdown summary including:
        - Run timestamp and mode (dry run vs live)
        - Metrics table (PRs processed, comments, conflicts)
        - Blocked PRs list (if any)
        - Rate limit status after run

    .PARAMETER Results
        PSCustomObject from Get-MaintenanceResults.

    .PARAMETER DryRun
        Whether the run was in dry-run mode.

    .PARAMETER CoreRemaining
        Remaining core API rate limit after run.

    .PARAMETER RunUrl
        URL to the workflow run for reference.

    .OUTPUTS
        System.String - Formatted markdown summary.

    .EXAMPLE
        $summary = New-MaintenanceSummary -Results $results -DryRun $true -CoreRemaining 4500
        $summary | Out-File $env:GITHUB_STEP_SUMMARY -Append
    #>
    [CmdletBinding()]
    [OutputType([string])]
    param(
        [Parameter(Mandatory)]
        [PSCustomObject]$Results,

        [bool]$DryRun = $true,

        [int]$CoreRemaining = 0,

        [string]$RunUrl = ''
    )

    $timestamp = Get-Date -Format 'yyyy-MM-dd HH:mm:ss UTC'
    $dryRunText = if ($DryRun) { 'Yes' } else { 'No' }

    $summary = @"
## PR Maintenance Summary

**Run Time**: $timestamp
**Dry Run**: $dryRunText

| Metric | Value |
|--------|-------|
| PRs Processed | $($Results.Processed) |
| Comments Acknowledged | $($Results.Acknowledged) |
| Conflicts Resolved | $($Results.Resolved) |

"@

    if ($Results.HasBlocked) {
        $blockedList = $Results.BlockedPRs -join "`n"
        $summary += @"

### Blocked PRs (Require Human Action)

``````
$blockedList
``````

"@
    }

    $summary += @"

### Rate Limit After Run

- Core API: $CoreRemaining remaining

"@

    if ($RunUrl) {
        $summary += @"

---
[View Logs]($RunUrl)
"@
    }

    return $summary
}

#endregion

#region Alert Generation

function New-BlockedPRsAlertBody {
    <#
    .SYNOPSIS
        Generates issue body for blocked PRs alert.

    .DESCRIPTION
        Creates formatted markdown body for the alert issue
        created when PRs require human intervention.

    .PARAMETER BlockedPRs
        Array of blocked PR descriptions.

    .PARAMETER RunUrl
        URL to the workflow run.

    .OUTPUTS
        System.String - Formatted issue body.

    .EXAMPLE
        $body = New-BlockedPRsAlertBody -BlockedPRs @("PR #123 - conflicts") -RunUrl $url
    #>
    [CmdletBinding()]
    [OutputType([string])]
    param(
        [Parameter(Mandatory)]
        [AllowEmptyCollection()]
        [string[]]$BlockedPRs,

        [string]$RunUrl = ''
    )

    $blockedList = $BlockedPRs -join "`n"

    $body = @"
## Blocked PRs

The automated PR maintenance workflow encountered PRs that require human action:

``````
$blockedList
``````

**Action Required**: Review the listed PRs and address blocking issues.

"@

    if ($RunUrl) {
        $body += @"

**Workflow Run**: $RunUrl

"@
    }

    $body += @"

---
<sub>Powered by [PR Maintenance](https://github.com/rjmurillo/ai-agents) workflow</sub>
"@

    return $body
}

function New-WorkflowFailureAlertBody {
    <#
    .SYNOPSIS
        Generates issue body for workflow failure alert.

    .DESCRIPTION
        Creates formatted markdown body for the alert issue
        created when the workflow fails.

    .PARAMETER RunUrl
        URL to the workflow run.

    .PARAMETER TriggerEvent
        The event that triggered the workflow (schedule, workflow_dispatch).

    .OUTPUTS
        System.String - Formatted issue body.

    .EXAMPLE
        $body = New-WorkflowFailureAlertBody -RunUrl $url -TriggerEvent 'schedule'
    #>
    [CmdletBinding()]
    [OutputType([string])]
    param(
        [string]$RunUrl = '',

        [string]$TriggerEvent = 'unknown'
    )

    $timestamp = Get-Date -Format 'yyyy-MM-dd HH:mm:ss UTC'

    $body = @"
## Workflow Failure

The PR maintenance workflow failed during execution.

**Run**: $RunUrl
**Trigger**: $TriggerEvent
**Time**: $timestamp

**Action Required**: Investigate workflow logs and resolve the issue.

---
<sub>Powered by [PR Maintenance](https://github.com/rjmurillo/ai-agents) workflow</sub>
"@

    return $body
}

#endregion

#region Environment Validation

function Test-WorkflowEnvironment {
    <#
    .SYNOPSIS
        Validates required tools are available for workflow execution.

    .DESCRIPTION
        Checks that PowerShell, gh CLI, and git are available and
        returns version information for the step summary.

    .OUTPUTS
        PSCustomObject with properties:
        - Valid: Boolean indicating all tools available
        - Versions: Hashtable of tool versions
        - SummaryMarkdown: Formatted markdown for step summary

    .EXAMPLE
        $env = Test-WorkflowEnvironment
        if (-not $env.Valid) {
            throw "Missing required tools"
        }
    #>
    [CmdletBinding()]
    [OutputType([PSCustomObject])]
    param()

    $versions = @{}
    $valid = $true

    # PowerShell version
    $versions['PowerShell'] = $PSVersionTable.PSVersion.ToString()

    # gh CLI version
    try {
        $ghVersion = (gh --version | Select-Object -First 1) -replace 'gh version\s*', ''
        $versions['gh'] = $ghVersion
    }
    catch {
        $versions['gh'] = 'NOT FOUND'
        $valid = $false
    }

    # git version
    try {
        $gitVersion = (git --version) -replace 'git version\s*', ''
        $versions['git'] = $gitVersion
    }
    catch {
        $versions['git'] = 'NOT FOUND'
        $valid = $false
    }

    $summaryLines = @(
        "### Environment Validation",
        "",
        "| Tool | Version |",
        "|------|---------|"
    )

    foreach ($tool in $versions.Keys) {
        $summaryLines += "| $tool | $($versions[$tool]) |"
    }

    return [PSCustomObject]@{
        Valid           = $valid
        Versions        = $versions
        SummaryMarkdown = $summaryLines -join "`n"
    }
}

#endregion

#region Module Exports

Export-ModuleMember -Function @(
    'Test-WorkflowRateLimit',
    'Get-MaintenanceResults',
    'New-MaintenanceSummary',
    'New-BlockedPRsAlertBody',
    'New-WorkflowFailureAlertBody',
    'Test-WorkflowEnvironment'
)

#endregion
