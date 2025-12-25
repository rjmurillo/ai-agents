#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Automated PR maintenance script for unattended operation.

.DESCRIPTION
    Processes all open PRs to:
    - Acknowledge unacknowledged bot comments (eyes reaction)
    - Resolve merge conflicts with main
    - Close PRs superseded by merged PRs
    - Report blocked PRs (CHANGES_REQUESTED, needs human approval)

    Designed to run periodically (e.g., hourly via cron/Task Scheduler).

.PARAMETER Owner
    Repository owner. Defaults to current repo owner.

.PARAMETER Repo
    Repository name. Defaults to current repo name.

.PARAMETER MaxPRs
    Maximum number of PRs to process in one run. Defaults to 20.

.PARAMETER LogPath
    Path to write detailed log file. Defaults to .agents/logs/pr-maintenance.log

.EXAMPLE
    .\scripts\Invoke-PRMaintenance.ps1

.EXAMPLE
    .\scripts\Invoke-PRMaintenance.ps1 -MaxPRs 5

.NOTES
    Exit Codes:
    0 = Success (all PRs processed, blocked PRs reported via separate step)
    1 = Reserved for future use
    2 = Error (script failure, API errors, fatal exceptions)
#>

[CmdletBinding()]
param(
    [string]$Owner,
    [string]$Repo,
    [int]$MaxPRs = 20,
    [string]$LogPath
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

#region Configuration

$script:Config = @{
    # Branches we must never commit to directly
    ProtectedBranches = @('main', 'master', 'develop')

    # Bot authors whose comments need acknowledgment
    BotAuthors = @('Copilot', 'coderabbitai[bot]', 'gemini-code-assist[bot]', 'cursor[bot]')

    # Reaction to add for acknowledgment
    AcknowledgeReaction = 'eyes'

    # Worktree base path (relative to repo root)
    WorktreeBasePath = '..'

    # Maximum time to wait for CI (seconds)
    CIWaitTimeout = 300
}

#endregion

#region Security Validation (P0 Fixes - ADR-015)

<#
.SYNOPSIS
    Validates branch name for command injection prevention.
.DESCRIPTION
    Rejects branch names that could be used for command injection or path traversal.
    ADR-015 Fix 1: Branch Name Validation (Security HIGH)
#>
function Test-SafeBranchName {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)]
        [string]$BranchName
    )

    # Empty or whitespace
    if ([string]::IsNullOrWhiteSpace($BranchName)) {
        Write-Log "Invalid branch name: empty or whitespace" -Level WARN
        return $false
    }

    # Starts with hyphen (could be interpreted as git option)
    if ($BranchName.StartsWith('-')) {
        Write-Log "Invalid branch name: starts with hyphen" -Level WARN
        return $false
    }

    # Contains path traversal
    if ($BranchName.Contains('..')) {
        Write-Log "Invalid branch name: contains path traversal" -Level WARN
        return $false
    }

    # Control characters
    if ($BranchName -match '[\x00-\x1f\x7f]') {
        Write-Log "Invalid branch name: contains control characters" -Level WARN
        return $false
    }

    # Git special characters that could cause issues
    if ($BranchName -match '[~^:?*\[\]\\]') {
        Write-Log "Invalid branch name: contains git special characters" -Level WARN
        return $false
    }

    # Shell metacharacters
    if ($BranchName -match '[`$;&|<>(){}]') {
        Write-Log "Invalid branch name: contains shell metacharacters" -Level WARN
        return $false
    }

    return $true
}

<#
.SYNOPSIS
    Gets a validated worktree path that cannot escape the base directory.
.DESCRIPTION
    Ensures worktree path is within allowed base directory to prevent path traversal.
    ADR-015 Fix 2: Worktree Path Validation (Security HIGH)
#>
function Get-SafeWorktreePath {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)]
        [string]$BasePath,

        [Parameter(Mandatory)]
        [long]$PRNumber
    )

    # Validate PR number is positive
    if ($PRNumber -le 0) {
        throw "Invalid PR number: $PRNumber"
    }

    # Resolve base path to absolute
    $base = Resolve-Path $BasePath -ErrorAction Stop

    # Construct worktree path (PR number is safe - validated as positive long)
    $worktreeName = "ai-agents-pr-$PRNumber"
    $worktreePath = Join-Path $base.Path $worktreeName

    # Get full path and verify it's within base
    $resolved = [System.IO.Path]::GetFullPath($worktreePath)
    if (-not $resolved.StartsWith($base.Path)) {
        throw "Worktree path escapes base directory: $worktreePath"
    }

    return $resolved
}

<#
.SYNOPSIS
    No-op script-level lock retained for compatibility.
.DESCRIPTION
    ADR-015 Decision 1 explicitly rejects file-based locking in favor of
    GitHub Actions concurrency groups on ephemeral runners because:
      - File-based locks add complexity without meaningful benefit
      - Runners are isolated per job, so cross-job file locks are ineffective

    This function is retained as a thin shim so existing call sites continue
    to work, but it does NOT implement any file-based locking. Concurrency
    protection is provided exclusively by the workflow's concurrency group.
#>
function Enter-ScriptLock {
    [CmdletBinding()]
    param()
    Write-Log "Enter-ScriptLock: no-op (ADR-015: rely on GitHub Actions concurrency group, not file-based locks)" -Level INFO
    return $true
}

<#
.SYNOPSIS
    No-op release for the script-level lock.
.DESCRIPTION
    Kept for compatibility with existing call sites. Does not modify any
    filesystem state because file-based locks were deprecated by ADR-015.
#>
function Exit-ScriptLock {
    [CmdletBinding()]
    param()
    Write-Log "Exit-ScriptLock: no-op (ADR-015: file-based locks deprecated)" -Level INFO
}

<#
.SYNOPSIS
    Checks GitHub API rate limit before processing.
.DESCRIPTION
    Prevents script from running when API rate limit is too low.
    Checks multiple resource types with resource-specific thresholds.
    ADR-015 Fix 6: Multi-Resource Rate Limit Check (DevOps/HLA P0)
#>
function Test-RateLimitSafe {
    [CmdletBinding()]
    param(
        [hashtable]$ResourceThresholds = @{
            'core' = 100           # General API calls
            'search' = 15          # 50% of 30 limit
            'code_search' = 5      # 50% of 10 limit
            'graphql' = 100        # 50% of 5000 limit (low because we use REST mostly)
        }
    )

    try {
        $rateLimitJson = gh api rate_limit 2>&1
        if ($LASTEXITCODE -ne 0) {
            Write-Log "Failed to check rate limit: $rateLimitJson" -Level WARN
            return $true  # Proceed on error - don't block if we can't check
        }

        $rateLimit = $rateLimitJson | ConvertFrom-Json
        $allResourcesSafe = $true
        $violations = @()

        foreach ($resourceName in $ResourceThresholds.Keys) {
            $threshold = $ResourceThresholds[$resourceName]
            $resource = $rateLimit.resources.$resourceName
            
            if ($null -eq $resource) {
                Write-Log "Resource '$resourceName' not found in rate limit response" -Level WARN
                continue
            }

            $remaining = [int]$resource.remaining
            $limit = [int]$resource.limit
            $resetEpoch = [int]$resource.reset

            if ($remaining -lt $threshold) {
                # Calculate reset time for smarter scheduling (P1 fix from PR #249)
                $resetTime = [DateTimeOffset]::FromUnixTimeSeconds($resetEpoch).LocalDateTime
                $timeUntilReset = $resetTime - (Get-Date)
                $violations += "${resourceName}: ${remaining}/${limit} (threshold: ${threshold}, resets in $([int]$timeUntilReset.TotalMinutes) minutes)"
                $allResourcesSafe = $false
            }
            else {
                Write-Log "Rate limit OK for ${resourceName}: ${remaining}/${limit} remaining" -Level INFO
            }
        }

        if (-not $allResourcesSafe) {
            Write-Log "API rate limit too low for: $($violations -join ', ')" -Level WARN
            # Log next available run time for scheduling
            $coreReset = [DateTimeOffset]::FromUnixTimeSeconds([int]$rateLimit.resources.core.reset).UtcDateTime
            Write-Log "Rate limit resets at: $($coreReset.ToString('yyyy-MM-dd HH:mm:ss')) UTC" -Level INFO
            return $false
        }

        Write-Log "All API rate limits OK" -Level INFO
        return $true
    }
    catch {
        Write-Log "Rate limit check failed: $_" -Level WARN
        return $true  # Proceed on error
    }
}

#endregion

#region Logging

$script:LogEntries = [System.Collections.ArrayList]::new()
$script:StartTime = Get-Date

function Write-Log {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)]
        [string]$Message,

        [ValidateSet('INFO', 'WARN', 'ERROR', 'SUCCESS', 'ACTION')]
        [string]$Level = 'INFO'
    )

    $timestamp = Get-Date -Format 'yyyy-MM-dd HH:mm:ss'
    $entry = "[$timestamp] [$Level] $Message"

    $null = $script:LogEntries.Add($entry)

    $color = switch ($Level) {
        'INFO'    { 'Gray' }
        'WARN'    { 'Yellow' }
        'ERROR'   { 'Red' }
        'SUCCESS' { 'Green' }
        'ACTION'  { 'Cyan' }
        default   { 'White' }
    }

    Write-Host $entry -ForegroundColor $color
}

function Save-Log {
    [CmdletBinding()]
    param([string]$Path)

    if (-not $Path) {
        $Path = Join-Path $PSScriptRoot '..' '.agents' 'logs' 'pr-maintenance.log'
    }

    $logDir = Split-Path $Path -Parent
    if (-not (Test-Path $logDir)) {
        New-Item -ItemType Directory -Path $logDir -Force | Out-Null
    }

    $script:LogEntries | Out-File -FilePath $Path -Append -Encoding utf8
    Write-Log "Log saved to: $Path" -Level INFO
}

#endregion

#region GitHub API Helpers

function Invoke-GhApi {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)]
        [string]$Endpoint,

        [string]$Method = 'GET',

        [hashtable]$Body,

        [string]$JqFilter
    )

    $args = @('api', $Endpoint)

    if ($Method -ne 'GET') {
        $args += '-X', $Method
    }

    if ($Body) {
        foreach ($key in $Body.Keys) {
            $args += '-f', "$key=$($Body[$key])"
        }
    }

    if ($JqFilter) {
        $args += '--jq', $JqFilter
    }

    $result = & gh @args 2>&1

    if ($LASTEXITCODE -ne 0) {
        throw "GitHub API call failed: $result"
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

#region PR Processing Functions

function Get-OpenPRs {
    [CmdletBinding()]
    param(
        [string]$Owner,
        [string]$Repo,
        [int]$Limit
    )

    $result = gh pr list --repo "$Owner/$Repo" --state open --limit $Limit --json number,title,state,headRefName,baseRefName,mergeable,reviewDecision,author 2>&1

    if ($LASTEXITCODE -ne 0) {
        throw "Failed to list PRs: $result"
    }

    # Skill-PowerShell-002: Return @() not $null for empty results
    # Wrap in @() to ensure empty JSON array "[]" becomes empty PowerShell array, not $null
    # Use comma operator to prevent array unwrapping on return
    $parsed = @($result | ConvertFrom-Json)
    if ($parsed.Count -eq 0) {
        return , @()
    }
    return , $parsed
}

function Get-PRComments {
    <#
    .SYNOPSIS
        Gets all comments for a PR.
    .DESCRIPTION
        Retrieves PR review comments using the GitHub API.
        Part of the PR comment acknowledgment workflow.
    #>
    [CmdletBinding()]
    param(
        [string]$Owner,
        [string]$Repo,
        [int]$PRNumber
    )

    $endpoint = "repos/$Owner/$Repo/pulls/$PRNumber/comments"
    $result = Invoke-GhApi -Endpoint $endpoint

    # Skill-PowerShell-002: Return @() not $null for empty results
    $parsed = $result | ConvertFrom-Json
    if ($null -eq $parsed) {
        Write-Output -NoEnumerate @()
        return
    }
    Write-Output -NoEnumerate @($parsed)
}

function Get-UnacknowledgedComments {
    <#
    .SYNOPSIS
        Gets bot comments that haven't been acknowledged with an eyes reaction.
    .DESCRIPTION
        Filters PR review comments to find bot-generated comments without acknowledgment.
        Works in conjunction with Get-PRComments and Add-CommentReaction to form
        the complete acknowledgment workflow.

        NOTE: Bot author list should ideally reference the agent configuration files
        (.claude/commands/pr-review.md, src/claude/pr-comment-responder.md) to avoid
        duplication and drift. Current implementation uses environment-configured list.
    #>
    [CmdletBinding()]
    param(
        [string]$Owner,
        [string]$Repo,
        [int]$PRNumber
    )

    $comments = Get-PRComments -Owner $Owner -Repo $Repo -PRNumber $PRNumber

    # Skill-PowerShell-002: Return @() not $null for empty results
    # Filter comments and ensure array return
    $unacked = @($comments | Where-Object {
        $_.user.type -eq 'Bot' -and
        $_.reactions.eyes -eq 0
    })
    if ($null -eq $unacked -or $unacked.Count -eq 0) {
        Write-Output -NoEnumerate @()
        return
    }
    Write-Output -NoEnumerate $unacked
}

function Add-CommentReaction {
    [CmdletBinding()]
    param(
        [string]$Owner,
        [string]$Repo,
        [long]$CommentId,  # ADR-015 Fix 4: Int64 to prevent overflow (GitHub IDs exceed Int32.MaxValue)
        [string]$Reaction = 'eyes'
    )

    $endpoint = "repos/$Owner/$Repo/pulls/comments/$CommentId/reactions"

    try {
        $null = Invoke-GhApi -Endpoint $endpoint -Method POST -Body @{ content = $Reaction }
        return $true
    }
    catch {
        Write-Log "Failed to add reaction to comment $CommentId`: $_" -Level WARN
        return $false
    }
}

function Test-PRHasConflicts {
    [CmdletBinding()]
    param(
        [string]$Owner,
        [string]$Repo,
        [int]$PRNumber
    )

    $pr = gh pr view $PRNumber --repo "$Owner/$Repo" --json mergeable --jq '.mergeable' 2>&1
    if ($LASTEXITCODE -ne 0) {
        Write-Log "Failed to check PR #$PRNumber mergeable status: $pr" -Level WARN
        return $false  # Fail-safe: assume no conflicts if we can't check
    }
    return $pr -eq 'CONFLICTING'
}

function Test-PRNeedsOwnerAction {
    [CmdletBinding()]
    param(
        [string]$Owner,
        [string]$Repo,
        [int]$PRNumber
    )

    $pr = gh pr view $PRNumber --repo "$Owner/$Repo" --json reviewDecision --jq '.reviewDecision' 2>&1
    if ($LASTEXITCODE -ne 0) {
        Write-Log "Failed to check PR #$PRNumber review decision: $pr" -Level WARN
        return $false  # Fail-safe: assume no action needed if we can't check
    }
    return $pr -eq 'CHANGES_REQUESTED'
}

function Test-IsGitHubRunner {
    <#
    .SYNOPSIS
        Detects if the script is running in a GitHub Actions runner environment.
    .DESCRIPTION
        GitHub Actions runners set several environment variables that can be used for detection.
        This avoids unnecessary worktree setup when running in CI where the workspace is already isolated.
    #>
    [CmdletBinding()]
    param()
    return $null -ne $env:GITHUB_ACTIONS
}

function Resolve-PRConflicts {
    [CmdletBinding()]
    param(
        [string]$Owner,
        [string]$Repo,
        [long]$PRNumber,  # ADR-015 Fix 4: Int64
        [string]$BranchName,
        [string]$TargetBranch = 'main'  # PR target branch (baseRefName)
    )

    # ADR-015 Fix 1: Validate branch name for command injection prevention
    if (-not (Test-SafeBranchName -BranchName $BranchName)) {
        Write-Log "Rejecting PR #$PRNumber due to unsafe branch name: $BranchName" -Level ERROR
        return $false
    }

    # Detect GitHub Actions runner - worktrees not needed there as workspace is already isolated
    $isGitHubRunner = Test-IsGitHubRunner

    if ($isGitHubRunner) {
        Write-Log "Running in GitHub Actions - using direct merge without worktree" -Level INFO

        try {
            # Fetch PR branch and target branch (P0 fix from PR #249: not hardcoded main)
            $null = git fetch origin $BranchName 2>&1
            if ($LASTEXITCODE -ne 0) {
                throw "Failed to fetch branch $BranchName"
            }
            $null = git fetch origin $TargetBranch 2>&1
            if ($LASTEXITCODE -ne 0) {
                throw "Failed to fetch target branch $TargetBranch"
            }

            # Checkout PR branch
            $null = git checkout $BranchName 2>&1
            if ($LASTEXITCODE -ne 0) {
                throw "Failed to checkout branch $BranchName"
            }

            # Attempt merge with target branch
            $mergeResult = git merge "origin/$TargetBranch" 2>&1

            if ($LASTEXITCODE -ne 0) {
                # Check if conflicts are in auto-resolvable files only
                $conflicts = git diff --name-only --diff-filter=U

                $canAutoResolve = $true
                foreach ($file in $conflicts) {
                    if ($file -eq '.agents/HANDOFF.md' -or $file -like '.agents/sessions/*') {
                        # Accept target branch's version (--theirs refers to the branch being merged FROM,
                        # which is origin/$TargetBranch when merging target into feature branch)
                        $null = git checkout --theirs $file 2>&1
                        if ($LASTEXITCODE -ne 0) {
                            throw "Failed to checkout --theirs for $file"
                        }
                        $null = git add $file 2>&1
                        if ($LASTEXITCODE -ne 0) {
                            throw "Failed to git add $file"
                        }
                    }
                    else {
                        $canAutoResolve = $false
                        Write-Log "Cannot auto-resolve conflict in: $file" -Level WARN
                    }
                }

                if (-not $canAutoResolve) {
                    $null = git merge --abort 2>&1
                    throw "Conflicts in non-auto-resolvable files"
                }

                # Check if there are staged changes to commit
                $null = git diff --cached --quiet 2>&1
                if ($LASTEXITCODE -eq 0) {
                    # No staged changes - merge was clean or already resolved
                    Write-Log "Merge completed without needing conflict resolution commit" -Level INFO
                }
                else {
                    # Complete merge with commit
                    $null = git commit -m "Merge $TargetBranch into $BranchName - auto-resolve HANDOFF.md conflicts" 2>&1
                    if ($LASTEXITCODE -ne 0) {
                        throw "Failed to commit merge"
                    }
                }
            }

            # Push (P1 fix from PR #249: check exit code to detect failures)
            $pushOutput = git push origin $BranchName 2>&1
            if ($LASTEXITCODE -ne 0) {
                throw "Git push failed: $pushOutput"
            }

            Write-Log "Successfully resolved conflicts for PR #$PRNumber" -Level SUCCESS
            return $true
        }
        catch {
            Write-Log "Failed to resolve conflicts for PR #${PRNumber}: $_" -Level ERROR
            return $false
        }
    }
    else {
        # Local execution - use worktree for isolation
        $repoRoot = git rev-parse --show-toplevel

        # ADR-015 Fix 2: Validate worktree path for path traversal prevention
        try {
            $worktreePath = Get-SafeWorktreePath -BasePath $script:Config.WorktreeBasePath -PRNumber $PRNumber
        }
        catch {
            Write-Log "Failed to get safe worktree path for PR #${PRNumber}: $_" -Level ERROR
            return $false
        }

        try {
            # Create worktree
            Write-Log "Creating worktree for PR #$PRNumber at $worktreePath" -Level ACTION
            $null = git worktree add $worktreePath $BranchName 2>&1
            if ($LASTEXITCODE -ne 0) {
                throw "Failed to create worktree for $BranchName"
            }

            Push-Location $worktreePath

            # Fetch and merge target branch (P0 fix from PR #249: not hardcoded main)
            $null = git fetch origin $TargetBranch 2>&1
            if ($LASTEXITCODE -ne 0) {
                throw "Failed to fetch target branch $TargetBranch"
            }
            $mergeResult = git merge "origin/$TargetBranch" 2>&1

            if ($LASTEXITCODE -ne 0) {
                # Check if conflicts are in auto-resolvable files only
                $conflicts = git diff --name-only --diff-filter=U

                $canAutoResolve = $true
                foreach ($file in $conflicts) {
                    if ($file -eq '.agents/HANDOFF.md' -or $file -like '.agents/sessions/*') {
                        # Accept target branch's version (--theirs refers to the branch being merged FROM,
                        # which is origin/$TargetBranch when merging target into feature branch)
                        $null = git checkout --theirs $file 2>&1
                        if ($LASTEXITCODE -ne 0) {
                            throw "Failed to checkout --theirs for $file"
                        }
                        $null = git add $file 2>&1
                        if ($LASTEXITCODE -ne 0) {
                            throw "Failed to git add $file"
                        }
                    }
                    else {
                        $canAutoResolve = $false
                        Write-Log "Cannot auto-resolve conflict in: $file" -Level WARN
                    }
                }

                if (-not $canAutoResolve) {
                    $null = git merge --abort 2>&1
                    throw "Conflicts in non-auto-resolvable files"
                }

                # Check if there are staged changes to commit
                $null = git diff --cached --quiet 2>&1
                if ($LASTEXITCODE -eq 0) {
                    # No staged changes - merge was clean or already resolved
                    Write-Log "Merge completed without needing conflict resolution commit" -Level INFO
                }
                else {
                    # Complete merge with commit
                    $null = git commit -m "Merge $TargetBranch into $BranchName - auto-resolve HANDOFF.md conflicts" 2>&1
                    if ($LASTEXITCODE -ne 0) {
                        throw "Failed to commit merge"
                    }
                }
            }

            # Push (P1 fix from PR #249: check exit code to detect failures)
            $pushOutput = git push origin $BranchName 2>&1
            if ($LASTEXITCODE -ne 0) {
                throw "Git push failed: $pushOutput"
            }

            Write-Log "Successfully resolved conflicts for PR #$PRNumber" -Level SUCCESS
            return $true
        }
        catch {
            Write-Log "Failed to resolve conflicts for PR #${PRNumber}: $_" -Level ERROR
            return $false
        }
        finally {
            Pop-Location -ErrorAction SilentlyContinue

            # Clean up worktree
            if (Test-Path $worktreePath) {
                git -C $repoRoot worktree remove $worktreePath --force 2>&1 | Out-Null
            }
        }
    }
}

function Get-SimilarPRs {
    <#
    .SYNOPSIS
        Finds merged PRs with similar titles to help identify potential duplicates.
    .DESCRIPTION
        Returns a list of recently merged PRs that have similar title patterns.
        Does not auto-close - just provides information for human review.
        Similar to CodeRabbit's approach on Issue enrichment.
    #>
    [CmdletBinding()]
    param(
        [string]$Owner,
        [string]$Repo,
        [int]$PRNumber,
        [string]$Title
    )

    # Check if there's a merged PR with very similar title
    $output = gh pr list --repo "$Owner/$Repo" --state merged --limit 20 --json number,title 2>&1
    if ($LASTEXITCODE -ne 0) {
        Write-Log "Failed to query merged PRs: $output" -Level WARN
        Write-Output -NoEnumerate @()
        return
    }

    # Skill-PowerShell-002: Ensure $mergedPRs is always array, not $null
    $parsed = $output | ConvertFrom-Json
    if ($null -eq $parsed) {
        Write-Output -NoEnumerate @()
        return
    }
    $mergedPRs = @($parsed)

    $similar = @()
    foreach ($merged in $mergedPRs) {
        if ($merged.number -eq $PRNumber) { continue }

        # Simple similarity check - same prefix up to first colon
        $thisPrefix = ($Title -split ':')[0]
        $mergedPrefix = ($merged.title -split ':')[0]

        # Two PRs are similar if they have the same type prefix (feat, fix, etc.)
        # AND one title contains a significant portion of the other (handles "v2" suffixes)
        if ($thisPrefix -eq $mergedPrefix) {
            # Extract the description part after the colon (if any)
            $thisDesc = if ($Title -match '^[^:]+:\s*(.+)$') { $Matches[1] } else { $Title }
            $mergedDesc = if ($merged.title -match '^[^:]+:\s*(.+)$') { $Matches[1] } else { $merged.title }

            # Check if descriptions are similar (one contains the other or share significant overlap)
            $minLen = [Math]::Min($thisDesc.Length, $mergedDesc.Length)
            $compareLen = [Math]::Max(10, [Math]::Min(30, $minLen))
            $thisCompare = $thisDesc.Substring(0, [Math]::Min($compareLen, $thisDesc.Length))
            $mergedCompare = $mergedDesc.Substring(0, [Math]::Min($compareLen, $mergedDesc.Length))

            if ($thisCompare -eq $mergedCompare -or $thisDesc -like "*$mergedCompare*" -or $mergedDesc -like "*$thisCompare*") {
                $similar += @{
                    Number = $merged.number
                    Title = $merged.title
                }
            }
        }
    }

    # Skill-PowerShell-002: Ensure return is always array, not $null
    if ($similar.Count -eq 0) {
        Write-Output -NoEnumerate @()
        return
    }
    Write-Output -NoEnumerate $similar
}

#endregion

#region Main Processing Logic

function Invoke-PRMaintenance {
    param(
        [string]$Owner,
        [string]$Repo,
        [int]$MaxPRs
    )

    $results = @{
        TotalPRs = 0
        Processed = 0
        CommentsAcknowledged = 0
        ConflictsResolved = 0
        Blocked = [System.Collections.ArrayList]::new()
        Errors = [System.Collections.ArrayList]::new()
    }

    Write-Log "Starting PR maintenance run" -Level INFO
    Write-Log "Repository: $Owner/$Repo" -Level INFO
    Write-Log "MaxPRs: $MaxPRs" -Level INFO

    # Get all open PRs
    $prs = Get-OpenPRs -Owner $Owner -Repo $Repo -Limit $MaxPRs
    $results.TotalPRs = $prs.Count
    Write-Log "Found $($prs.Count) open PRs" -Level INFO

    foreach ($pr in $prs) {
        Write-Log "Processing PR #$($pr.number): $($pr.title)" -Level INFO

        try {
            # Check if PR needs owner action (CHANGES_REQUESTED)
            if ($pr.reviewDecision -eq 'CHANGES_REQUESTED') {
                Write-Log "PR #$($pr.number) has CHANGES_REQUESTED - blocked" -Level WARN
                $null = $results.Blocked.Add(@{
                    PR = $pr.number
                    Reason = 'CHANGES_REQUESTED'
                    Title = $pr.title
                })
                continue
            }

            # Check for similar merged PRs (informational only - no auto-close)
            $similarPRs = Get-SimilarPRs -Owner $Owner -Repo $Repo -PRNumber $pr.number -Title $pr.title
            if ($similarPRs.Count -gt 0) {
                Write-Log "PR #$($pr.number) has similar merged PRs - review recommended:" -Level INFO
                foreach ($similar in $similarPRs) {
                    Write-Log "  - PR #$($similar.Number): $($similar.Title)" -Level INFO
                }
            }

            # Acknowledge unacknowledged bot comments
            $unacked = Get-UnacknowledgedComments -Owner $Owner -Repo $Repo -PRNumber $pr.number
            foreach ($comment in $unacked) {
                Write-Log "Acknowledging comment $($comment.id) from $($comment.user.login)" -Level ACTION
                $acked = Add-CommentReaction -Owner $Owner -Repo $Repo -CommentId $comment.id
                if ($acked) {
                    $results.CommentsAcknowledged++
                }
            }

            # Check and resolve merge conflicts
            if ($pr.mergeable -eq 'CONFLICTING') {
                Write-Log "PR #$($pr.number) has merge conflicts - attempting resolution" -Level ACTION
                $resolved = Resolve-PRConflicts -Owner $Owner -Repo $Repo -PRNumber $pr.number -BranchName $pr.headRefName -TargetBranch $pr.baseRefName
                if ($resolved) {
                    $results.ConflictsResolved++
                }
                else {
                    $null = $results.Blocked.Add(@{
                        PR = $pr.number
                        Reason = 'UNRESOLVABLE_CONFLICTS'
                        Title = $pr.title
                    })
                }
            }

            $results.Processed++
        }
        catch {
            Write-Log "Error processing PR #$($pr.number): $_" -Level ERROR
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
    # Script is being dot-sourced - functions are now available but don't execute main logic
    return
}

try {
    # ADR-015 Fix 3: Acquire script lock to prevent concurrent execution
    if (-not (Enter-ScriptLock)) {
        Write-Log "Exiting: another instance is running" -Level WARN
        exit 0
    }

    try {
        # ADR-015 Fix 6: Check API rate limit before processing (multi-resource)
        if (-not (Test-RateLimitSafe)) {
            Write-Log "Exiting: API rate limit too low" -Level WARN
            exit 0
        }

        # Resolve repo info
        if (-not $Owner -or -not $Repo) {
            $repoInfo = Get-RepoInfo
            if (-not $Owner) { $Owner = $repoInfo.Owner }
            if (-not $Repo) { $Repo = $repoInfo.Repo }
        }

        # Safety check: ensure we're not on a protected branch (unless in CI)
        # In GitHub Actions scheduled runs, we checkout main but only READ PR data via API
        $currentBranch = git branch --show-current
        $isCI = $env:GITHUB_ACTIONS -eq 'true'
        if ($currentBranch -in $script:Config.ProtectedBranches -and -not $isCI) {
            Write-Log "ERROR: Cannot run on protected branch '$currentBranch' outside CI" -Level ERROR
            exit 2
        }
        if ($currentBranch -in $script:Config.ProtectedBranches -and $isCI) {
            Write-Log "Running on protected branch '$currentBranch' in CI mode (read-only operations via API)" -Level INFO
        }

        # Run maintenance
        $results = Invoke-PRMaintenance -Owner $Owner -Repo $Repo -MaxPRs $MaxPRs

        # Summary
        Write-Log "---" -Level INFO
        Write-Log "=== PR Maintenance Summary ===" -Level INFO
        Write-Log "PRs Processed: $($results.Processed)" -Level INFO
        Write-Log "Comments Acknowledged: $($results.CommentsAcknowledged)" -Level SUCCESS
        Write-Log "Conflicts Resolved: $($results.ConflictsResolved)" -Level SUCCESS

        if ($results.Blocked.Count -gt 0) {
            Write-Log "---" -Level INFO
            Write-Log "Blocked PRs (require human action):" -Level WARN
            foreach ($blocked in $results.Blocked) {
                Write-Log "  PR #$($blocked.PR): $($blocked.Reason) - $($blocked.Title)" -Level WARN
            }
        }

        if ($results.Errors.Count -gt 0) {
            Write-Log "---" -Level INFO
            Write-Log "Errors:" -Level ERROR
            foreach ($err in $results.Errors) {
                Write-Log "  PR #$($err.PR): $($err.Error)" -Level ERROR
            }
        }

        $duration = (Get-Date) - $script:StartTime
        Write-Log "---" -Level INFO
        Write-Log "Completed in $([math]::Round($duration.TotalSeconds, 1)) seconds" -Level INFO

        # Write GitHub Actions step summary for visibility (Issue #400)
        if ($env:GITHUB_STEP_SUMMARY) {
            $actionsCount = $results.CommentsAcknowledged + $results.ConflictsResolved
            $summary = @"
## PR Maintenance Summary

| Metric | Count |
|--------|-------|
| Open PRs Scanned | $($results.TotalPRs) |
| PRs Processed | $($results.Processed) |
| Comments Acknowledged | $($results.CommentsAcknowledged) |
| Conflicts Resolved | $($results.ConflictsResolved) |
| Blocked (needs human) | $($results.Blocked.Count) |
| Errors | $($results.Errors.Count) |

"@
            # Explain why 0 actions might have been taken
            if ($actionsCount -eq 0 -and $results.TotalPRs -gt 0) {
                $summary += @"
### Why No Actions Taken?

All $($results.TotalPRs) open PRs were scanned but none required automated action:
- No unacknowledged bot comments found
- No merge conflicts to resolve
- $($results.Blocked.Count) PR(s) blocked with CHANGES_REQUESTED

This is normal when PRs are awaiting human review or have no pending bot feedback.
"@
            }
            elseif ($results.TotalPRs -eq 0) {
                $summary += @"
### No Open PRs

No open pull requests found in the repository.
"@
            }

            $summary | Out-File $env:GITHUB_STEP_SUMMARY -Append
        }

        # Save log
        Save-Log -Path $LogPath

        # Determine exit code
        # Exit code 0: Success (PRs processed, even if some are blocked)
        # Exit code 1: Reserved for future use
        # Exit code 2: Fatal errors (script failure, API errors)
        # 
        # Note: Blocked PRs (CHANGES_REQUESTED) are not errors - they're
        # reported via summary and trigger a separate alert issue.
        # The workflow should only fail on actual errors.
        $exitCode = 0
        if ($results.Errors.Count -gt 0) {
            $exitCode = 2
        }
        # Removed: elseif ($results.Blocked.Count -gt 0) { $exitCode = 1 }
        # Blocked PRs are handled by the "Create alert issue for blocked PRs" step
    }
    finally {
        # ADR-015 Fix 3: Always release lock in finally block
        Exit-ScriptLock
    }

    exit $exitCode
}
catch {
    Write-Log "Fatal error: $_" -Level ERROR
    Write-Log $_.ScriptStackTrace -Level ERROR
    Save-Log -Path $LogPath

    # ADR-015 Fix 3: Release lock on fatal error
    Exit-ScriptLock
    exit 2
}

#endregion
