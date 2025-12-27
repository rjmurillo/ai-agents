#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Resolves merge conflicts for a PR branch with auto-resolution support.

.DESCRIPTION
    Extracted from Invoke-PRMaintenance.ps1 to be reusable by merge-resolver skill.

    Features:
    - Security validation for branch names and paths
    - Auto-resolves conflicts in HANDOFF.md and session files
    - Handles both GitHub Actions runner and local worktree environments
    - Pushes resolved branch on success

.PARAMETER Owner
    Repository owner. Auto-detected from git remote if not specified.

.PARAMETER Repo
    Repository name. Auto-detected from git remote if not specified.

.PARAMETER PRNumber
    Pull request number.

.PARAMETER BranchName
    Branch name to resolve conflicts for (headRefName).

.PARAMETER TargetBranch
    Target branch to merge from (baseRefName). Defaults to 'main'.

.PARAMETER WorktreeBasePath
    Base path for worktrees when running locally. Defaults to parent of repo.

.PARAMETER DryRun
    If specified, show what would be done without making changes.

.OUTPUTS
    PSCustomObject with:
    - Success: [bool] Whether resolution succeeded
    - Message: [string] Human-readable result
    - FilesResolved: [string[]] List of auto-resolved files
    - FilesBlocked: [string[]] Files that blocked auto-resolution

.EXAMPLE
    ./Resolve-PRConflicts.ps1 -PRNumber 123 -BranchName "fix/my-feature" -TargetBranch "main"

.NOTES
    Auto-resolvable files (accept theirs):
    - .agents/HANDOFF.md
    - .agents/sessions/*

    Security: ADR-015 compliance for branch name and path validation.
#>

[CmdletBinding()]
param(
    [string]$Owner,
    [string]$Repo,
    [Parameter(Mandatory)]
    [long]$PRNumber,
    [Parameter(Mandatory)]
    [string]$BranchName,
    [string]$TargetBranch = 'main',
    [string]$WorktreeBasePath = '..',
    [switch]$DryRun
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

#region Configuration

# Files that can be auto-resolved by accepting target branch (main) version
# These are typically auto-generated or frequently-updated files where
# the main branch version is authoritative
$script:AutoResolvableFiles = @(
    # Session artifacts - constantly changing, main is authoritative
    '.agents/HANDOFF.md',
    '.agents/sessions/*',
    '.agents/*',  # All .agents subdirectories
    # Serena memories - auto-generated, main is authoritative
    '.serena/memories/*',
    '.serena/*',  # All Serena files
    # Lock files - should match main
    'package-lock.json',
    'pnpm-lock.yaml',
    'yarn.lock',
    # Skill definitions - main is authoritative
    '.claude/skills/*',
    '.claude/skills/*/*',
    '.claude/skills/*/*/*',
    '.claude/commands/*',
    '.claude/agents/*',
    # Template files - main is authoritative (include subdirectories)
    'templates/*',
    'templates/*/*',
    'templates/*/*/*',
    # Platform-specific agent definitions - main is authoritative
    'src/copilot-cli/*',
    'src/vs-code-agents/*',
    'src/claude/*',
    # GitHub configs - main is authoritative
    '.github/agents/*',
    '.github/prompts/*'
)

#endregion

#region Security Validation (ADR-015)

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
        Write-Warning "Invalid branch name: empty or whitespace"
        return $false
    }

    # Starts with hyphen (could be interpreted as git option)
    if ($BranchName.StartsWith('-')) {
        Write-Warning "Invalid branch name: starts with hyphen"
        return $false
    }

    # Contains path traversal
    if ($BranchName.Contains('..')) {
        Write-Warning "Invalid branch name: contains path traversal"
        return $false
    }

    # Control characters
    if ($BranchName -match '[\x00-\x1f\x7f]') {
        Write-Warning "Invalid branch name: contains control characters"
        return $false
    }

    # Git special characters that could cause issues
    if ($BranchName -match '[~^:?*\[\]\\]') {
        Write-Warning "Invalid branch name: contains git special characters"
        return $false
    }

    # Shell metacharacters
    if ($BranchName -match '[`$;&|<>(){}]') {
        Write-Warning "Invalid branch name: contains shell metacharacters"
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

#endregion

#region Helpers

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

function Test-IsGitHubRunner {
    [CmdletBinding()]
    param()
    return $null -ne $env:GITHUB_ACTIONS
}

function Test-IsAutoResolvable {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)]
        [string]$FilePath
    )

    foreach ($pattern in $script:AutoResolvableFiles) {
        if ($FilePath -eq $pattern -or $FilePath -like $pattern) {
            return $true
        }
    }
    return $false
}

#endregion

#region Main Logic

function Resolve-PRConflicts {
    [CmdletBinding()]
    param(
        [string]$Owner,
        [string]$Repo,
        [long]$PRNumber,
        [string]$BranchName,
        [string]$TargetBranch = 'main',
        [string]$WorktreeBasePath = '..',
        [switch]$DryRun
    )

    $result = [PSCustomObject]@{
        Success = $false
        Message = ''
        FilesResolved = @()
        FilesBlocked = @()
    }

    # Validate branch names for command injection prevention
    if (-not (Test-SafeBranchName -BranchName $BranchName)) {
        $result.Message = "Rejecting PR #$PRNumber due to unsafe branch name: $BranchName"
        Write-Error $result.Message
        return $result
    }
    if (-not (Test-SafeBranchName -BranchName $TargetBranch)) {
        $result.Message = "Rejecting PR #$PRNumber due to unsafe target branch name: $TargetBranch"
        Write-Error $result.Message
        return $result
    }

    # Detect GitHub Actions runner - worktrees not needed there
    $isGitHubRunner = Test-IsGitHubRunner

    if ($isGitHubRunner) {
        Write-Host "Running in GitHub Actions - using direct merge without worktree" -ForegroundColor Cyan

        if ($DryRun) {
            $result.Message = "[DRY-RUN] Would resolve conflicts for PR #$PRNumber in GitHub runner mode"
            $result.Success = $true
            return $result
        }

        try {
            # Fetch PR branch and target branch
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
                    if (Test-IsAutoResolvable -FilePath $file) {
                        # Accept target branch's version
                        $null = git checkout --theirs $file 2>&1
                        if ($LASTEXITCODE -ne 0) {
                            throw "Failed to checkout --theirs for $file"
                        }
                        $null = git add $file 2>&1
                        if ($LASTEXITCODE -ne 0) {
                            throw "Failed to git add $file"
                        }
                        $result.FilesResolved += $file
                    }
                    else {
                        $canAutoResolve = $false
                        $result.FilesBlocked += $file
                        Write-Warning "Cannot auto-resolve conflict in: $file"
                    }
                }

                if (-not $canAutoResolve) {
                    $null = git merge --abort 2>&1
                    $result.Message = "Conflicts in non-auto-resolvable files: $($result.FilesBlocked -join ', ')"
                    return $result
                }

                # Check if there are staged changes to commit
                $null = git diff --cached --quiet 2>&1
                if ($LASTEXITCODE -eq 0) {
                    Write-Host "Merge completed without needing conflict resolution commit" -ForegroundColor Gray
                }
                else {
                    # Complete merge with commit
                    $null = git commit -m "Merge $TargetBranch into $BranchName - auto-resolve HANDOFF.md conflicts" 2>&1
                    if ($LASTEXITCODE -ne 0) {
                        throw "Failed to commit merge"
                    }
                }
            }

            # Push
            $pushOutput = git push origin $BranchName 2>&1
            if ($LASTEXITCODE -ne 0) {
                throw "Git push failed: $pushOutput"
            }

            $result.Success = $true
            $result.Message = "Successfully resolved conflicts for PR #$PRNumber"
            Write-Host $result.Message -ForegroundColor Green
            return $result
        }
        catch {
            $result.Message = "Failed to resolve conflicts for PR #${PRNumber}: $_"
            Write-Error $result.Message
            return $result
        }
    }
    else {
        # Local execution - use worktree for isolation
        $repoRoot = git rev-parse --show-toplevel

        # Validate worktree path for path traversal prevention
        try {
            $worktreePath = Get-SafeWorktreePath -BasePath $WorktreeBasePath -PRNumber $PRNumber
        }
        catch {
            $result.Message = "Failed to get safe worktree path for PR #${PRNumber}: $_"
            Write-Error $result.Message
            return $result
        }

        if ($DryRun) {
            $result.Message = "[DRY-RUN] Would create worktree at $worktreePath and resolve conflicts for PR #$PRNumber"
            $result.Success = $true
            return $result
        }

        try {
            # Create worktree
            Write-Host "Creating worktree for PR #$PRNumber at $worktreePath" -ForegroundColor Cyan
            $null = git worktree add $worktreePath $BranchName 2>&1
            if ($LASTEXITCODE -ne 0) {
                throw "Failed to create worktree for $BranchName"
            }

            Push-Location $worktreePath

            # Fetch and merge target branch
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
                    if (Test-IsAutoResolvable -FilePath $file) {
                        # Accept target branch's version
                        $null = git checkout --theirs $file 2>&1
                        if ($LASTEXITCODE -ne 0) {
                            throw "Failed to checkout --theirs for $file"
                        }
                        $null = git add $file 2>&1
                        if ($LASTEXITCODE -ne 0) {
                            throw "Failed to git add $file"
                        }
                        $result.FilesResolved += $file
                    }
                    else {
                        $canAutoResolve = $false
                        $result.FilesBlocked += $file
                        Write-Warning "Cannot auto-resolve conflict in: $file"
                    }
                }

                if (-not $canAutoResolve) {
                    $null = git merge --abort 2>&1
                    $result.Message = "Conflicts in non-auto-resolvable files: $($result.FilesBlocked -join ', ')"
                    return $result
                }

                # Check if there are staged changes to commit
                $null = git diff --cached --quiet 2>&1
                if ($LASTEXITCODE -eq 0) {
                    Write-Host "Merge completed without needing conflict resolution commit" -ForegroundColor Gray
                }
                else {
                    # Complete merge with commit
                    $null = git commit -m "Merge $TargetBranch into $BranchName - auto-resolve HANDOFF.md conflicts" 2>&1
                    if ($LASTEXITCODE -ne 0) {
                        throw "Failed to commit merge"
                    }
                }
            }

            # Push
            $pushOutput = git push origin $BranchName 2>&1
            if ($LASTEXITCODE -ne 0) {
                throw "Git push failed: $pushOutput"
            }

            $result.Success = $true
            $result.Message = "Successfully resolved conflicts for PR #$PRNumber"
            Write-Host $result.Message -ForegroundColor Green
            return $result
        }
        catch {
            $result.Message = "Failed to resolve conflicts for PR #${PRNumber}: $_"
            Write-Error $result.Message
            return $result
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

#endregion

#region Entry Point

# Guard: Only execute main logic when run directly, not when dot-sourced for testing
if ($MyInvocation.InvocationName -eq '.') {
    return
}

# Auto-detect repo info if not provided
if (-not $Owner -or -not $Repo) {
    $repoInfo = Get-RepoInfo
    if (-not $Owner) { $Owner = $repoInfo.Owner }
    if (-not $Repo) { $Repo = $repoInfo.Repo }
}

# Run conflict resolution
$result = Resolve-PRConflicts `
    -Owner $Owner `
    -Repo $Repo `
    -PRNumber $PRNumber `
    -BranchName $BranchName `
    -TargetBranch $TargetBranch `
    -WorktreeBasePath $WorktreeBasePath `
    -DryRun:$DryRun

# Output result as JSON for machine consumption
$result | ConvertTo-Json -Compress

# Exit with appropriate code
if ($result.Success) {
    exit 0
} else {
    exit 1
}

#endregion
