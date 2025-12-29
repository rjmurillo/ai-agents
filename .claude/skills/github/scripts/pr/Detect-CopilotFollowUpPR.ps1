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
    Repository owner. Inferred from git remote if not provided.

.PARAMETER Repo
    Repository name. Inferred from git remote if not provided.

.EXAMPLE
    ./Detect-CopilotFollowUpPR.ps1 -PRNumber 32
    ./Detect-CopilotFollowUpPR.ps1 -PRNumber 32 -Owner rjmurillo -Repo ai-agents

.NOTES
    Pattern: Copilot creates PR with branch copilot/sub-pr-{original_pr}
    Targets original PR's base branch (not main)
    Posts announcement: "I've opened a new pull request, #{number}"

    Exit Codes: 0=Success, 1=Invalid params, 3=API error, 4=Not authenticated
#>

[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [int]$PRNumber,

    [string]$Owner,

    [string]$Repo
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

Import-Module (Join-Path $PSScriptRoot ".." ".." "modules" "GitHubHelpers.psm1") -Force

Assert-GhAuthenticated
$resolved = Resolve-RepoParams -Owner $Owner -Repo $Repo
$script:Owner = $resolved.Owner
$script:Repo = $resolved.Repo

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

    # Single jq filter for efficiency (addresses issue #238)
    $announcement = gh api "repos/$script:Owner/$script:Repo/issues/$PRNumber/comments" `
        --jq '.[] | select(.user.login == "copilot-swe-agent[bot]" and (.body | contains("opened a new pull request"))) | {id: .id, body: .body, created_at: .created_at}' 2>$null

    if ($LASTEXITCODE -ne 0 -or $null -eq $announcement -or $announcement -eq '') {
        return $null
    }

    return $announcement
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

    $diff = gh pr diff $FollowUpPRNumber --repo "$script:Owner/$script:Repo" 2>$null
    if ($LASTEXITCODE -ne 0) {
        return ''
    }
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

    $prJson = gh pr view $PRNumber --repo "$script:Owner/$script:Repo" --json commits,baseRefName,headRefName 2>$null
    if ($LASTEXITCODE -ne 0 -or $null -eq $prJson) {
        return @()
    }

    $pr = $prJson | ConvertFrom-Json
    if ($null -eq $pr) {
        return @()
    }

    $commits = @()
    try {
        $commitData = gh api "repos/$script:Owner/$script:Repo/commits" `
            --jq ".[] | select(.commit.message | contains(\"PR $PRNumber\") or contains(\"Comment-ID\"))" 2>$null
        if ($LASTEXITCODE -eq 0 -and $commitData) {
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
    .PARAMETER FollowUpDiff
        The unified diff content of the follow-up PR.
    .PARAMETER OriginalCommits
        Commits from the original PR for comparison.
    .PARAMETER OriginalPRNumber
        The original PR number to check merge status (Issue #293).
    #>
    param(
        [Parameter(Mandatory = $true)]
        [AllowEmptyString()]
        [string]$FollowUpDiff,

        [Parameter(Mandatory = $true)]
        [AllowEmptyCollection()]
        [object[]]$OriginalCommits,

        [Parameter(Mandatory = $false)]
        [int]$OriginalPRNumber = 0
    )

    if ([string]::IsNullOrWhiteSpace($FollowUpDiff)) {
        # Empty or whitespace-only diff - check if original PR was merged (Issue #293)
        $reason = 'Follow-up PR contains no changes'

        if ($OriginalPRNumber -gt 0) {
            $mergedJson = gh pr view $OriginalPRNumber --repo "$script:Owner/$script:Repo" --json merged 2>$null
            if ($LASTEXITCODE -eq 0 -and $mergedJson) {
                try {
                    $mergeData = $mergedJson | ConvertFrom-Json
                    if ($mergeData.merged -eq $true) {
                        $reason = 'Follow-up contains no changes (original PR already merged)'
                    }
                }
                catch {
                    Write-Warning "Failed to parse merge status for PR #$OriginalPRNumber. Defaulting to standard reason. Error: $_"
                }
            }
        }

        return @{similarity = 100; category = 'DUPLICATE'; reason = $reason }
    }

    # Count file changes in follow-up
    $followUpFiles = @($FollowUpDiff -split '^diff --git' | Where-Object { $_.Trim() } | Measure-Object).Count

    # If follow-up has 1 file and original also modified that file, likely duplicate
    if ($followUpFiles -eq 1 -and $OriginalCommits.Count -gt 0) {
        return @{similarity = 85; category = 'LIKELY_DUPLICATE'; reason = 'Single file change matching original scope' }
    }

    # If follow-up has no file changes but adds comments/replies

    # Multiple files or complex diff = might be supplemental
    return @{similarity = 40; category = 'POSSIBLE_SUPPLEMENTAL'; reason = 'Multiple file changes suggest additional work' }
}

function Invoke-FollowUpDetection {
    <#
    .SYNOPSIS
        Main detection logic.
    #>

    Write-Verbose "Detecting Copilot follow-up PRs for PR #$PRNumber..."

    # Step 1: Query for follow-up PR matching pattern
    $followUpPRQuery = "head:copilot/sub-pr-$PRNumber"
    Write-Verbose "Searching for: $followUpPRQuery"

    $followUpPRs = @()
    try {
        $prJson = gh pr list --repo "$script:Owner/$script:Repo" --state open --search $followUpPRQuery `
            --json number,title,body,headRefName,baseRefName,state,author,createdAt 2>$null
        if ($LASTEXITCODE -eq 0 -and $prJson) {
            $prData = $prJson | ConvertFrom-Json
            if ($prData -is [array]) {
                $followUpPRs = @($prData)
            }
            elseif ($null -ne $prData) {
                $followUpPRs = @($prData)
            }
        }
    }
    catch {
        Write-Verbose "Info: No follow-up PRs found (query may not match any results)"
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

    Write-Verbose "Found $($followUpPRs.Count) follow-up PR(s)"

    # Step 2: Verify Copilot announcement
    $announcement = Get-CopilotAnnouncement -PRNumber $PRNumber
    if ($null -eq $announcement -or $announcement -eq '') {
        Write-Warning " No Copilot announcement found, but follow-up PR exists"
    }
    else {
        Write-Verbose "Verified Copilot announcement"
    }

    # Step 3: Analyze each follow-up PR
    $analysis = @()
    foreach ($followUp in $followUpPRs) {
        $prNum = $followUp.number
        Write-Verbose "Analyzing follow-up PR #$prNum..."

        $diff = Get-FollowUpPRDiff -FollowUpPRNumber $prNum
        $originalCommits = Get-OriginalPRCommits -PRNumber $PRNumber

        $comparison = Compare-DiffContent -FollowUpDiff $diff -OriginalCommits $originalCommits -OriginalPRNumber $PRNumber

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
