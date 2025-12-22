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

.PARAMETER DryRun
    If specified, only report what would be done without making changes.

.PARAMETER MaxPRs
    Maximum number of PRs to process in one run. Defaults to 20.

.PARAMETER LogPath
    Path to write detailed log file. Defaults to .agents/logs/pr-maintenance.log

.EXAMPLE
    .\scripts\Invoke-PRMaintenance.ps1

.EXAMPLE
    .\scripts\Invoke-PRMaintenance.ps1 -DryRun

.EXAMPLE
    .\scripts\Invoke-PRMaintenance.ps1 -MaxPRs 5

.NOTES
    Exit Codes:
    0 = Success (all actionable items processed)
    1 = Partial success (some items processed, some blocked)
    2 = Error (script failure)
#>

[CmdletBinding()]
param(
    [string]$Owner,
    [string]$Repo,
    [switch]$DryRun,
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

#region Logging

$script:LogEntries = [System.Collections.ArrayList]::new()
$script:StartTime = Get-Date

function Write-Log {
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
    param(
        [string]$Owner,
        [string]$Repo,
        [int]$Limit
    )

    $jq = '.[] | {number, title, state, head: .headRefName, base: .baseRefName, mergeable: .mergeable, reviewDecision: .reviewDecision, author: .author.login}'

    $result = gh pr list --repo "$Owner/$Repo" --state open --limit $Limit --json number,title,state,headRefName,baseRefName,mergeable,reviewDecision,author 2>&1

    if ($LASTEXITCODE -ne 0) {
        throw "Failed to list PRs: $result"
    }

    return $result | ConvertFrom-Json
}

function Get-PRComments {
    param(
        [string]$Owner,
        [string]$Repo,
        [int]$PRNumber
    )

    $endpoint = "repos/$Owner/$Repo/pulls/$PRNumber/comments"
    $result = Invoke-GhApi -Endpoint $endpoint

    return $result | ConvertFrom-Json
}

function Get-UnacknowledgedComments {
    param(
        [string]$Owner,
        [string]$Repo,
        [int]$PRNumber
    )

    $comments = Get-PRComments -Owner $Owner -Repo $Repo -PRNumber $PRNumber

    $unacked = $comments | Where-Object {
        $_.user.type -eq 'Bot' -and
        $_.reactions.eyes -eq 0
    }

    return $unacked
}

function Add-CommentReaction {
    param(
        [string]$Owner,
        [string]$Repo,
        [int]$CommentId,
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
    param(
        [string]$Owner,
        [string]$Repo,
        [int]$PRNumber
    )

    $pr = gh pr view $PRNumber --repo "$Owner/$Repo" --json mergeable --jq '.mergeable' 2>&1
    return $pr -eq 'CONFLICTING'
}

function Test-PRNeedsOwnerAction {
    param(
        [string]$Owner,
        [string]$Repo,
        [int]$PRNumber
    )

    $pr = gh pr view $PRNumber --repo "$Owner/$Repo" --json reviewDecision --jq '.reviewDecision' 2>&1
    return $pr -eq 'CHANGES_REQUESTED'
}

function Resolve-PRConflicts {
    param(
        [string]$Owner,
        [string]$Repo,
        [int]$PRNumber,
        [string]$BranchName,
        [switch]$DryRun
    )

    if ($DryRun) {
        Write-Log "[DRY RUN] Would resolve conflicts for PR #$PRNumber" -Level ACTION
        return $true
    }

    $repoRoot = git rev-parse --show-toplevel
    $worktreePath = Join-Path $script:Config.WorktreeBasePath "ai-agents-pr-$PRNumber"

    try {
        # Create worktree
        Write-Log "Creating worktree for PR #$PRNumber at $worktreePath" -Level ACTION
        git worktree add $worktreePath $BranchName 2>&1 | Out-Null

        Push-Location $worktreePath

        # Fetch and merge main
        git fetch origin main 2>&1 | Out-Null
        $mergeResult = git merge origin/main 2>&1

        if ($LASTEXITCODE -ne 0) {
            # Check if conflicts are in HANDOFF.md only (accept theirs)
            $conflicts = git diff --name-only --diff-filter=U

            $canAutoResolve = $true
            foreach ($file in $conflicts) {
                if ($file -eq '.agents/HANDOFF.md' -or $file -like '.agents/sessions/*') {
                    # Accept main's version for these files
                    git checkout --theirs $file 2>&1 | Out-Null
                    git add $file 2>&1 | Out-Null
                }
                else {
                    $canAutoResolve = $false
                    Write-Log "Cannot auto-resolve conflict in: $file" -Level WARN
                }
            }

            if (-not $canAutoResolve) {
                git merge --abort 2>&1 | Out-Null
                throw "Conflicts in non-auto-resolvable files"
            }

            # Complete merge
            git commit -m "Merge main into $BranchName - auto-resolve HANDOFF.md conflicts" 2>&1 | Out-Null
        }

        # Push
        git push origin $BranchName 2>&1 | Out-Null

        Write-Log "Successfully resolved conflicts for PR #$PRNumber" -Level SUCCESS
        return $true
    }
    catch {
        Write-Log "Failed to resolve conflicts for PR #$PRNumber`: $_" -Level ERROR
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

function Test-PRSuperseded {
    param(
        [string]$Owner,
        [string]$Repo,
        [int]$PRNumber,
        [string]$Title
    )

    # Check if there's a merged PR with very similar title
    $mergedPRs = gh pr list --repo "$Owner/$Repo" --state merged --limit 20 --json number,title 2>&1 | ConvertFrom-Json

    foreach ($merged in $mergedPRs) {
        if ($merged.number -eq $PRNumber) { continue }

        # Simple similarity check - same prefix up to first colon
        $thisPrefix = ($Title -split ':')[0]
        $mergedPrefix = ($merged.title -split ':')[0]

        if ($thisPrefix -eq $mergedPrefix -and $Title -like "*$($merged.title.Substring(0, [Math]::Min(30, $merged.title.Length)))*") {
            return @{
                Superseded = $true
                SupersededBy = $merged.number
            }
        }
    }

    return @{ Superseded = $false }
}

function Close-SupersededPR {
    param(
        [string]$Owner,
        [string]$Repo,
        [int]$PRNumber,
        [int]$SupersededBy,
        [switch]$DryRun
    )

    if ($DryRun) {
        Write-Log "[DRY RUN] Would close PR #$PRNumber as superseded by #$SupersededBy" -Level ACTION
        return $true
    }

    try {
        gh pr comment $PRNumber --repo "$Owner/$Repo" --body "Closing as superseded by PR #$SupersededBy which has been merged." 2>&1 | Out-Null
        gh pr close $PRNumber --repo "$Owner/$Repo" 2>&1 | Out-Null
        Write-Log "Closed PR #$PRNumber as superseded by #$SupersededBy" -Level SUCCESS
        return $true
    }
    catch {
        Write-Log "Failed to close PR #$PRNumber`: $_" -Level ERROR
        return $false
    }
}

#endregion

#region Main Processing Logic

function Invoke-PRMaintenance {
    param(
        [string]$Owner,
        [string]$Repo,
        [switch]$DryRun,
        [int]$MaxPRs
    )

    $results = @{
        Processed = 0
        CommentsAcknowledged = 0
        ConflictsResolved = 0
        PRsClosed = 0
        Blocked = [System.Collections.ArrayList]::new()
        Errors = [System.Collections.ArrayList]::new()
    }

    Write-Log "Starting PR maintenance run" -Level INFO
    Write-Log "Repository: $Owner/$Repo" -Level INFO
    Write-Log "DryRun: $DryRun" -Level INFO
    Write-Log "MaxPRs: $MaxPRs" -Level INFO

    # Get all open PRs
    $prs = Get-OpenPRs -Owner $Owner -Repo $Repo -Limit $MaxPRs
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

            # Check if PR is superseded by a merged PR
            $superseded = Test-PRSuperseded -Owner $Owner -Repo $Repo -PRNumber $pr.number -Title $pr.title
            if ($superseded.Superseded) {
                $closed = Close-SupersededPR -Owner $Owner -Repo $Repo -PRNumber $pr.number -SupersededBy $superseded.SupersededBy -DryRun:$DryRun
                if ($closed) {
                    $results.PRsClosed++
                }
                continue
            }

            # Acknowledge unacknowledged bot comments
            $unacked = Get-UnacknowledgedComments -Owner $Owner -Repo $Repo -PRNumber $pr.number
            foreach ($comment in $unacked) {
                Write-Log "Acknowledging comment $($comment.id) from $($comment.user.login)" -Level ACTION
                if (-not $DryRun) {
                    $acked = Add-CommentReaction -Owner $Owner -Repo $Repo -CommentId $comment.id
                    if ($acked) {
                        $results.CommentsAcknowledged++
                    }
                }
                else {
                    Write-Log "[DRY RUN] Would acknowledge comment $($comment.id)" -Level ACTION
                    $results.CommentsAcknowledged++
                }
            }

            # Check and resolve merge conflicts
            if ($pr.mergeable -eq 'CONFLICTING') {
                Write-Log "PR #$($pr.number) has merge conflicts - attempting resolution" -Level ACTION
                $resolved = Resolve-PRConflicts -Owner $Owner -Repo $Repo -PRNumber $pr.number -BranchName $pr.head -DryRun:$DryRun
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

try {
    # Resolve repo info
    if (-not $Owner -or -not $Repo) {
        $repoInfo = Get-RepoInfo
        if (-not $Owner) { $Owner = $repoInfo.Owner }
        if (-not $Repo) { $Repo = $repoInfo.Repo }
    }

    # Safety check: ensure we're not on a protected branch
    $currentBranch = git branch --show-current
    if ($currentBranch -in $script:Config.ProtectedBranches) {
        Write-Log "ERROR: Cannot run on protected branch '$currentBranch'" -Level ERROR
        exit 2
    }

    # Run maintenance
    $results = Invoke-PRMaintenance -Owner $Owner -Repo $Repo -DryRun:$DryRun -MaxPRs $MaxPRs

    # Summary
    Write-Log "" -Level INFO
    Write-Log "=== PR Maintenance Summary ===" -Level INFO
    Write-Log "PRs Processed: $($results.Processed)" -Level INFO
    Write-Log "Comments Acknowledged: $($results.CommentsAcknowledged)" -Level SUCCESS
    Write-Log "Conflicts Resolved: $($results.ConflictsResolved)" -Level SUCCESS
    Write-Log "PRs Closed (Superseded): $($results.PRsClosed)" -Level SUCCESS

    if ($results.Blocked.Count -gt 0) {
        Write-Log "" -Level INFO
        Write-Log "Blocked PRs (require human action):" -Level WARN
        foreach ($blocked in $results.Blocked) {
            Write-Log "  PR #$($blocked.PR): $($blocked.Reason) - $($blocked.Title)" -Level WARN
        }
    }

    if ($results.Errors.Count -gt 0) {
        Write-Log "" -Level INFO
        Write-Log "Errors:" -Level ERROR
        foreach ($err in $results.Errors) {
            Write-Log "  PR #$($err.PR): $($err.Error)" -Level ERROR
        }
    }

    $duration = (Get-Date) - $script:StartTime
    Write-Log "" -Level INFO
    Write-Log "Completed in $([math]::Round($duration.TotalSeconds, 1)) seconds" -Level INFO

    # Save log
    Save-Log -Path $LogPath

    # Exit code
    if ($results.Errors.Count -gt 0) {
        exit 2
    }
    elseif ($results.Blocked.Count -gt 0) {
        exit 1
    }
    else {
        exit 0
    }
}
catch {
    Write-Log "Fatal error: $_" -Level ERROR
    Write-Log $_.ScriptStackTrace -Level ERROR
    Save-Log -Path $LogPath
    exit 2
}

#endregion
