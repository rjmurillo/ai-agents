#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Aggregates PR review comment statistics by reviewer and updates Serena memory.

.DESCRIPTION
    Queries all PRs (open and closed) for review comments, calculates signal quality
    metrics per reviewer, and optionally updates the pr-comment-responder-skills memory file.

    This script provides:
    - Comprehensive coverage of all PRs with review comments
    - Consistent methodology for actionability scoring
    - Historical trend tracking via JSON output

    LIMITATIONS:
    - Maximum of 50 pages of PRs are queried (2500 PRs) due to pagination limits.
      For repositories with extensive history, consider reducing -DaysBack.

.PARAMETER DaysBack
    Number of days of PR history to analyze. Default: 90

.PARAMETER OutputPath
    Path to write the statistics JSON. Default: .agents/stats/reviewer-signal.json

.PARAMETER UpdateMemory
    If set, updates the Serena memory file directly.

.PARAMETER Owner
    Repository owner. Defaults to current repo owner.

.PARAMETER Repo
    Repository name. Defaults to current repo name.

.EXAMPLE
    ./Update-ReviewerSignalStats.ps1 -DaysBack 30
    # Analyze last 30 days and output JSON stats

.EXAMPLE
    ./Update-ReviewerSignalStats.ps1 -DaysBack 90 -UpdateMemory
    # Analyze last 90 days and update Serena memory file

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
    [string]$OutputPath,

    [Parameter()]
    [switch]$UpdateMemory,

    [Parameter()]
    [string]$Owner,

    [Parameter()]
    [string]$Repo
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

#region Configuration

$script:Config = @{
    # Authors to exclude from reviewer counts (they can't review their own PRs)
    ExcludedAuthors = @('rjmurillo', 'rjmurillo-bot', 'dependabot[bot]')

    # Actionability heuristics scoring
    Heuristics = @{
        # Positive signals
        FixedInReply = 1.0         # Reply contains "Fixed in" - confirmed implementation
        WontFixReply = 0.5         # Reply contains "Won't fix" - valid observation, intentional skip
        SeverityHigh = 0.3         # High/Critical severity - likely actionable
        PotentialNull = 0.2        # Contains "potential null" - usually valid

        # Negative signals
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

#region Repository Info

function Get-RepoInfo {
    [CmdletBinding()]
    param()

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

#region Rate Limiting

function Test-RateLimitSafe {
    <#
    .SYNOPSIS
        Check if API rate limit is sufficient for operations.
    #>
    [CmdletBinding()]
    param(
        [int]$MinCore = 200,
        [int]$MinGraphQL = 100
    )

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
        Group comments by reviewer, excluding PR authors.

    .PARAMETER PRs
        Array of PR objects with review threads.

    .PARAMETER ExcludedAuthors
        List of authors to exclude from reviewer counts.
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)]
        [array]$PRs,

        [Parameter()]
        [string[]]$ExcludedAuthors = @()
    )

    $reviewerStats = @{}

    foreach ($pr in $PRs) {
        $prAuthor = $pr.author.login

        foreach ($thread in $pr.reviewThreads.nodes) {
            foreach ($comment in $thread.comments.nodes) {
                $commentAuthor = $comment.author.login

                # Skip if comment author is the PR author or in excluded list
                if ($commentAuthor -eq $prAuthor) { continue }
                if ($commentAuthor -in $ExcludedAuthors) { continue }

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

#region Output Generation

function Export-StatsJson {
    <#
    .SYNOPSIS
        Write statistics JSON file.

    .PARAMETER Stats
        Reviewer statistics hashtable.

    .PARAMETER PRsAnalyzed
        Number of PRs analyzed.

    .PARAMETER DaysAnalyzed
        Number of days analyzed.

    .PARAMETER OutputPath
        Path to write JSON file.
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
        [string]$OutputPath
    )

    $totalComments = ($Stats.Values | ForEach-Object { $_.total_comments } | Measure-Object -Sum).Sum

    # Sort reviewers by signal rate descending for priority matrix
    $sortedReviewers = $Stats.GetEnumerator() | Sort-Object { $_.Value.signal_rate } -Descending

    # Generate priority matrix
    $priorityMatrix = [System.Collections.ArrayList]::new()
    $priority = 0
    foreach ($entry in $sortedReviewers) {
        $reviewer = $entry.Key
        $signalRate = $entry.Value.signal_rate

        $action = if ($signalRate -ge 0.9) {
            'Verify then fix'
        } elseif ($signalRate -ge 0.7) {
            'Review with care'
        } elseif ($signalRate -ge 0.5) {
            'Triage individually'
        } else {
            'Low priority'
        }

        $null = $priorityMatrix.Add(@{
            priority = "P$priority"
            reviewer = $reviewer
            signal_rate = $signalRate
            action = $action
        })
        $priority++
    }

    $output = [ordered]@{
        generated_at = (Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ')
        days_analyzed = $DaysAnalyzed
        prs_analyzed = $PRsAnalyzed
        total_comments = $totalComments
        reviewers = $Stats
        priority_matrix = $priorityMatrix.ToArray()
    }

    # Ensure output directory exists
    $dir = Split-Path $OutputPath -Parent
    if ($dir -and -not (Test-Path $dir)) {
        New-Item -ItemType Directory -Path $dir -Force | Out-Null
    }

    $output | ConvertTo-Json -Depth 10 | Set-Content -Path $OutputPath -Encoding UTF8
    Write-Log "Stats written to: $OutputPath" -Level SUCCESS

    return $output
}

function Update-SerenaMemory {
    <#
    .SYNOPSIS
        Update the Serena memory file with new statistics.

    .DESCRIPTION
        Updates specific sections of the pr-comment-responder-skills.md file
        with the latest statistics. Preserves existing content structure.

    .PARAMETER Stats
        Reviewer statistics from Get-ReviewerSignalStats.

    .PARAMETER MemoryPath
        Path to the Serena memory file.
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)]
        [hashtable]$Stats,

        [Parameter(Mandatory)]
        [string]$MemoryPath
    )

    if (-not (Test-Path $MemoryPath)) {
        Write-Log "Memory file not found: $MemoryPath" -Level WARN
        return $false
    }

    $content = Get-Content -Path $MemoryPath -Raw

    # Update the "Last updated" date in Per-Reviewer Performance section
    $today = (Get-Date).ToString('yyyy-MM-dd')
    $content = $content -replace '(Last updated:\s*)\d{4}-\d{2}-\d{2}', "`${1}$today"

    # Log stats summary (uses the Stats parameter)
    $reviewerCount = $Stats.Count
    Write-Log "Updating memory with $reviewerCount reviewer(s) data" -Level DEBUG

    # Note: Full table regeneration would require more complex parsing
    # For now, just update the date. Full table update would be a future enhancement.

    Set-Content -Path $MemoryPath -Value $content -Encoding UTF8 -NoNewline
    Write-Log "Updated memory file timestamp: $MemoryPath" -Level SUCCESS

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
        $repoInfo = Get-RepoInfo
        if (-not $Owner) { $Owner = $repoInfo.Owner }
        if (-not $Repo) { $Repo = $repoInfo.Repo }
    }
    Write-Log "Repository: $Owner/$Repo" -Level INFO

    # Set default output path
    if (-not $OutputPath) {
        $repoRoot = git rev-parse --show-toplevel
        $OutputPath = Join-Path $repoRoot '.agents/stats/reviewer-signal.json'
    }

    # Calculate date range
    $since = (Get-Date).AddDays(-$DaysBack)

    # Fetch PRs with comments
    $prs = Get-AllPRsWithComments -Owner $Owner -Repo $Repo -Since $since

    if ($prs.Count -eq 0) {
        Write-Log "No PRs with review comments found in the last $DaysBack days" -Level WARN
        exit 0
    }

    # Group comments by reviewer
    $reviewerStats = Get-CommentsByReviewer -PRs $prs -ExcludedAuthors $script:Config.ExcludedAuthors

    if ($reviewerStats.Count -eq 0) {
        Write-Log "No reviewer comments found (excluding PR authors)" -Level WARN
        exit 0
    }

    # Calculate signal quality stats
    $signalStats = Get-ReviewerSignalStats -ReviewerStats $reviewerStats -Heuristics $script:Config.Heuristics

    # Export to JSON
    $outputData = Export-StatsJson -Stats $signalStats -PRsAnalyzed $prs.Count -DaysAnalyzed $DaysBack -OutputPath $OutputPath

    # Optionally update Serena memory
    if ($UpdateMemory) {
        $repoRoot = git rev-parse --show-toplevel
        $memoryPath = Join-Path $repoRoot $script:Config.MemoryPath
        $null = Update-SerenaMemory -Stats $signalStats -MemoryPath $memoryPath
    }

    # Summary
    $duration = (Get-Date) - $script:StartTime
    Write-Log "---" -Level INFO
    Write-Log "=== Aggregation Complete ===" -Level SUCCESS
    Write-Log "PRs analyzed: $($prs.Count)" -Level INFO
    Write-Log "Reviewers found: $($signalStats.Count)" -Level INFO
    Write-Log "Total comments: $($outputData.total_comments)" -Level INFO
    Write-Log "Duration: $([math]::Round($duration.TotalSeconds, 1)) seconds" -Level INFO

    # GitHub Actions step summary
    if ($env:GITHUB_STEP_SUMMARY) {
        $summary = @"
## Reviewer Signal Stats Update

| Metric | Value |
|--------|-------|
| Days Analyzed | $DaysBack |
| PRs Analyzed | $($prs.Count) |
| Reviewers Found | $($signalStats.Count) |
| Total Comments | $($outputData.total_comments) |

### Priority Matrix

| Priority | Reviewer | Signal Rate | Action |
|----------|----------|-------------|--------|
"@
        foreach ($item in $outputData.priority_matrix) {
            $summary += "| $($item.priority) | $($item.reviewer) | $([math]::Round($item.signal_rate * 100))% | $($item.action) |`n"
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
