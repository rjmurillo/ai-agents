<#
.SYNOPSIS
    Manages git worktrees for batch PR review operations.

.DESCRIPTION
    Creates, monitors, and cleans up git worktrees for parallel PR review processing.
    Designed to work with the /pr-review Claude command.

.PARAMETER PRNumbers
    Array of PR numbers to process.

.PARAMETER Operation
    Operation to perform: Setup, Status, Cleanup, or All.

.PARAMETER WorktreeRoot
    Root directory for worktrees. Defaults to parent of current repo.

.PARAMETER Force
    Force cleanup even if worktrees have uncommitted changes.

.EXAMPLE
    .\Invoke-BatchPRReview.ps1 -PRNumbers 53,141,143 -Operation Setup

.EXAMPLE
    .\Invoke-BatchPRReview.ps1 -PRNumbers 53,141,143 -Operation Status

.EXAMPLE
    .\Invoke-BatchPRReview.ps1 -PRNumbers 53,141,143 -Operation Cleanup

.NOTES
    EXIT CODES:
    0  - Success: Worktree operation completed
    1  - Error: Operation failed

    See: ADR-035 Exit Code Standardization
#>

[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [int[]]$PRNumbers,

    [Parameter(Mandatory = $true)]
    [ValidateSet('Setup', 'Status', 'Cleanup', 'All')]
    [string]$Operation,

    [Parameter()]
    [string]$WorktreeRoot,

    [Parameter()]
    [switch]$Force
)

$ErrorActionPreference = 'Stop'

# Determine worktree root
if (-not $WorktreeRoot) {
    $repoRoot = git rev-parse --show-toplevel 2>$null
    if (-not $repoRoot) {
        Write-Error "Not in a git repository"
        exit 1
    }
    $WorktreeRoot = Split-Path $repoRoot -Parent
}

function Get-PRBranch {
    param([int]$PRNumber)

    $rawOutput = gh pr view $PRNumber --json headRefName 2>&1
    if ($LASTEXITCODE -ne 0) {
        Write-Warning ("PR #$PRNumber not found or not accessible. " +
                       "Verify that the PR number is correct, that you are in the correct repository, " +
                       "and that the GitHub CLI is authenticated with sufficient permissions (try 'gh auth status').")
        return $null
    }
    $prInfo = $rawOutput | ConvertFrom-Json
    if (-not $prInfo -or -not $prInfo.headRefName) {
        Write-Warning "PR #${PRNumber}: Unable to parse branch information."
        return $null
    }
    return $prInfo.headRefName
}

function New-PRWorktree {
    param([int]$PRNumber)

    $branch = Get-PRBranch -PRNumber $PRNumber
    if (-not $branch) { return $false }

    $worktreePath = Join-Path $WorktreeRoot "worktree-pr-$PRNumber"

    if (Test-Path $worktreePath) {
        Write-Host "Worktree already exists: $worktreePath" -ForegroundColor Yellow
        return $true
    }

    # Fetch the branch from remote to ensure we have the latest
    # This is equivalent to what 'gh pr checkout' does internally
    Write-Host "PR #${PRNumber}: Fetching branch '$branch' from origin..." -ForegroundColor Cyan
    git fetch origin "${branch}:${branch}" 2>&1 | Out-Null

    # If fetch fails (branch doesn't exist locally), try fetching without creating local branch
    if ($LASTEXITCODE -ne 0) {
        Write-Host "PR #${PRNumber}: Branch not found locally, fetching from remote..." -ForegroundColor Yellow
        git fetch origin $branch 2>&1 | Out-Null
    }

    Write-Host "PR #${PRNumber}: Creating worktree on branch '$branch'..." -ForegroundColor Cyan
    git worktree add $worktreePath $branch 2>&1

    if ($LASTEXITCODE -ne 0) {
        # Try with origin/ prefix if direct branch reference failed
        Write-Host "PR #${PRNumber}: Retrying with origin/${branch}..." -ForegroundColor Yellow
        git worktree add $worktreePath "origin/${branch}" 2>&1

        if ($LASTEXITCODE -ne 0) {
            Write-Warning "Failed to create worktree for PR #$PRNumber. Continuing with remaining PRs."
            return $false
        }
    }

    Write-Host "Created: $worktreePath" -ForegroundColor Green
    return $true
}

function Get-WorktreeStatus {
    param([int]$PRNumber)

    $worktreePath = Join-Path $WorktreeRoot "worktree-pr-$PRNumber"

    if (-not (Test-Path $worktreePath)) {
        return [PSCustomObject]@{
            PR         = $PRNumber
            Path       = $worktreePath
            Exists     = $false
            Clean      = $null
            Branch     = $null
            Commit     = $null
            Unpushed   = $null
        }
    }

    Push-Location $worktreePath
    try {
        $status = git status --short 2>$null
        $branch = git branch --show-current 2>$null
        $commit = git log -1 --format='%h' 2>$null
        # Check if upstream exists before querying unpushed commits
        $hasUpstream = git rev-parse --abbrev-ref '@{u}' 2>$null
        $unpushed = if ($LASTEXITCODE -eq 0 -and $hasUpstream) {
            git log "@{u}.." --oneline 2>$null
        } else {
            $null
        }

        return [PSCustomObject]@{
            PR         = $PRNumber
            Path       = $worktreePath
            Exists     = $true
            Clean      = [string]::IsNullOrWhiteSpace($status)
            Branch     = $branch
            Commit     = $commit
            Unpushed   = -not [string]::IsNullOrWhiteSpace($unpushed)
        }
    }
    finally {
        Pop-Location
    }
}

function Remove-PRWorktree {
    param(
        [int]$PRNumber,
        [switch]$Force
    )

    $status = Get-WorktreeStatus -PRNumber $PRNumber

    if (-not $status.Exists) {
        Write-Host "Worktree for PR #$PRNumber does not exist" -ForegroundColor Yellow
        return $true
    }

    if (-not $status.Clean -and -not $Force) {
        Write-Warning "Worktree for PR #$PRNumber has uncommitted changes. Use -Force to remove anyway."
        return $false
    }

    if ($status.Unpushed -and -not $Force) {
        Write-Warning "Worktree for PR #$PRNumber has unpushed commits. Use -Force to remove anyway."
        return $false
    }

    Write-Host "Removing worktree for PR #$PRNumber..." -ForegroundColor Cyan

    $removeArgs = @('worktree', 'remove', $status.Path)
    if ($Force) { $removeArgs += '--force' }

    $output = git @removeArgs 2>&1

    if ($LASTEXITCODE -ne 0) {
        Write-Warning "Failed to remove worktree for PR #$PRNumber. Error: $output. Continuing with remaining PRs."
        return $false
    }

    Write-Host "Removed: $($status.Path)" -ForegroundColor Green
    return $true
}

function Push-WorktreeChanges {
    param([int]$PRNumber)

    $status = Get-WorktreeStatus -PRNumber $PRNumber

    if (-not $status.Exists) {
        Write-Warning "Worktree for PR #$PRNumber does not exist"
        return $false
    }

    if ($status.Clean -and -not $status.Unpushed) {
        Write-Host "PR #${PRNumber}: Already clean and pushed" -ForegroundColor Green
        return $true
    }

    Push-Location $status.Path
    try {
        if (-not $status.Clean) {
            Write-Host "PR #${PRNumber}: Committing changes..." -ForegroundColor Cyan
            git add .
            if ($LASTEXITCODE -ne 0) {
                throw "PR #${PRNumber}: 'git add .' failed with exit code $LASTEXITCODE"
            }
            git commit -m "chore(pr-$PRNumber): finalize review response session"
            if ($LASTEXITCODE -ne 0) {
                throw "PR #${PRNumber}: 'git commit' failed with exit code $LASTEXITCODE"
            }
        }

        if ($status.Unpushed -or -not $status.Clean) {
            Write-Host "PR #${PRNumber}: Pushing to remote..." -ForegroundColor Cyan
            git push
            if ($LASTEXITCODE -ne 0) {
                throw "PR #${PRNumber}: 'git push' failed with exit code $LASTEXITCODE"
            }
        }

        Write-Host "PR #${PRNumber}: Synced" -ForegroundColor Green
        return $true
    }
    catch {
        Write-Warning "PR #${PRNumber}: Failed to sync - $_. Continuing with remaining PRs."
        return $false
    }
    finally {
        Pop-Location
    }
}

# Main execution
switch ($Operation) {
    'Setup' {
        Write-Host "`n=== Setting up worktrees for PRs: $($PRNumbers -join ', ') ===" -ForegroundColor Magenta
        $results = @()
        foreach ($pr in $PRNumbers) {
            $success = New-PRWorktree -PRNumber $pr
            $results += [PSCustomObject]@{ PR = $pr; Success = $success }
        }
        $results | Format-Table -AutoSize
    }

    'Status' {
        Write-Host "`n=== Worktree Status ===" -ForegroundColor Magenta
        $statuses = foreach ($pr in $PRNumbers) {
            Get-WorktreeStatus -PRNumber $pr
        }
        $statuses | Format-Table PR, Exists, Clean, Branch, Commit, Unpushed -AutoSize
    }

    'Cleanup' {
        Write-Host "`n=== Cleaning up worktrees ===" -ForegroundColor Magenta

        # First push any changes
        foreach ($pr in $PRNumbers) {
            Push-WorktreeChanges -PRNumber $pr | Out-Null
        }

        # Then remove worktrees
        foreach ($pr in $PRNumbers) {
            Remove-PRWorktree -PRNumber $pr -Force:$Force | Out-Null
        }

        # Final status
        Write-Host "`n=== Remaining worktrees ===" -ForegroundColor Magenta
        git worktree list
    }

    'All' {
        # Setup
        Write-Host "`n=== Phase 1: Setting up worktrees ===" -ForegroundColor Magenta
        foreach ($pr in $PRNumbers) {
            New-PRWorktree -PRNumber $pr | Out-Null
        }

        # Status
        Write-Host "`n=== Phase 2: Initial Status ===" -ForegroundColor Magenta
        $statuses = foreach ($pr in $PRNumbers) {
            Get-WorktreeStatus -PRNumber $pr
        }
        $statuses | Format-Table PR, Exists, Clean, Branch, Commit -AutoSize

        Write-Host "`n=== Ready for parallel PR review ===" -ForegroundColor Green
        Write-Host "Worktrees created at: $WorktreeRoot" -ForegroundColor Cyan
        Write-Host "`nRun pr-comment-responder for each PR, then use -Operation Cleanup" -ForegroundColor Yellow
    }
}
