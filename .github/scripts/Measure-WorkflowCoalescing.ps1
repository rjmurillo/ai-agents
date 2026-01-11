<#
.SYNOPSIS
    Measures workflow run coalescing effectiveness by analyzing GitHub Actions runs.

.DESCRIPTION
    Queries GitHub Actions API to collect workflow run data, detects overlapping runs
    within the same concurrency group, and calculates metrics for coalescing effectiveness,
    race conditions, and cancellation performance.

.PARAMETER Since
    Number of days to analyze (default: 30)

.PARAMETER Repository
    Repository in format owner/repo (default: current repo from git remote)

.PARAMETER Workflows
    Array of workflow names to analyze (default: all AI-powered workflows)

.PARAMETER Output
    Output format: Json, Markdown, or Summary (default: Markdown)

.PARAMETER OutputPath
    Path to save report (default: .agents/metrics/workflow-coalescing.md)

.EXAMPLE
    .\Measure-WorkflowCoalescing.ps1
    Analyzes last 30 days with markdown output

.EXAMPLE
    .\Measure-WorkflowCoalescing.ps1 -Since 90 -Output Json
    Analyzes last 90 days with JSON output

.EXAMPLE
    .\Measure-WorkflowCoalescing.ps1 -Workflows @('ai-pr-quality-gate', 'ai-spec-validation')
    Analyzes specific workflows only

.NOTES
    EXIT CODES:
    0  - Success: Analysis completed
    1  - Error: Failed to fetch workflow data or process results

    See: ADR-035 Exit Code Standardization
#>

[CmdletBinding()]
param(
    [Parameter()]
    [int]$Since = 30,

    [Parameter()]
    [string]$Repository,

    [Parameter()]
    [string[]]$Workflows = @(
        'ai-pr-quality-gate',
        'ai-spec-validation',
        'ai-session-protocol',
        'pr-validation',
        'label-pr',
        'memory-validation',
        'auto-assign-reviewer'
    ),

    [Parameter()]
    [ValidateSet('Json', 'Markdown', 'Summary')]
    [string]$Output = 'Markdown',

    [Parameter()]
    [string]$OutputPath = '.agents/metrics/workflow-coalescing.md'
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

# Import common functions
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$commonModule = Join-Path $scriptDir 'AIReviewCommon.psm1'
if (Test-Path $commonModule) {
    Import-Module $commonModule -Force
}

function Test-Prerequisites {
    <#
    .SYNOPSIS
        Validates required tools and authentication.
    #>
    if (-not (Get-Command gh -ErrorAction SilentlyContinue)) {
        throw "GitHub CLI (gh) is not installed or not in PATH"
    }

    $authStatus = gh auth status 2>&1
    if ($LASTEXITCODE -ne 0) {
        throw "GitHub CLI is not authenticated. Run: gh auth login"
    }

    Write-Verbose "Prerequisites validated: gh CLI available and authenticated"
}

function Get-RepositoryContext {
    <#
    .SYNOPSIS
        Gets repository owner and name from git remote or parameter.
    #>
    param([string]$Repository)

    if ($Repository) {
        if ($Repository -match '^([^/]+)/([^/]+)$') {
            return @{
                Owner = $matches[1]
                Repo = $matches[2]
            }
        }
        throw "Repository must be in format 'owner/repo'"
    }

    try {
        $remote = git remote get-url origin 2>&1
        if ($remote -match 'github\.com[:/]([^/]+)/([^/\.]+)') {
            return @{
                Owner = $matches[1]
                Repo = $matches[2]
            }
        }
    }
    catch {
        throw "Could not determine repository from git remote. Use -Repository parameter"
    }

    throw "Could not determine repository context"
}

function Get-WorkflowRuns {
    <#
    .SYNOPSIS
        Queries GitHub Actions API for workflow runs.
    #>
    param(
        [string]$Owner,
        [string]$Repo,
        [DateTime]$StartDate,
        [string[]]$WorkflowNames
    )

    Write-Verbose "Querying workflow runs since $StartDate"
    
    $allRuns = @()
    $page = 1
    $perPage = 100
    $continueLoop = $true

    while ($continueLoop) {
        $apiUrl = "/repos/$Owner/$Repo/actions/runs?page=$page&per_page=$perPage"
        Write-Verbose "Fetching page $page from API: $apiUrl"
        
        $response = gh api $apiUrl --repo "$Owner/$Repo" --jq '.workflow_runs' | ConvertFrom-Json
        
        if (-not $response -or $response.Count -eq 0) {
            break
        }

        # Filter by workflow name
        $filteredRuns = $response | Where-Object {
            $workflowName = $_.name
            $WorkflowNames | Where-Object { $workflowName -like "*$_*" }
        }

        # Check if we've reached runs older than StartDate
        foreach ($run in $filteredRuns) {
            $runCreatedAt = [DateTime]::Parse($run.created_at)
            if ($runCreatedAt -lt $StartDate) {
                $continueLoop = $false
                break
            }
            # Only add runs within the date window
            if ($runCreatedAt -ge $StartDate) {
                $allRuns += $run
            }
        }
        
        # Stop if we got fewer results than requested (last page)
        if ($response.Count -lt $perPage) {
            break
        }
        
        $page++
    }

    Write-Verbose "Retrieved $($allRuns.Count) workflow runs"
    return $allRuns
}

function Get-ConcurrencyGroup {
    <#
    .SYNOPSIS
        Extracts concurrency group identifier from workflow run.
    #>
    param(
        [Parameter(Mandatory)]
        [object]$Run
    )

    # Extract PR number from event
    $prNumber = $null
    if ($Run.event -eq 'pull_request' -and $Run.pull_requests) {
        $prNumber = $Run.pull_requests[0].number
    }

    if ($prNumber) {
        # Determine workflow type for concurrency group naming
        $workflowName = $Run.name
        $groupPrefix = switch -Wildcard ($workflowName) {
            '*quality*' { 'ai-quality' }
            '*spec*' { 'spec-validation' }
            '*session*' { 'session-protocol' }
            '*label*' { 'label-pr' }
            '*memory*' { 'memory-validation' }
            '*assign*' { 'auto-assign' }
            default { 'pr-validation' }
        }
        return "$groupPrefix-$prNumber"
    }

    # Fallback: use workflow name + branch
    return "$($Run.name)-$($Run.head_branch)"
}

function Test-RunsOverlap {
    <#
    .SYNOPSIS
        Checks if two workflow runs overlap in time.
    #>
    param(
        [Parameter(Mandatory)]
        [object]$Run1,
        
        [Parameter(Mandatory)]
        [object]$Run2
    )

    $run1Start = [DateTime]::Parse($Run1.created_at)
    $run1End = [DateTime]::Parse($Run1.updated_at)
    $run2Start = [DateTime]::Parse($Run2.created_at)
    $run2End = [DateTime]::Parse($Run2.updated_at)

    # Run2 started before Run1 finished and not before Run1 started (treat equal start as overlap)
    return ($run2Start -lt $run1End -and $run2Start -ge $run1Start)
}

function Get-OverlappingRuns {
    <#
    .SYNOPSIS
        Finds overlapping runs within concurrency groups.
    #>
    param(
        [Parameter(Mandatory)]
        [array]$Runs
    )

    Write-Verbose "Analyzing $($Runs.Count) runs for overlaps"
    
    # Group runs by concurrency group
    $grouped = $Runs | Group-Object { Get-ConcurrencyGroup $_ }
    
    $overlaps = @()
    
    foreach ($group in $grouped) {
        $groupRuns = $group.Group | Sort-Object created_at
        
        for ($i = 0; $i -lt $groupRuns.Count - 1; $i++) {
            for ($j = $i + 1; $j -lt $groupRuns.Count; $j++) {
                $run1 = $groupRuns[$i]
                $run2 = $groupRuns[$j]
                
                if (Test-RunsOverlap -Run1 $run1 -Run2 $run2) {
                    $overlap = @{
                        ConcurrencyGroup = $group.Name
                        Run1 = $run1
                        Run2 = $run2
                        Run1Cancelled = $run1.conclusion -eq 'cancelled'
                        Run2Cancelled = $run2.conclusion -eq 'cancelled'
                        IsRaceCondition = ($run1.conclusion -ne 'cancelled' -and $run2.conclusion -ne 'cancelled')
                    }
                    $overlaps += $overlap
                    Write-Verbose "Overlap detected in $($group.Name): Run $($run1.id) vs $($run2.id)"
                }
            }
        }
    }
    
    Write-Verbose "Found $($overlaps.Count) overlapping run pairs"
    return $overlaps
}

function Get-CoalescingMetrics {
    <#
    .SYNOPSIS
        Calculates coalescing effectiveness metrics.
    #>
    param(
        [Parameter(Mandatory)]
        [array]$Runs,
        
        [Parameter(Mandatory)]
        [array]$Overlaps
    )

    $totalRuns = $Runs.Count
    $cancelledRuns = @($Runs | Where-Object { $_.conclusion -eq 'cancelled' }).Count
    
    # Deduplicate by run ID to avoid double-counting in multi-run overlaps
    $uniqueCancelledRunIds = [System.Collections.Generic.HashSet[int]]::new()
    $raceConditionOverlapCount = 0
    
    foreach ($overlap in $Overlaps) {
        if ($overlap.Run1Cancelled) {
            [void]$uniqueCancelledRunIds.Add($overlap.Run1.id)
        }
        if ($overlap.IsRaceCondition) {
            $raceConditionOverlapCount++
        }
    }
    
    $raceConditions = $raceConditionOverlapCount
    $successfulCoalescing = $uniqueCancelledRunIds.Count
    
    $coalescingEffectiveness = if ($successfulCoalescing + $raceConditions -gt 0) {
        ($successfulCoalescing / ($successfulCoalescing + $raceConditions)) * 100
    } else {
        0
    }
    
    $raceConditionRate = if ($totalRuns -gt 0) {
        ($raceConditions / $totalRuns) * 100
    } else {
        0
    }

    # Calculate average cancellation time
    $cancelledOverlaps = $Overlaps | Where-Object { $_.Run1Cancelled }
    $avgCancellationTime = if ($cancelledOverlaps.Count -gt 0) {
        $times = $cancelledOverlaps | ForEach-Object {
            $start = [DateTime]::Parse($_.Run1.created_at)
            $end = [DateTime]::Parse($_.Run1.updated_at)
            ($end - $start).TotalSeconds
        }
        ($times | Measure-Object -Average).Average
    } else {
        0
    }

    return @{
        TotalRuns = $totalRuns
        CancelledRuns = $cancelledRuns
        RaceConditions = $raceConditions
        SuccessfulCoalescing = $successfulCoalescing
        CoalescingEffectiveness = [math]::Round($coalescingEffectiveness, 2)
        RaceConditionRate = [math]::Round($raceConditionRate, 2)
        AvgCancellationTime = [math]::Round($avgCancellationTime, 2)
    }
}

function Format-MarkdownReport {
    <#
    .SYNOPSIS
        Generates markdown report from metrics data.
    #>
    param(
        [Parameter(Mandatory)]
        [hashtable]$Metrics,
        
        [Parameter(Mandatory)]
        [array]$Runs,
        
        [Parameter(Mandatory)]
        [array]$Overlaps,
        
        [Parameter(Mandatory)]
        [DateTime]$StartDate,
        
        [Parameter(Mandatory)]
        [DateTime]$EndDate,
        
        [Parameter(Mandatory)]
        [string[]]$Workflows
    )

    $report = @"
# Workflow Run Coalescing Metrics

## Report Period

- **From**: $($StartDate.ToString('yyyy-MM-dd'))
- **To**: $($EndDate.ToString('yyyy-MM-dd'))
- **Generated**: $([DateTime]::UtcNow.ToString('yyyy-MM-dd HH:mm:ss')) UTC

## Executive Summary

| Metric | Value | Target | Status |
|--------|-------|--------|--------|
| Coalescing Effectiveness | $($Metrics.CoalescingEffectiveness)% | 90% | $(if ($Metrics.CoalescingEffectiveness -ge 90) { '[On Track]' } else { '[Behind]' }) |
| Race Condition Rate | $($Metrics.RaceConditionRate)% | <10% | $(if ($Metrics.RaceConditionRate -le 10) { '[On Track]' } else { '[Behind]' }) |
| Average Cancellation Time | $($Metrics.AvgCancellationTime) seconds | <5s | $(if ($Metrics.AvgCancellationTime -le 5) { '[On Track]' } else { '[Behind]' }) |

## Workflow Run Analysis

### Total Runs Summary

- **Total Workflow Runs**: $($Metrics.TotalRuns)
- **Cancelled Runs**: $($Metrics.CancelledRuns)
- **Successful Coalescing Events**: $($Metrics.SuccessfulCoalescing)
- **Race Conditions Detected**: $($Metrics.RaceConditions)

### Runs by Workflow

| Workflow | Total Runs | Cancelled | Percentage |
|----------|------------|-----------|------------|
"@

    $workflowGroups = $Runs | Group-Object name | Sort-Object Count -Descending
    foreach ($wg in $workflowGroups) {
        $cancelled = @($wg.Group | Where-Object { $_.conclusion -eq 'cancelled' }).Count
        $pct = if ($wg.Count -gt 0) { [math]::Round(($cancelled / $wg.Count) * 100, 1) } else { 0 }
        $report += "`n| $($wg.Name) | $($wg.Count) | $cancelled | $pct% |"
    }

    $report += @"

### Concurrency Group Analysis

| Concurrency Group | Total Runs | Overlaps Detected |
|-------------------|------------|-------------------|
"@

    $concurrencyGroups = $Runs | Group-Object { Get-ConcurrencyGroup $_ } | Sort-Object Count -Descending | Select-Object -First 10
    foreach ($cg in $concurrencyGroups) {
        $groupOverlaps = @($Overlaps | Where-Object { $_.ConcurrencyGroup -eq $cg.Name }).Count
        $report += "`n| $($cg.Name) | $($cg.Count) | $groupOverlaps |"
    }

    if ($Metrics.RaceConditions -gt 0) {
        $report += @"


## Race Condition Details

### Detected Race Conditions

| Concurrency Group | Run 1 ID | Run 2 ID | Both Completed |
|-------------------|----------|----------|----------------|
"@

        $raceConditions = $Overlaps | Where-Object { $_.IsRaceCondition } | Select-Object -First 10
        foreach ($rc in $raceConditions) {
            $report += "`n| $($rc.ConcurrencyGroup) | $($rc.Run1.id) | $($rc.Run2.id) | Yes |"
        }
    }

    $report += @"


## Recommendations

"@

    if ($Metrics.RaceConditionRate -gt 10) {
        $report += "- **HIGH PRIORITY**: Race condition rate ($($Metrics.RaceConditionRate)%) exceeds 10% threshold. Investigate trigger patterns and consider implementing debouncing.`n"
        $report += "- **MITIGATION**: Consider enabling debouncing for affected workflows using enable_debouncing=true in workflow_dispatch. This adds 10s latency but reduces race condition probability.`n"
    }
    
    if ($Metrics.AvgCancellationTime -gt 5) {
        $report += "- **MEDIUM PRIORITY**: Average cancellation time ($($Metrics.AvgCancellationTime)s) exceeds 5s target. Review workflow startup time and GitHub Actions infrastructure.`n"
    }
    
    if ($Metrics.CoalescingEffectiveness -lt 90 -and $Metrics.CoalescingEffectiveness -gt 0) {
        $report += "- **MEDIUM PRIORITY**: Coalescing effectiveness ($($Metrics.CoalescingEffectiveness)%) is below 90% target. Review concurrency group configurations.`n"
    }
    
    if ($Metrics.CoalescingEffectiveness -ge 90 -and $Metrics.RaceConditionRate -le 10) {
        $report += "- **STATUS**: All metrics are within target thresholds. Continue monitoring.`n"
    }

    $report += @"

## Data Sources

- **GitHub Actions API**: `/repos/{owner}/{repo}/actions/runs`
- **Collection Period**: $($StartDate.ToString('yyyy-MM-dd')) to $($EndDate.ToString('yyyy-MM-dd'))
- **Workflows Analyzed**: $($Workflows -join ', ')

---

*Generated by Measure-WorkflowCoalescing.ps1*
"@

    return $report
}

# Main execution
try {
    Test-Prerequisites
    
    $repoContext = Get-RepositoryContext -Repository $Repository
    Write-Host "Analyzing repository: $($repoContext.Owner)/$($repoContext.Repo)"
    
    $endDate = [DateTime]::UtcNow
    $startDate = $endDate.AddDays(-$Since)
    
    Write-Host "Querying workflow runs from $($startDate.ToString('yyyy-MM-dd')) to $($endDate.ToString('yyyy-MM-dd'))"
    $runs = Get-WorkflowRuns -Owner $repoContext.Owner -Repo $repoContext.Repo -StartDate $startDate -WorkflowNames $Workflows
    
    if ($runs.Count -eq 0) {
        Write-Warning "No workflow runs found in the specified period"
        return
    }
    
    Write-Host "Analyzing $($runs.Count) workflow runs for overlaps"
    $overlaps = Get-OverlappingRuns -Runs $runs
    
    Write-Host "Calculating metrics"
    $metrics = Get-CoalescingMetrics -Runs $runs -Overlaps $overlaps
    
    switch ($Output) {
        'Json' {
            $result = @{
                Metrics = $metrics
                Period = @{
                    StartDate = $startDate.ToString('yyyy-MM-dd')
                    EndDate = $endDate.ToString('yyyy-MM-dd')
                }
                Runs = $runs.Count
                Overlaps = $overlaps.Count
            }
            $json = $result | ConvertTo-Json -Depth 5
            if ($OutputPath) {
                $json | Out-File -FilePath $OutputPath -Encoding utf8
                Write-Host "JSON report saved to: $OutputPath"
            }
            else {
                Write-Output $json
            }
        }
        'Summary' {
            Write-Host "`n=== Coalescing Metrics Summary ===" -ForegroundColor Cyan
            Write-Host "Total Runs: $($metrics.TotalRuns)"
            Write-Host "Cancelled Runs: $($metrics.CancelledRuns)"
            Write-Host "Race Conditions: $($metrics.RaceConditions)"
            Write-Host "Coalescing Effectiveness: $($metrics.CoalescingEffectiveness)% $(if ($metrics.CoalescingEffectiveness -ge 90) { '✓' } else { '✗' })"
            Write-Host "Race Condition Rate: $($metrics.RaceConditionRate)% $(if ($metrics.RaceConditionRate -le 10) { '✓' } else { '✗' })"
            Write-Host "Avg Cancellation Time: $($metrics.AvgCancellationTime)s $(if ($metrics.AvgCancellationTime -le 5) { '✓' } else { '✗' })"
        }
        'Markdown' {
            $report = Format-MarkdownReport -Metrics $metrics -Runs $runs -Overlaps $overlaps -StartDate $startDate -EndDate $endDate -Workflows $Workflows
            if ($OutputPath) {
                $outputDir = Split-Path -Parent $OutputPath
                if ($outputDir -and -not (Test-Path $outputDir)) {
                    New-Item -ItemType Directory -Path $outputDir -Force | Out-Null
                }
                $report | Out-File -FilePath $OutputPath -Encoding utf8
                Write-Host "Markdown report saved to: $OutputPath" -ForegroundColor Green
            }
            else {
                Write-Output $report
            }
        }
    }
}
catch {
    Write-Error "Failed to measure workflow coalescing: $_"
    exit 1
}
