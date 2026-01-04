#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Aggregates PR review comment statistics by reviewer and updates Serena memory.

.DESCRIPTION
    Queries all PRs (open and closed) for review comments, calculates signal quality
    metrics per reviewer, and updates the pr-comment-responder-skills memory file.

    This script provides:
    - Comprehensive coverage of all PRs with review comments
    - Consistent methodology for actionability scoring
    - Direct updates to the Serena memory file (source of truth)

    LIMITATIONS:
    - Maximum of 50 pages of PRs are queried (2500 PRs) due to pagination limits.
      For repositories with extensive history, consider reducing -DaysBack.

.PARAMETER DaysBack
    Number of days of PR history to analyze. Default: 90

.PARAMETER Owner
    Repository owner. Defaults to current repo owner.

.PARAMETER Repo
    Repository name. Defaults to current repo name.

.EXAMPLE
    ./Update-ReviewerSignalStats.ps1 -DaysBack 30
    # Analyze last 30 days and update Serena memory

.EXAMPLE
    ./Update-ReviewerSignalStats.ps1 -DaysBack 90
    # Analyze last 90 days and update Serena memory

.NOTES
    Exit Codes:
    0 = Success
    1 = Invalid parameters
    2 = API error or script failure

    Pagination: Maximum 50 pages (2500 PRs) are queried to avoid API rate limits.
#>

[CmdletBinding()]
param(
    [Parameter()]
    [ValidateRange(1, 365)]
    [int]$DaysBack = 90,

    [Parameter()]
    [string]$Owner,

    [Parameter()]
    [string]$Repo
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

# Import GitHubCore module for shared functions (rate limiting, repo info)
$script:GitHubCorePath = Join-Path $PSScriptRoot ".." ".claude" "skills" "github" "modules" "GitHubCore.psm1"
if (Test-Path $script:GitHubCorePath) {
    Import-Module $script:GitHubCorePath -Force
}

#region Configuration

$script:Config = @{
    # Authors to skip when counting comments ON THEIR OWN PRs
    # Note: These authors CAN and DO review other authors' PRs (e.g., rjmurillo reviews
    # rjmurillo-bot PRs and vice versa). This only excludes self-comments on own PRs.
    SelfCommentExcludedAuthors = @('dependabot[bot]')

    # Actionability heuristics scoring
    # SCORE RANGE: 0.0 to 1.0
    # - 0.5 = neutral starting point
    # - Positive adjustments increase actionability likelihood
    # - Negative adjustments decrease actionability likelihood
    # - Final score clamped to [0, 1] range
    # - IsActionable = true when score >= 0.5
    Heuristics = @{
        # Positive signals (add to score)
        FixedInReply = 1.0         # Reply contains "Fixed in" - confirmed implementation
        WontFixReply = 0.5         # Reply contains "Won't fix" - valid observation, intentional skip
        SeverityHigh = 0.3         # High/Critical severity - likely actionable
        PotentialNull = 0.2        # Contains "potential null" - usually valid

        # Negative signals (subtract from score)
        SeverityLow = -0.1         # Low severity - often style noise
        UnusedRemove = -0.2        # Contains "unused"/"remove" - often false positive
        NoReplyAfterDays = -0.3    # No reply after N days - likely ignored
        NoReplyThreshold = 7       # Days threshold for "no reply" penalty
    }

    # Memory file path
    MemoryPath = '.serena/memories/pr-comment-responder-skills.md'

    # Trend thresholds
    TrendThresholds = @{
        Improving = 0.05   # Signal rate increased by 5%+
        Declining = -0.05  # Signal rate decreased by 5%+
    }
}

$script:StartTime = Get-Date

#endregion

#region Logging

function Write-Log {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)]
        [string]$Message,

        [ValidateSet('INFO', 'WARN', 'ERROR', 'SUCCESS', 'DEBUG')]
        [string]$Level = 'INFO'
    )

    $timestamp = Get-Date -Format 'yyyy-MM-dd HH:mm:ss'
    $color = switch ($Level) {
        'INFO' { 'Gray' }
        'WARN' { 'Yellow' }
        'ERROR' { 'Red' }
        'SUCCESS' { 'Green' }
        'DEBUG' { 'DarkGray' }
    }
    Write-Host "[$timestamp] [$Level] $Message" -ForegroundColor $color
}

#endregion

#region Rate Limiting

function Test-RateLimitSafe {
    <#
    .SYNOPSIS
        Check if API rate limit is sufficient for operations.
    .NOTES
        If GitHubCore module is loaded, uses Test-WorkflowRateLimit from there.
        Otherwise falls back to local implementation.
    #>
    [CmdletBinding()]
    param(
        [int]$MinCore = 200,
        [int]$MinGraphQL = 100
    )

    # Use shared function if GitHubCore module is loaded
    if (Get-Command -Name Test-WorkflowRateLimit -ErrorAction SilentlyContinue) {
        try {
            $result = Test-WorkflowRateLimit -ResourceThresholds @{
                'core'    = $MinCore
                'graphql' = $MinGraphQL
            }
            if (-not $result.Success) {
                Write-Log "Rate limit too low: core=$($result.CoreRemaining)" -Level WARN
            }
            return $result.Success
        }
        catch {
            Write-Log "Failed to check rate limit via GitHubCore: $_" -Level WARN
            # Fall through to local implementation
        }
    }

    # Local fallback
    $limits = gh api rate_limit 2>&1
    if ($LASTEXITCODE -ne 0) {
        Write-Log "Failed to check rate limit: $limits" -Level WARN
        return $true  # Assume safe if can't check
    }

    try {
        $parsed = $limits | ConvertFrom-Json
        $core = $parsed.resources.core
        $graphql = $parsed.resources.graphql

        if ($core.remaining -lt $MinCore -or $graphql.remaining -lt $MinGraphQL) {
            Write-Log "Rate limit too low: core=$($core.remaining), graphql=$($graphql.remaining)" -Level WARN
            return $false
        }
        Write-Log "Rate limit OK: core=$($core.remaining), graphql=$($graphql.remaining)" -Level DEBUG
        return $true
    }
    catch {
        Write-Log "Failed to parse rate limit response: $_" -Level WARN
        return $true
    }
}

#endregion

#region Repository Info

function Get-RepoInfoLocal {
    <#
    .SYNOPSIS
        Get repository owner and repo from git remote.
    .NOTES
        If GitHubCore module is loaded, uses Get-RepoInfo from there.
        Otherwise uses local implementation.
    #>
    [CmdletBinding()]
    param()

    # Use shared function if GitHubCore module is loaded
    if (Get-Command -Name Get-RepoInfo -ErrorAction SilentlyContinue) {
        try {
            $result = Get-RepoInfo
            if ($result) {
                return $result
            }
        }
        catch {
            Write-Log "Failed to get repo info via GitHubCore: $_" -Level WARN
            # Fall through to local implementation
        }
    }

    # Local fallback
    $remote = git remote get-url origin 2>$null
    if (-not $remote) {
        throw "Not in a git repository or no origin remote"
    }

    if ($remote -match 'github\.com[:/]([^/]+)/([^/.]+)') {
        return @{
            Owner = $Matches[1]
            Repo = $Matches[2] -replace '\.git$', ''
        }
    }

    throw "Could not parse GitHub repository from remote: $remote"
}

#endregion

#region GitHub API Helpers

function Get-AllPRsWithComments {
    <#
    .SYNOPSIS
        Query PRs with review comments using gh api with pagination.

    .DESCRIPTION
        Fetches all PRs (open and closed) from the specified time range that have
        review comments. Uses GraphQL for efficient querying.

    .PARAMETER Owner
        Repository owner.

    .PARAMETER Repo
        Repository name.

    .PARAMETER Since
        Only include PRs updated since this date.
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)]
        [string]$Owner,

        [Parameter(Mandatory)]
        [string]$Repo,

        [Parameter(Mandatory)]
        [datetime]$Since
    )

    $allPRs = [System.Collections.ArrayList]::new()
    $cursor = $null
    $hasNextPage = $true
    $pageCount = 0
    $maxPages = 50  # Safety limit

    Write-Log "Fetching PRs updated since $($Since.ToString('yyyy-MM-dd'))..." -Level INFO

    while ($hasNextPage -and $pageCount -lt $maxPages) {
        $pageCount++

        # Build cursor clause for pagination
        $cursorClause = if ($cursor) { ", after: `"$cursor`"" } else { "" }

        $query = @"
query {
  repository(owner: "$Owner", name: "$Repo") {
    pullRequests(first: 50, orderBy: {field: UPDATED_AT, direction: DESC}$cursorClause) {
      pageInfo {
        hasNextPage
        endCursor
      }
      nodes {
        number
        title
        state
        author { login }
        createdAt
        updatedAt
        mergedAt
        closedAt
        reviewThreads(first: 100) {
          nodes {
            isResolved
            isOutdated
            comments(first: 50) {
              nodes {
                id
                body
                author { login }
                createdAt
                path
              }
            }
          }
        }
      }
    }
  }
}
"@

        $result = gh api graphql -f query=$query 2>&1
        if ($LASTEXITCODE -ne 0) {
            Write-Log "GraphQL query failed: $result" -Level ERROR
            throw "Failed to query PRs: $result"
        }

        try {
            $parsed = $result | ConvertFrom-Json
            $prData = $parsed.data.repository.pullRequests

            foreach ($pr in $prData.nodes) {
                # Check if PR was updated within our time range
                $updatedAt = [datetime]::Parse($pr.updatedAt)
                if ($updatedAt -lt $Since) {
                    # PRs are ordered by updatedAt DESC, so we can stop here
                    $hasNextPage = $false
                    break
                }

                # Only include PRs that have review comments
                $hasComments = $pr.reviewThreads.nodes | Where-Object { $_.comments.nodes.Count -gt 0 }
                if ($hasComments) {
                    $null = $allPRs.Add($pr)
                }
            }

            # Check pagination
            if ($hasNextPage) {
                $hasNextPage = $prData.pageInfo.hasNextPage
                $cursor = $prData.pageInfo.endCursor
            }

            Write-Log "Page $pageCount processed, total PRs with comments: $($allPRs.Count)" -Level DEBUG
        }
        catch {
            Write-Log "Failed to parse GraphQL response: $_" -Level ERROR
            throw
        }
    }

    if ($pageCount -ge $maxPages) {
        Write-Log "Reached maximum page limit ($maxPages)" -Level WARN
    }

    Write-Log "Found $($allPRs.Count) PRs with review comments" -Level INFO
    return $allPRs.ToArray()
}

function Get-CommentsByReviewer {
    <#
    .SYNOPSIS
        Group comments by reviewer.

    .DESCRIPTION
        Aggregates review comments by reviewer login. Excludes comments where
        the reviewer is commenting on their own PR (self-comments).
        
        Note: Authors CAN review other authors' PRs. For example, rjmurillo
        reviews rjmurillo-bot PRs and vice versa. Only self-comments are excluded.

    .PARAMETER PRs
        Array of PR objects with review threads.

    .PARAMETER SelfCommentExcludedAuthors
        List of bot authors whose self-comments should be excluded.
        Human authors can still be counted when reviewing other PRs.
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)]
        [array]$PRs,

        [Parameter()]
        [string[]]$SelfCommentExcludedAuthors = @()
    )

    $reviewerStats = @{}

    foreach ($pr in $PRs) {
        $prAuthor = $pr.author.login

        foreach ($thread in $pr.reviewThreads.nodes) {
            foreach ($comment in $thread.comments.nodes) {
                $commentAuthor = $comment.author.login

                # Skip self-comments (reviewer commenting on their own PR)
                if ($commentAuthor -eq $prAuthor) { continue }

                # Initialize reviewer stats if needed
                if (-not $reviewerStats.ContainsKey($commentAuthor)) {
                    $reviewerStats[$commentAuthor] = @{
                        TotalComments = 0
                        PRsWithComments = [System.Collections.Generic.HashSet[int]]::new()
                        Comments = [System.Collections.ArrayList]::new()
                        VerifiedActionable = 0
                        Last30Days = @{
                            Comments = 0
                            Actionable = 0
                        }
                    }
                }

                # Add comment to stats
                $reviewerStats[$commentAuthor].TotalComments++
                $null = $reviewerStats[$commentAuthor].PRsWithComments.Add($pr.number)
                $null = $reviewerStats[$commentAuthor].Comments.Add(@{
                    PRNumber = $pr.number
                    Body = $comment.body
                    CreatedAt = $comment.createdAt
                    Path = $comment.path
                    IsResolved = $thread.isResolved
                    IsOutdated = $thread.isOutdated
                    ThreadComments = $thread.comments.nodes
                })
            }
        }
    }

    return $reviewerStats
}

#endregion

#region Actionability Scoring

function Get-ActionabilityScore {
    <#
    .SYNOPSIS
        Calculate actionability score for a comment based on heuristics.

    .PARAMETER CommentData
        Comment data including body, thread replies, and metadata.

    .PARAMETER Heuristics
        Scoring heuristics configuration.
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)]
        [hashtable]$CommentData,

        [Parameter(Mandatory)]
        [hashtable]$Heuristics
    )

    $score = 0.5  # Start at neutral
    $reasons = [System.Collections.ArrayList]::new()

    $body = $CommentData.Body.ToLower()
    $threadComments = $CommentData.ThreadComments

    # Check for "Fixed in" reply
    $hasFixedReply = $threadComments | Where-Object {
        $_.body -match 'fixed\s+in|implemented|addressed|resolved'
    }
    if ($hasFixedReply) {
        $score += $Heuristics.FixedInReply
        $null = $reasons.Add('FixedInReply')
    }

    # Check for "Won't fix" reply
    $hasWontFixReply = $threadComments | Where-Object {
        $_.body -match "won't\s*fix|wontfix|intentional|by\s*design|not\s*a\s*bug"
    }
    if ($hasWontFixReply) {
        $score += $Heuristics.WontFixReply
        $null = $reasons.Add('WontFixReply')
    }

    # Check for severity indicators in comment body
    if ($body -match 'critical|high\s*severity|security|vulnerability|cwe-|injection') {
        $score += $Heuristics.SeverityHigh
        $null = $reasons.Add('SeverityHigh')
    }

    if ($body -match 'low\s*severity|style|nit:|minor|cosmetic') {
        $score += $Heuristics.SeverityLow
        $null = $reasons.Add('SeverityLow')
    }

    # Check for common patterns
    if ($body -match 'potential\s*null|null\s*reference|null\s*check') {
        $score += $Heuristics.PotentialNull
        $null = $reasons.Add('PotentialNull')
    }

    if ($body -match 'unused|remove\s*(this|it|the)|dead\s*code') {
        $score += $Heuristics.UnusedRemove
        $null = $reasons.Add('UnusedRemove')
    }

    # Check for no reply after threshold days (only if not resolved)
    if (-not $CommentData.IsResolved -and -not $hasFixedReply -and -not $hasWontFixReply) {
        $createdAt = [datetime]::Parse($CommentData.CreatedAt)
        $daysSinceCreated = ((Get-Date) - $createdAt).Days
        if ($daysSinceCreated -ge $Heuristics.NoReplyThreshold) {
            $score += $Heuristics.NoReplyAfterDays
            $null = $reasons.Add('NoReplyAfterDays')
        }
    }

    # Clamp score between 0 and 1
    # NOTE: [double] cast is required - PowerShell uses integer arithmetic with literal 0/1,
    # which truncates decimals (e.g., 0.5 becomes 0). See tests for verification.
    $score = [Math]::Max([double]0, [Math]::Min([double]1, $score))

    return @{
        Score = $score
        Reasons = $reasons.ToArray()
        IsActionable = $score -ge 0.5
    }
}

function Get-ReviewerSignalStats {
    <#
    .SYNOPSIS
        Calculate signal quality statistics for each reviewer.

    .PARAMETER ReviewerStats
        Hashtable of reviewer stats from Get-CommentsByReviewer.

    .PARAMETER Heuristics
        Scoring heuristics configuration.
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)]
        [hashtable]$ReviewerStats,

        [Parameter(Mandatory)]
        [hashtable]$Heuristics
    )

    $results = @{}
    $thirtyDaysAgo = (Get-Date).AddDays(-30)

    foreach ($reviewer in $ReviewerStats.Keys) {
        $stats = $ReviewerStats[$reviewer]
        $actionableCount = 0
        $last30DaysActionable = 0
        $last30DaysCount = 0

        foreach ($comment in $stats.Comments) {
            $scoreResult = Get-ActionabilityScore -CommentData $comment -Heuristics $Heuristics

            if ($scoreResult.IsActionable) {
                $actionableCount++
            }

            # Track last 30 days
            $commentDate = [datetime]::Parse($comment.CreatedAt)
            if ($commentDate -ge $thirtyDaysAgo) {
                $last30DaysCount++
                if ($scoreResult.IsActionable) {
                    $last30DaysActionable++
                }
            }
        }

        $signalRate = if ($stats.TotalComments -gt 0) {
            [Math]::Round($actionableCount / $stats.TotalComments, 2)
        } else { 0 }

        $last30SignalRate = if ($last30DaysCount -gt 0) {
            [Math]::Round($last30DaysActionable / $last30DaysCount, 2)
        } else { 0 }

        # Determine trend
        $trend = 'stable'
        if ($last30DaysCount -ge 5 -and $stats.TotalComments -ge 10) {
            $rateDiff = $last30SignalRate - $signalRate
            if ($rateDiff -ge $script:Config.TrendThresholds.Improving) {
                $trend = 'improving'
            } elseif ($rateDiff -le $script:Config.TrendThresholds.Declining) {
                $trend = 'declining'
            }
        }

        $results[$reviewer] = @{
            total_comments = $stats.TotalComments
            prs_with_comments = $stats.PRsWithComments.Count
            verified_actionable = $stats.VerifiedActionable
            estimated_actionable = $actionableCount
            signal_rate = $signalRate
            trend = $trend
            last_30_days = @{
                comments = $last30DaysCount
                signal_rate = $last30SignalRate
            }
        }
    }

    return $results
}

#endregion

#region Serena Memory Update

function Update-SerenaMemory {
    <#
    .SYNOPSIS
        Update the Serena memory file with computed statistics.

    .DESCRIPTION
        Updates the Per-Reviewer Performance table in the pr-comment-responder-skills.md
        memory file with the latest computed statistics. This is the source of truth
        for reviewer signal quality data used by LLM agents.

    .PARAMETER Stats
        Reviewer statistics from Get-ReviewerSignalStats.

    .PARAMETER PRsAnalyzed
        Number of PRs analyzed.

    .PARAMETER DaysAnalyzed
        Number of days analyzed.

    .PARAMETER MemoryPath
        Path to the Serena memory file.
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)]
        [hashtable]$Stats,

        [Parameter(Mandatory)]
        [int]$PRsAnalyzed,

        [Parameter(Mandatory)]
        [int]$DaysAnalyzed,

        [Parameter(Mandatory)]
        [string]$MemoryPath
    )

    if (-not (Test-Path $MemoryPath)) {
        Write-Log "Memory file not found: $MemoryPath" -Level WARN
        return $false
    }

    $content = Get-Content -Path $MemoryPath -Raw

    # Build the new Per-Reviewer Performance table
    $tableHeader = @"
## Per-Reviewer Performance (Cumulative)

Aggregated from $PRsAnalyzed PRs over last $DaysAnalyzed days.

| Reviewer | PRs | Comments | Actionable | Signal | Trend |
|----------|-----|----------|------------|--------|-------|
"@

    $tableRows = [System.Collections.ArrayList]::new()
    
    # Sort by signal rate descending
    $sortedReviewers = $Stats.GetEnumerator() | Sort-Object { $_.Value.signal_rate } -Descending

    foreach ($entry in $sortedReviewers) {
        $reviewer = $entry.Key
        $data = $entry.Value
        $signalPercent = [math]::Round($data.signal_rate * 100)
        $signalDisplay = if ($signalPercent -ge 90) { "**$signalPercent%**" } else { "$signalPercent%" }
        $trend = switch ($data.trend) {
            'improving' { '↑' }
            'declining' { '↓' }
            default { '→' }
        }
        
        $row = "| $reviewer | $($data.prs_with_comments) | $($data.total_comments) | $($data.estimated_actionable) | $signalDisplay | $trend |"
        $null = $tableRows.Add($row)
    }

    $newTable = $tableHeader + "`n" + ($tableRows -join "`n")

    # Replace the existing Per-Reviewer Performance section
    # Match from "## Per-Reviewer Performance" until the next level-2 heading or end of file
    $pattern = '(?s)## Per-Reviewer Performance.*?(?=\n## |\z)'
    
    if ($content -match $pattern) {
        $content = $content -replace $pattern, ($newTable + "`n")
    } else {
        # If section doesn't exist, insert after Overview
        $content = $content -replace '(## Overview.*?)(\n## )', "`$1`n`n$newTable`n`$2"
    }

    Set-Content -Path $MemoryPath -Value $content -Encoding UTF8 -NoNewline
    Write-Log "Updated Serena memory: $MemoryPath" -Level SUCCESS
    Write-Log "  Reviewers: $($Stats.Count)" -Level INFO

    return $true
}

#endregion

#region Main

# Guard: Only execute main logic when run directly, not when dot-sourced for testing
if ($MyInvocation.InvocationName -eq '.') {
    return
}

try {
    Write-Log "Starting reviewer signal stats aggregation" -Level INFO
    Write-Log "DaysBack: $DaysBack" -Level INFO

    # Check rate limit
    if (-not (Test-RateLimitSafe)) {
        Write-Log "Insufficient API rate limit. Exiting." -Level ERROR
        exit 2
    }

    # Resolve repo info
    if (-not $Owner -or -not $Repo) {
        $repoInfo = Get-RepoInfoLocal
        if (-not $Owner) { $Owner = $repoInfo.Owner }
        if (-not $Repo) { $Repo = $repoInfo.Repo }
    }
    Write-Log "Repository: $Owner/$Repo" -Level INFO

    # Calculate date range
    $since = (Get-Date).AddDays(-$DaysBack)

    # Fetch PRs with comments
    $prs = Get-AllPRsWithComments -Owner $Owner -Repo $Repo -Since $since

    if ($prs.Count -eq 0) {
        Write-Log "No PRs with review comments found in the last $DaysBack days" -Level WARN
        exit 0
    }

    # Group comments by reviewer
    $reviewerStats = Get-CommentsByReviewer -PRs $prs -SelfCommentExcludedAuthors $script:Config.SelfCommentExcludedAuthors

    if ($reviewerStats.Count -eq 0) {
        Write-Log "No reviewer comments found (excluding self-comments)" -Level WARN
        exit 0
    }

    # Calculate signal quality stats
    $signalStats = Get-ReviewerSignalStats -ReviewerStats $reviewerStats -Heuristics $script:Config.Heuristics

    # Calculate total comments for summary
    $totalComments = ($signalStats.Values | ForEach-Object { $_.total_comments } | Measure-Object -Sum).Sum

    # Update Serena memory (source of truth)
    $repoRoot = git rev-parse --show-toplevel
    $memoryPath = Join-Path $repoRoot $script:Config.MemoryPath
    $null = Update-SerenaMemory -Stats $signalStats -PRsAnalyzed $prs.Count -DaysAnalyzed $DaysBack -MemoryPath $memoryPath

    # Summary
    $duration = (Get-Date) - $script:StartTime
    Write-Log "---" -Level INFO
    Write-Log "=== Aggregation Complete ===" -Level SUCCESS
    Write-Log "PRs analyzed: $($prs.Count)" -Level INFO
    Write-Log "Reviewers found: $($signalStats.Count)" -Level INFO
    Write-Log "Total comments: $totalComments" -Level INFO
    Write-Log "Duration: $([math]::Round($duration.TotalSeconds, 1)) seconds" -Level INFO

    # GitHub Actions step summary
    if ($env:GITHUB_STEP_SUMMARY) {
        # Sort by signal rate descending
        $sortedReviewers = $signalStats.GetEnumerator() | Sort-Object { $_.Value.signal_rate } -Descending

        $summary = @"
## Reviewer Signal Stats Update

| Metric | Value |
|--------|-------|
| Days Analyzed | $DaysBack |
| PRs Analyzed | $($prs.Count) |
| Reviewers Found | $($signalStats.Count) |
| Total Comments | $totalComments |

### Reviewer Rankings

| Reviewer | Signal Rate | Trend | Comments |
|----------|-------------|-------|----------|
"@
        foreach ($entry in $sortedReviewers) {
            $reviewer = $entry.Key
            $data = $entry.Value
            $signalPercent = [math]::Round($data.signal_rate * 100)
            $trend = switch ($data.trend) {
                'improving' { '↑' }
                'declining' { '↓' }
                default { '→' }
            }
            $summary += "| $reviewer | $signalPercent% | $trend | $($data.total_comments) |`n"
        }

        $summary | Out-File -FilePath $env:GITHUB_STEP_SUMMARY -Append -Encoding UTF8
    }

    exit 0
}
catch {
    Write-Log "Fatal error: $_" -Level ERROR
    Write-Log $_.ScriptStackTrace -Level ERROR
    exit 2
}

#endregion
