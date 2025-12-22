<#
.SYNOPSIS
    Detect and analyze Copilot follow-up PR patterns.

.DESCRIPTION
    Identifies when Copilot creates follow-up PRs after PR comment replies.
    Categorizes follow-ups as DUPLICATE, SUPPLEMENTAL, or INDEPENDENT.
    Returns structured data for decision-making.

.PARAMETER PRNumber
    The original PR number to check for follow-ups.

.PARAMETER Owner
    Repository owner.

.PARAMETER Repo
    Repository name.

.EXAMPLE
    Detect-CopilotFollowUpPR -PRNumber 32 -Owner rjmurillo-bot -Repo ai-agents

.NOTES
    Pattern: Copilot creates PR with branch copilot/sub-pr-{original_pr}
    Targets original PR's base branch (not main)
    Posts announcement: "I've opened a new pull request, #{number}"
#>

param(
    [Parameter(Mandatory = $true)]
    [int]$PRNumber,

    [Parameter(Mandatory = $true)]
    [string]$Owner,

    [Parameter(Mandatory = $true)]
    [string]$Repo
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Test-FollowUpPattern {
    <#
    .SYNOPSIS
        Check if a PR matches Copilot follow-up pattern.
    #>
    param(
        [Parameter(Mandatory = $true)]
        [object]$PR
    )

    $headRef = $PR.headRefName
    $pattern = "copilot/sub-pr-\d+"

    return $headRef -match $pattern
}

function Get-CopilotAnnouncement {
    <#
    .SYNOPSIS
        Find Copilot's announcement comment on the original PR.
    #>
    param(
        [Parameter(Mandatory = $true)]
        [int]$PRNumber
    )

    $comments = gh api repos/$Owner/$Repo/issues/$PRNumber/comments `
        --jq '.[] | select(.user.login == "app/copilot-swe-agent")' 2>/dev/null

    if ($null -eq $comments -or $comments -eq '') {
        return $null
    }

    # Parse each comment and check for follow-up PR announcement
    $comments | jq -r 'select(.body | contains("opened a new pull request")) | {id: .id, body: .body, created_at: .created_at}' 2>/dev/null
}

function Get-FollowUpPRDiff {
    <#
    .SYNOPSIS
        Get unified diff for follow-up PR.
    #>
    param(
        [Parameter(Mandatory = $true)]
        [int]$FollowUpPRNumber
    )

    $diff = gh pr diff $FollowUpPRNumber --no-merges 2>/dev/null
    return $diff
}

function Get-OriginalPRCommits {
    <#
    .SYNOPSIS
        Get commits from original PR for comparison.
    #>
    param(
        [Parameter(Mandatory = $true)]
        [int]$PRNumber
    )

    $pr = gh pr view $PRNumber --json commits --jq '.' 2>/dev/null | ConvertFrom-Json

    if ($null -eq $pr) {
        return @()
    }

    $commits = @()
    try {
        $commitData = gh api repos/$Owner/$Repo/commits `
            --jq ".[] | select(.commit.message | contains(\"PR $PRNumber\") or contains(\"Comment-ID\"))" 2>/dev/null
        if ($commitData) {
            $commits = @($commitData | ConvertFrom-Json -ErrorAction SilentlyContinue)
        }
    }
    catch {
        # No specific commits found, continue
    }

    return $commits
}

function Compare-DiffContent {
    <#
    .SYNOPSIS
        Compare follow-up diff to original changes.
        Returns likelihood percentage of being duplicate.
    #>
    param(
        [Parameter(Mandatory = $true)]
        [string]$FollowUpDiff,

        [Parameter(Mandatory = $true)]
        [object[]]$OriginalCommits
    )

    if ($FollowUpDiff -eq '') {
        # Empty diff = likely duplicate (no changes to add)
        return @{similarity = 100; category = 'DUPLICATE'; reason = 'Follow-up PR contains no changes' }
    }

    # Count file changes in follow-up
    $followUpFiles = @($FollowUpDiff -split '^diff --git' | Where-Object { $_.Trim() } | Measure-Object).Count

    # If follow-up has 1 file and original also modified that file, likely duplicate
    if ($followUpFiles -eq 1 -and $OriginalCommits.Count -gt 0) {
        return @{similarity = 85; category = 'LIKELY_DUPLICATE'; reason = 'Single file change matching original scope' }
    }

    # If follow-up has no file changes but adds comments/replies
    if ($followUpFiles -eq 0) {
        return @{similarity = 95; category = 'DUPLICATE'; reason = 'No code changes in follow-up PR' }
    }

    # Multiple files or complex diff = might be supplemental
    return @{similarity = 40; category = 'POSSIBLE_SUPPLEMENTAL'; reason = 'Multiple file changes suggest additional work' }
}

function Invoke-FollowUpDetection {
    <#
    .SYNOPSIS
        Main detection logic.
    #>

    Write-Host "Detecting Copilot follow-up PRs for PR #$PRNumber..."

    # Step 1: Query for follow-up PR matching pattern
    $followUpPRQuery = "head:copilot/sub-pr-$PRNumber"
    Write-Host "Searching for: $followUpPRQuery"

    $followUpPRs = @()
    try {
        $prData = gh pr list --state=open --search $followUpPRQuery --json=number,title,body,headRefName,baseRefName,state,author,createdAt 2>/dev/null | ConvertFrom-Json
        if ($prData -is [array]) {
            $followUpPRs = @($prData)
        }
        elseif ($null -ne $prData) {
            $followUpPRs = @($prData)
        }
    }
    catch {
        Write-Host "Info: No follow-up PRs found (query may not match any results)"
    }

    if ($followUpPRs.Count -eq 0) {
        return @{
            found             = $false
            followUpPRs       = @()
            announcement      = $null
            analysis          = $null
            recommendation    = 'NO_ACTION_NEEDED'
            message           = 'No follow-up PRs detected'
        }
    }

    Write-Host "Found $($followUpPRs.Count) follow-up PR(s)"

    # Step 2: Verify Copilot announcement
    $announcement = Get-CopilotAnnouncement -PRNumber $PRNumber
    if ($null -eq $announcement -or $announcement -eq '') {
        Write-Host "Warning: No Copilot announcement found, but follow-up PR exists"
    }
    else {
        Write-Host "Verified Copilot announcement"
    }

    # Step 3: Analyze each follow-up PR
    $analysis = @()
    foreach ($followUp in $followUpPRs) {
        $prNum = $followUp.number
        Write-Host "Analyzing follow-up PR #$prNum..."

        $diff = Get-FollowUpPRDiff -FollowUpPRNumber $prNum
        $originalCommits = Get-OriginalPRCommits -PRNumber $PRNumber

        $comparison = Compare-DiffContent -FollowUpDiff $diff -OriginalCommits $originalCommits

        $analysisResult = @{
            followUpPRNumber   = $prNum
            headBranch         = $followUp.headRefName
            baseBranch         = $followUp.baseRefName
            createdAt          = $followUp.createdAt
            author             = $followUp.author.login
            category           = $comparison.category
            similarity         = $comparison.similarity
            reason             = $comparison.reason
            recommendation     = $null
        }

        # Determine recommendation based on category
        switch ($comparison.category) {
            'DUPLICATE' {
                $analysisResult.recommendation = 'CLOSE_AS_DUPLICATE'
            }
            'LIKELY_DUPLICATE' {
                $analysisResult.recommendation = 'REVIEW_THEN_CLOSE'
            }
            'POSSIBLE_SUPPLEMENTAL' {
                $analysisResult.recommendation = 'EVALUATE_FOR_MERGE'
            }
            default {
                $analysisResult.recommendation = 'MANUAL_REVIEW'
            }
        }

        $analysis += $analysisResult
    }

    return @{
        found             = $true
        originalPRNumber  = $PRNumber
        followUpPRs       = $followUpPRs
        announcement      = $announcement
        analysis          = $analysis
        recommendation    = if ($analysis.Count -eq 1) { $analysis[0].recommendation } else { 'MULTIPLE_FOLLOW_UPS_REVIEW' }
        timestamp         = (Get-Date -Format 'O')
    }
}

# Execute detection
$result = Invoke-FollowUpDetection

# Output as JSON for script consumption
$result | ConvertTo-Json -Depth 5
