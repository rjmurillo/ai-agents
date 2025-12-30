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

Import-Module (Join-Path $PSScriptRoot ".." ".." "modules" "GitHubCore.psm1") -Force

Assert-GhAuthenticated
$resolved = Resolve-RepoParams -Owner $Owner -Repo $Repo
$script:Owner = $resolved.Owner
$script:Repo = $resolved.Repo

function Test-FollowUpPattern {
    <#
    .SYNOPSIS
        Check if a PR matches Copilot follow-up pattern for a specific original PR.
    .DESCRIPTION
        Validates that the branch name follows the copilot/sub-pr-{number} pattern
        AND that the extracted number matches the expected original PR number.
        This prevents false positives when multiple Copilot follow-up branches exist.
    .PARAMETER PR
        The PR object containing headRefName property.
    .PARAMETER OriginalPRNumber
        The original PR number to validate against. If not provided, only pattern matching is performed.
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        [object]$PR,

        [Parameter(Mandatory = $false)]
        [int]$OriginalPRNumber = 0
    )

    $headRef = $PR.headRefName
    # Use end-of-string anchor $ to ensure exact match (e.g., "copilot/sub-pr-32")
    # Prevents matching branches with ANY suffix like "32a", "32-fix", or "32_test"
    # Addresses Issue #507: regex allows non-numeric suffixes
    $pattern = 'copilot/sub-pr-(\d+)$'

    if ($headRef -match $pattern) {
        # If OriginalPRNumber is specified, validate the extracted number matches
        if ($OriginalPRNumber -gt 0) {
            $extractedPR = [int]$matches[1]
            return $extractedPR -eq $OriginalPRNumber
        }
        # No validation requested, just pattern match
        return $true
    }
    return $false
}

function Get-CopilotAnnouncement {
    <#
    .SYNOPSIS
        Find Copilot's announcement comment on the original PR.
    #>
    [CmdletBinding()]
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
    [CmdletBinding()]
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
    .DESCRIPTION
        Returns commits directly from PR metadata instead of querying repository commits.
        This optimization eliminates a redundant API call and avoids rate limit risk on large repos (Issue #290).
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        [int]$PRNumber
    )

    $prJson = gh pr view $PRNumber --repo "$script:Owner/$script:Repo" --json commits 2>$null
    if ($LASTEXITCODE -ne 0 -or $null -eq $prJson) {
        return @()
    }

    $pr = $prJson | ConvertFrom-Json
    if ($null -eq $pr -or -not $pr.commits) {
        return @()
    }

    return @($pr.commits)
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
    [CmdletBinding()]
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

    # Extract file paths from follow-up diff
    # Use multiline mode (?m) to make ^ match line-start, not just string-start
    # Addresses gemini-code-assist review comment (PR #503, comment ID 2651525060)
    # Issue #244: Extract actual file paths for comparison (not just count)
    $diffSections = @($FollowUpDiff -split '(?m)^diff --git' | Where-Object { $_.Trim() })
    $followUpFiles = @()
    foreach ($section in $diffSections) {
        # Extract file path from "a/path/to/file b/path/to/file" pattern
        if ($section -match 'a/(.+?)\s+b/') {
            $followUpFiles += $matches[1]
        }
    }

    # Extract file paths from original commits (Issue #244)
    $originalFiles = @()
    foreach ($commit in $OriginalCommits) {
        if ($commit.changedFiles) {
            $originalFiles += $commit.changedFiles
        }
    }
    $originalFiles = @($originalFiles | Select-Object -Unique)

    # Calculate file overlap for more accurate duplicate detection
    $overlapCount = 0
    foreach ($followUpFile in $followUpFiles) {
        if ($originalFiles -contains $followUpFile) {
            $overlapCount++
        }
    }

    # Calculate overlap percentage
    $overlapPercentage = 0
    if ($followUpFiles.Count -gt 0) {
        $overlapPercentage = [math]::Round(($overlapCount / $followUpFiles.Count) * 100)
    }

    # Determine category based on overlap analysis
    if ($followUpFiles.Count -eq 0) {
        return @{similarity = 100; category = 'DUPLICATE'; reason = 'No file changes detected in follow-up diff' }
    }

    if ($overlapPercentage -ge 80) {
        return @{similarity = $overlapPercentage; category = 'DUPLICATE'; reason = "High file overlap ($overlapCount of $($followUpFiles.Count) files match original PR)" }
    }

    if ($overlapPercentage -ge 50 -or ($followUpFiles.Count -eq 1 -and $OriginalCommits.Count -gt 0)) {
        return @{similarity = [math]::Max(85, $overlapPercentage); category = 'LIKELY_DUPLICATE'; reason = "Partial file overlap ($overlapCount of $($followUpFiles.Count) files match original PR)" }
    }

    if ($overlapPercentage -gt 0) {
        return @{similarity = $overlapPercentage; category = 'POSSIBLE_SUPPLEMENTAL'; reason = "Some file overlap ($overlapCount of $($followUpFiles.Count) files), may extend original work" }
    }

    # No overlap - likely independent or supplemental work
    return @{similarity = 0; category = 'INDEPENDENT'; reason = "No file overlap with original PR ($($followUpFiles.Count) new files)" }
}

function Invoke-FollowUpDetection {
    <#
    .SYNOPSIS
        Main detection logic.
    #>
    [CmdletBinding()]
    param()

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

    # Step 1.5: Filter results using Test-FollowUpPattern with PR number validation (Issue #292)
    # This prevents false positives from GitHub search returning partial matches
    $followUpPRs = @($followUpPRs | Where-Object {
        Test-FollowUpPattern -PR $_ -OriginalPRNumber $PRNumber
    })

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
            'INDEPENDENT' {
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
