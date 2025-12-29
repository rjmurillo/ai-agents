#!/usr/bin/env pwsh
<#
.SYNOPSIS
    PR discovery and classification for GitHub Actions matrix strategy.

.DESCRIPTION
    THIN ORCHESTRATION LAYER: Identifies PRs needing attention and outputs JSON
    for GitHub Actions matrix to spawn parallel pr-comment-responder jobs.

    This script ONLY does:
    - Discover open PRs
    - Classify each PR by activation trigger
    - Detect conflicts and derivative PRs
    - Output ActionRequired JSON for workflow matrix

    Processing is delegated to:
    - /pr-comment-responder: Comment acknowledgment, replies, thread resolution
    - /merge-resolver: Conflict resolution

    See: .agents/architecture/bot-author-feedback-protocol.md

.PARAMETER Owner
    Repository owner. Defaults to current repo owner.

.PARAMETER Repo
    Repository name. Defaults to current repo name.

.PARAMETER MaxPRs
    Maximum number of PRs to process in one run. Defaults to 20.

.PARAMETER LogPath
    Path to write detailed log file. Defaults to .agents/logs/pr-maintenance.log

.PARAMETER OutputJson
    Output ActionRequired PRs as JSON for matrix consumption.
    When specified, suppresses normal logging and outputs only JSON.

.EXAMPLE
    .\scripts\Invoke-PRMaintenance.ps1
    # Normal mode: logs summary and step summary

.EXAMPLE
    .\scripts\Invoke-PRMaintenance.ps1 -OutputJson
    # Matrix mode: outputs JSON for workflow consumption

.OUTPUTS
    When -OutputJson is specified:
    {
      "prs": [
        {"number": 123, "category": "agent-controlled", "hasConflicts": true, "reason": "CHANGES_REQUESTED"},
        {"number": 456, "category": "mention-triggered", "hasConflicts": false, "reason": "MENTION"}
      ],
      "summary": {
        "total": 5,
        "actionRequired": 2,
        "blocked": 1,
        "derivatives": 0
      }
    }

.NOTES
    Exit Codes:
    0 = Success
    2 = Error (script failure, API errors, fatal exceptions)
    Supports -WhatIf for dry-run mode (issue #461).
#>

[CmdletBinding(SupportsShouldProcess)]
param(
    [string]$Owner,
    [string]$Repo,
    [int]$MaxPRs = 20,
    [string]$LogPath,
    [switch]$OutputJson
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

#region Configuration

$script:Config = @{
    # Branches we must never commit to directly
    ProtectedBranches = @('main', 'master', 'develop')

    # Bot authors by category
    BotCategories = @{
        'agent-controlled' = @('rjmurillo-bot', 'rjmurillo[bot]')
        'mention-triggered' = @('copilot-swe-agent', 'copilot-swe-agent[bot]', 'copilot', 'app/copilot-swe-agent')
        'review-bot' = @('coderabbitai', 'coderabbitai[bot]', 'cursor[bot]', 'gemini-code-assist', 'gemini-code-assist[bot]')
    }
}

$script:StartTime = Get-Date
$script:LogBuffer = [System.Collections.ArrayList]::new()

#endregion

#region Logging

function Write-Log {
    [CmdletBinding()]
    param(
        [string]$Message,
        [ValidateSet('INFO', 'WARN', 'ERROR', 'SUCCESS', 'ACTION')]
        [string]$Level = 'INFO'
    )

    # Skip logging in JSON output mode
    if ($OutputJson) { return }

    $timestamp = Get-Date -Format 'yyyy-MM-dd HH:mm:ss'
    $color = switch ($Level) {
        'INFO'    { 'Gray' }
        'WARN'    { 'Yellow' }
        'ERROR'   { 'Red' }
        'SUCCESS' { 'Green' }
        'ACTION'  { 'Cyan' }
    }
    $entry = "[$timestamp] [$Level] $Message"
    Write-Host $entry -ForegroundColor $color
    $null = $script:LogBuffer.Add($entry)
}

function Save-Log {
    [CmdletBinding()]
    param([string]$Path)

    if ($OutputJson) { return }
    if (-not $Path) { return }

    $dir = Split-Path $Path -Parent
    if ($dir -and -not (Test-Path $dir)) {
        New-Item -ItemType Directory -Path $dir -Force | Out-Null
    }
    $script:LogBuffer -join "`n" | Set-Content -Path $Path -Encoding UTF8
}

#endregion

#region Security Validation

function Test-RateLimitSafe {
    [CmdletBinding()]
    param()

    $limits = gh api rate_limit 2>&1
    if ($LASTEXITCODE -ne 0) {
        Write-Log "Failed to check rate limit: $limits" -Level WARN
        return $true  # Assume safe if can't check
    }

    try {
        $parsed = $limits | ConvertFrom-Json
        $core = $parsed.resources.core
        $graphql = $parsed.resources.graphql

        # Need at least 100 core and 50 graphql remaining
        if ($core.remaining -lt 100 -or $graphql.remaining -lt 50) {
            Write-Log "Rate limit too low: core=$($core.remaining), graphql=$($graphql.remaining)" -Level WARN
            return $false
        }
        return $true
    }
    catch {
        Write-Log "Failed to parse rate limit response: $_" -Level WARN
        return $true
    }
}

#endregion

#region GitHub API Helpers

function Invoke-GhApi {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)]
        [string]$Endpoint,
        [string]$Method = 'GET',
        [string]$Body
    )

    $args = @('api', $Endpoint)
    if ($Method -ne 'GET') {
        $args += @('--method', $Method)
    }
    if ($Body) {
        $args += @('--input', '-')
        $result = $Body | gh @args 2>&1
    } else {
        $result = gh @args 2>&1
    }

    if ($LASTEXITCODE -ne 0) {
        Write-Log "API call failed: $Endpoint - $result" -Level WARN
        return $null
    }
    return $result
}

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

#region PR Discovery

function Get-OpenPRs {
    [CmdletBinding()]
    param(
        [string]$Owner,
        [string]$Repo,
        [int]$Limit = 20
    )

    # Uses GraphQL variables for security (prevents injection via Owner/Repo)
    $query = @'
query($owner: String!, $name: String!, $limit: Int!) {
    repository(owner: $owner, name: $name) {
        pullRequests(first: $limit, states: OPEN, orderBy: {field: UPDATED_AT, direction: DESC}) {
            nodes {
                number
                title
                author { login }
                headRefName
                baseRefName
                mergeable
                reviewDecision
                reviewRequests(first: 10) {
                    nodes {
                        requestedReviewer {
                            ... on User { login }
                            ... on Team { name }
                            ... on Bot { login }
                        }
                    }
                }
                commits(last: 1) {
                    nodes {
                        commit {
                            statusCheckRollup {
                                state
                                contexts(first: 100) {
                                    nodes {
                                        ... on CheckRun {
                                            name
                                            conclusion
                                            status
                                        }
                                        ... on StatusContext {
                                            context
                                            state
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
    }
}
'@

    $result = gh api graphql -f query=$query -f owner="$Owner" -f name="$Repo" -F limit=$Limit 2>&1
    if ($LASTEXITCODE -ne 0) {
        Write-Log "Failed to query PRs: $result" -Level ERROR
        return @()
    }

    try {
        $parsed = $result | ConvertFrom-Json
        return @($parsed.data.repository.pullRequests.nodes)
    }
    catch {
        Write-Log "Failed to parse PR query response: $_" -Level ERROR
        return @()
    }
}

#endregion

#region Classification

function Get-BotAuthorInfo {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)]
        [string]$AuthorLogin
    )

    foreach ($category in $script:Config.BotCategories.Keys) {
        $bots = $script:Config.BotCategories[$category]
        foreach ($bot in $bots) {
            if ($AuthorLogin -ieq $bot -or $AuthorLogin -imatch "^$([regex]::Escape($bot))") {
                return @{
                    IsBot = $true
                    Category = $category
                    Name = $AuthorLogin
                }
            }
        }
    }

    return @{
        IsBot = $false
        Category = 'human'
        Name = $AuthorLogin
    }
}

function Test-IsBotReviewer {
    [CmdletBinding()]
    param(
        [Parameter()]
        $ReviewRequests
    )

    if ($null -eq $ReviewRequests -or $null -eq $ReviewRequests.nodes) {
        return $false
    }

    foreach ($request in $ReviewRequests.nodes) {
        $reviewer = $request.requestedReviewer
        if ($null -eq $reviewer) { continue }

        $login = $reviewer.login
        if (-not $login) { continue }

        $botInfo = Get-BotAuthorInfo -AuthorLogin $login
        if ($botInfo.IsBot -and $botInfo.Category -eq 'agent-controlled') {
            return $true
        }
    }

    return $false
}

function Test-PRHasConflicts {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)]
        $PR
    )

    return $PR.mergeable -eq 'CONFLICTING'
}

function Test-PRHasFailingChecks {
    <#
    .SYNOPSIS
        Checks if a PR has failing CI checks.

    .DESCRIPTION
        Examines the statusCheckRollup from the PR's latest commit to determine
        if any required checks have failed. This enables detecting PRs that need
        attention due to CI failures (e.g., Session Protocol validation failures).

    .PARAMETER PR
        The PR object from GraphQL query containing commits.nodes[0].commit.statusCheckRollup.
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)]
        $PR
    )

    # Helper to safely get property (strict mode compatible, works with hashtables and PSObjects)
    # Uses Write-Output -NoEnumerate to preserve arrays (prevents PowerShell unrolling)
    function Get-SafeProperty {
        param($Object, [string]$PropertyName)
        if ($null -eq $Object) { return $null }

        $value = $null

        # Handle hashtables
        if ($Object -is [hashtable]) {
            if ($Object.ContainsKey($PropertyName)) {
                $value = $Object[$PropertyName]
            }
        }
        # Handle PSObjects (from JSON parsing)
        elseif ($Object.PSObject.Properties.Name -contains $PropertyName) {
            $value = $Object.$PropertyName
        }

        # Preserve arrays when returning (prevent PowerShell unrolling)
        if ($null -ne $value -and $value -is [array]) {
            return @(,$value)  # Wrap in array to prevent unrolling
        }
        return $value
    }

    # Safely navigate the nested structure
    $commits = Get-SafeProperty $PR 'commits'
    if (-not $commits) { return $false }

    $nodes = Get-SafeProperty $commits 'nodes'
    if (-not $nodes -or $nodes.Count -eq 0) { return $false }

    $firstNode = $nodes[0]
    if (-not $firstNode) { return $false }

    $commit = Get-SafeProperty $firstNode 'commit'
    if (-not $commit) { return $false }

    $rollup = Get-SafeProperty $commit 'statusCheckRollup'
    if (-not $rollup) { return $false }

    # Check overall state first (FAILURE, ERROR, PENDING, SUCCESS, EXPECTED)
    $state = Get-SafeProperty $rollup 'state'
    if ($state -and $state -in @('FAILURE', 'ERROR')) {
        return $true
    }

    # Also check individual check runs for FAILURE conclusion
    $contexts = Get-SafeProperty $rollup 'contexts'
    if (-not $contexts) { return $false }

    $contextNodes = Get-SafeProperty $contexts 'nodes'
    if (-not $contextNodes) { return $false }

    foreach ($ctx in $contextNodes) {
        if (-not $ctx) { continue }

        # CheckRun has 'conclusion', StatusContext has 'state'
        $conclusion = Get-SafeProperty $ctx 'conclusion'
        $ctxState = Get-SafeProperty $ctx 'state'

        if ($conclusion -eq 'FAILURE' -or $ctxState -eq 'FAILURE') {
            return $true
        }
    }

    return $false
}

#endregion

#region Derivative Detection

function Get-DerivativePRs {
    [CmdletBinding()]
    param(
        [string]$Owner,
        [string]$Repo,
        [array]$OpenPRs
    )

    $derivatives = @()
    $protectedBranches = $script:Config.ProtectedBranches

    foreach ($pr in $OpenPRs) {
        # Derivative = targets a non-protected branch (feature branch)
        if ($pr.baseRefName -notin $protectedBranches) {
            $derivatives += @{
                Number = $pr.number
                Title = $pr.title
                Author = $pr.author.login
                TargetBranch = $pr.baseRefName
                SourceBranch = $pr.headRefName
            }
        }
    }

    return $derivatives
}

function Get-PRsWithPendingDerivatives {
    [CmdletBinding()]
    param(
        [string]$Owner,
        [string]$Repo,
        [array]$OpenPRs,
        [array]$Derivatives
    )

    $parentsWithDerivatives = @()

    foreach ($derivative in $Derivatives) {
        # Find parent PR that has headRefName matching derivative's baseRefName
        $parentPR = $OpenPRs | Where-Object { $_.headRefName -eq $derivative.TargetBranch } | Select-Object -First 1
        if ($parentPR) {
            # Check if we already have this parent in the list
            $existing = $parentsWithDerivatives | Where-Object { $_.ParentPR -eq $parentPR.number }
            if ($existing) {
                $existing.Derivatives += $derivative.Number
            } else {
                $parentsWithDerivatives += @{
                    ParentPR = $parentPR.number
                    ParentTitle = $parentPR.title
                    ParentBranch = $parentPR.headRefName
                    Derivatives = @($derivative.Number)
                }
            }
        }
    }

    return $parentsWithDerivatives
}

#endregion

#region Main Logic

function Invoke-PRMaintenance {
    [CmdletBinding()]
    param(
        [string]$Owner,
        [string]$Repo,
        [int]$MaxPRs
    )

    $results = @{
        TotalPRs = 0
        ActionRequired = [System.Collections.ArrayList]::new()
        Blocked = [System.Collections.ArrayList]::new()
        DerivativePRs = [System.Collections.ArrayList]::new()
        ParentsWithDerivatives = [System.Collections.ArrayList]::new()
        Errors = [System.Collections.ArrayList]::new()
    }

    Write-Log "Starting PR discovery" -Level INFO
    Write-Log "Repository: $Owner/$Repo" -Level INFO
    Write-Log "MaxPRs: $MaxPRs" -Level INFO

    # Get all open PRs
    $prs = Get-OpenPRs -Owner $Owner -Repo $Repo -Limit $MaxPRs
    $results.TotalPRs = $prs.Count
    Write-Log "Found $($prs.Count) open PRs" -Level INFO

    # Detect derivative PRs
    $derivatives = @(Get-DerivativePRs -Owner $Owner -Repo $Repo -OpenPRs $prs)
    if ($derivatives.Count -gt 0) {
        Write-Log "Found $($derivatives.Count) derivative PR(s)" -Level WARN
        foreach ($d in $derivatives) {
            $null = $results.DerivativePRs.Add($d)
        }

        $parentsWithDerivatives = Get-PRsWithPendingDerivatives -Owner $Owner -Repo $Repo -OpenPRs $prs -Derivatives $derivatives
        foreach ($p in $parentsWithDerivatives) {
            $null = $results.ParentsWithDerivatives.Add($p)
            $null = $results.ActionRequired.Add(@{
                number = $p.ParentPR
                category = 'has-derivatives'
                hasConflicts = $false
                reason = 'PENDING_DERIVATIVES'
                author = 'N/A'
                title = $p.ParentTitle
                derivatives = $p.Derivatives
            })
        }
    }

    # Classify each PR
    foreach ($pr in $prs) {
        Write-Log "Classifying PR #$($pr.number): $($pr.title)" -Level INFO

        try {
            $authorLogin = $pr.author.login
            $botInfo = Get-BotAuthorInfo -AuthorLogin $authorLogin
            $isAgentControlledBot = $botInfo.IsBot -and $botInfo.Category -eq 'agent-controlled'
            $isMentionTriggeredBot = $botInfo.IsBot -and $botInfo.Category -eq 'mention-triggered'
            $isBotReviewer = Test-IsBotReviewer -ReviewRequests $pr.reviewRequests
            $hasChangesRequested = $pr.reviewDecision -eq 'CHANGES_REQUESTED'
            $hasConflicts = Test-PRHasConflicts -PR $pr
            $hasFailingChecks = Test-PRHasFailingChecks -PR $pr

            # Decision flow (classification only - no processing)
            #
            # Priority 1: Agent-controlled bot (rjmurillo-bot) as author or reviewer
            # Priority 2: Mention-triggered bot (copilot-swe-agent) with rjmurillo-bot as reviewer
            #             -> rjmurillo-bot can synthesize comments and @copilot to unblock
            # Priority 3: Human-authored PRs (blocked, require human action)

            if ($isAgentControlledBot -or $isBotReviewer) {
                $role = if ($isAgentControlledBot) { 'author' } else { 'reviewer' }

                if ($hasChangesRequested) {
                    Write-Log "PR #$($pr.number): rjmurillo-bot is $role with CHANGES_REQUESTED" -Level WARN
                    $null = $results.ActionRequired.Add(@{
                        number = $pr.number
                        category = 'agent-controlled'
                        hasConflicts = $hasConflicts
                        hasFailingChecks = $hasFailingChecks
                        reason = 'CHANGES_REQUESTED'
                        author = $authorLogin
                        title = $pr.title
                        headRefName = $pr.headRefName
                        baseRefName = $pr.baseRefName
                    })
                }
                elseif ($hasConflicts) {
                    Write-Log "PR #$($pr.number): rjmurillo-bot is $role with conflicts" -Level WARN
                    $null = $results.ActionRequired.Add(@{
                        number = $pr.number
                        category = 'agent-controlled'
                        hasConflicts = $true
                        hasFailingChecks = $hasFailingChecks
                        reason = 'HAS_CONFLICTS'
                        author = $authorLogin
                        title = $pr.title
                        headRefName = $pr.headRefName
                        baseRefName = $pr.baseRefName
                    })
                }
                elseif ($hasFailingChecks) {
                    Write-Log "PR #$($pr.number): rjmurillo-bot is $role with failing checks" -Level WARN
                    $null = $results.ActionRequired.Add(@{
                        number = $pr.number
                        category = 'agent-controlled'
                        hasConflicts = $false
                        hasFailingChecks = $true
                        reason = 'HAS_FAILING_CHECKS'
                        author = $authorLogin
                        title = $pr.title
                        headRefName = $pr.headRefName
                        baseRefName = $pr.baseRefName
                    })
                }
                else {
                    Write-Log "PR #$($pr.number): rjmurillo-bot is $role, no action needed" -Level INFO
                }
            }
            elseif ($isMentionTriggeredBot) {
                # Copilot-SWE-Agent PR - rjmurillo-bot can synthesize comments and @copilot to unblock
                # No need to check if rjmurillo-bot is reviewer - we can always help
                # Triggers: CHANGES_REQUESTED, HAS_CONFLICTS, or HAS_FAILING_CHECKS
                if ($hasChangesRequested -or $hasConflicts -or $hasFailingChecks) {
                    $reason = if ($hasChangesRequested) { 'CHANGES_REQUESTED' }
                              elseif ($hasConflicts) { 'HAS_CONFLICTS' }
                              else { 'HAS_FAILING_CHECKS' }
                    Write-Log "PR #$($pr.number): $authorLogin PR needs @copilot synthesis ($reason)" -Level WARN
                    $null = $results.ActionRequired.Add(@{
                        number = $pr.number
                        category = 'mention-triggered'
                        hasConflicts = $hasConflicts
                        hasFailingChecks = $hasFailingChecks
                        reason = $reason
                        author = $authorLogin
                        title = $pr.title
                        headRefName = $pr.headRefName
                        baseRefName = $pr.baseRefName
                        requiresSynthesis = $true
                    })
                }
                else {
                    Write-Log "PR #$($pr.number): $authorLogin PR, no action needed" -Level INFO
                }
            }
            else {
                # Human-authored PRs or mention-triggered bots without rjmurillo-bot reviewer
                if ($hasChangesRequested) {
                    Write-Log "PR #$($pr.number): Human-authored with CHANGES_REQUESTED" -Level INFO
                    $null = $results.Blocked.Add(@{
                        number = $pr.number
                        category = 'human-blocked'
                        hasConflicts = $hasConflicts
                        reason = 'CHANGES_REQUESTED'
                        author = $authorLogin
                        title = $pr.title
                    })
                }
                elseif ($hasConflicts) {
                    Write-Log "PR #$($pr.number): Human-authored with conflicts" -Level INFO
                    $null = $results.Blocked.Add(@{
                        number = $pr.number
                        category = 'human-blocked'
                        hasConflicts = $true
                        reason = 'HAS_CONFLICTS'
                        author = $authorLogin
                        title = $pr.title
                    })
                }
                elseif ($hasFailingChecks) {
                    Write-Log "PR #$($pr.number): Human-authored with failing checks" -Level INFO
                    $null = $results.Blocked.Add(@{
                        number = $pr.number
                        category = 'human-blocked'
                        hasConflicts = $false
                        hasFailingChecks = $true
                        reason = 'HAS_FAILING_CHECKS'
                        author = $authorLogin
                        title = $pr.title
                    })
                }
            }
        }
        catch {
            Write-Log "Error classifying PR #$($pr.number): $_" -Level ERROR
            $null = $results.Errors.Add(@{
                PR = $pr.number
                Error = $_.ToString()
            })
        }
    }

    return $results
}

#endregion

#region Entry Point

# Guard: Only execute main logic when run directly, not when dot-sourced for testing
if ($MyInvocation.InvocationName -eq '.') {
    return
}

try {
    # Check API rate limit
    if (-not (Test-RateLimitSafe)) {
        if (-not $OutputJson) {
            Write-Log "Exiting: API rate limit too low" -Level WARN
        }
        exit 0
    }

    # Resolve repo info
    if (-not $Owner -or -not $Repo) {
        $repoInfo = Get-RepoInfo
        if (-not $Owner) { $Owner = $repoInfo.Owner }
        if (-not $Repo) { $Repo = $repoInfo.Repo }
    }

    # Run discovery
    $results = Invoke-PRMaintenance -Owner $Owner -Repo $Repo -MaxPRs $MaxPRs

    # JSON Output Mode (for workflow matrix)
    if ($OutputJson) {
        # Sort: conflicts first (most urgent), then failing checks, then other issues
        $sortedPRs = @($results.ActionRequired | Sort-Object -Property @{
            Expression = { $_.hasConflicts }
            Descending = $true
        }, @{
            Expression = { $_.hasFailingChecks }
            Descending = $true
        }, @{
            Expression = { $_.number }
            Ascending = $true
        })

        $output = @{
            prs = $sortedPRs
            summary = @{
                total = $results.TotalPRs
                actionRequired = $results.ActionRequired.Count
                blocked = $results.Blocked.Count
                derivatives = $results.DerivativePRs.Count
            }
        }
        $output | ConvertTo-Json -Depth 10 -Compress
        exit 0
    }

    # Normal Mode: Log summary
    Write-Log "---" -Level INFO
    Write-Log "=== PR Discovery Summary ===" -Level INFO
    Write-Log "Open PRs: $($results.TotalPRs)" -Level INFO
    Write-Log "Action Required: $($results.ActionRequired.Count)" -Level $(if ($results.ActionRequired.Count -gt 0) { 'WARN' } else { 'INFO' })
    Write-Log "Blocked (human): $($results.Blocked.Count)" -Level $(if ($results.Blocked.Count -gt 0) { 'WARN' } else { 'INFO' })
    Write-Log "Derivatives: $($results.DerivativePRs.Count)" -Level $(if ($results.DerivativePRs.Count -gt 0) { 'WARN' } else { 'INFO' })

    if ($results.ActionRequired.Count -gt 0) {
        Write-Log "---" -Level INFO
        Write-Log "PRs Requiring Action:" -Level WARN
        foreach ($item in $results.ActionRequired) {
            Write-Log "  PR #$($item.number): $($item.reason) [$($item.category)]" -Level WARN
            if ($item.hasConflicts) {
                Write-Log "    -> Has conflicts, run /merge-resolver first" -Level INFO
            }
        }

        $prNumbers = ($results.ActionRequired | ForEach-Object { $_.number }) -join ','
        Write-Log "Run: /pr-comment-responder $prNumbers" -Level INFO
    }

    if ($results.Blocked.Count -gt 0) {
        Write-Log "---" -Level INFO
        Write-Log "Blocked PRs (require human action):" -Level WARN
        foreach ($blocked in $results.Blocked) {
            Write-Log "  PR #$($blocked.number): $($blocked.reason) - $($blocked.title)" -Level WARN
        }
    }

    $duration = (Get-Date) - $script:StartTime
    Write-Log "---" -Level INFO
    Write-Log "Completed in $([math]::Round($duration.TotalSeconds, 1)) seconds" -Level INFO

    # GitHub Actions step summary
    if ($env:GITHUB_STEP_SUMMARY) {
        $summary = @"
## PR Discovery Summary

| Metric | Count |
|--------|-------|
| Open PRs Scanned | $($results.TotalPRs) |
| PRs Need Action | $($results.ActionRequired.Count) |
| Blocked (human) | $($results.Blocked.Count) |
| Derivative PRs | $($results.DerivativePRs.Count) |
| Errors | $($results.Errors.Count) |

"@
        if ($results.ActionRequired.Count -gt 0) {
            $summary += @"
### PRs Requiring Action

| PR | Category | Reason | Has Conflicts |
|----|----------|--------|---------------|
"@
            foreach ($item in $results.ActionRequired) {
                $conflictIcon = if ($item.hasConflicts) { ':warning:' } else { ':white_check_mark:' }
                $summary += "| #$($item.number) | $($item.category) | $($item.reason) | $conflictIcon |`n"
            }
            $summary += "`n"
        }

        if ($results.Blocked.Count -gt 0) {
            $summary += @"
### Blocked PRs (Human Action Required)

| PR | Author | Reason |
|----|--------|--------|
"@
            foreach ($blocked in $results.Blocked) {
                $summary += "| #$($blocked.number) | $($blocked.author) | $($blocked.reason) |`n"
            }
        }

        $summary | Out-File -FilePath $env:GITHUB_STEP_SUMMARY -Append -Encoding UTF8
    }

    # Save log
    if ($LogPath) {
        Save-Log -Path $LogPath
    }
}
catch {
    Write-Log "Fatal error: $_" -Level ERROR
    exit 2
}

#endregion
