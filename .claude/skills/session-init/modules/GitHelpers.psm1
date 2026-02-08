<#
.SYNOPSIS
    Git repository information helpers.

.DESCRIPTION
    Provides functions to extract git state for session initialization.
    Retrieves repository root, current branch, commit SHA, and working tree status.

.NOTES
    Designed to be self-contained and reusable across session-init workflows.
#>

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

# Import shared exception type (single source of truth per Issue #840)
Import-Module (Join-Path $PSScriptRoot 'CommonTypes.psm1') -Force

# Fallback: define locally if type not available (e.g., module scoping edge cases)
if (-not ([System.Management.Automation.PSTypeName]'ApplicationFailedException').Type) {
    class ApplicationFailedException : System.ApplicationException {
        ApplicationFailedException([string]$Message, [Exception]$InnerException) : base($Message, $InnerException) {}
    }
}

function Get-GitInfo {
    <#
    .SYNOPSIS
        Gather git repository information for session initialization.

    .DESCRIPTION
        Retrieves comprehensive git repository state including root path, current branch,
        commit SHA, and working tree status. The commit SHA is extracted using
        'git rev-parse --short HEAD' to prevent subject line contamination that occurs
        with 'git log --oneline -1'.

    .OUTPUTS
        [hashtable] Containing:
        - RepoRoot: Absolute path to repository root
        - Branch: Current branch name
        - Commit: Short commit SHA (7-40 hex characters, no subject line)
        - Status: "clean" if no changes, "dirty" if working tree has changes

    .NOTES
        Throws:
        - InvalidOperationException: Not in a git repository or git operations failed
        - ApplicationFailedException: Unexpected errors during git command execution
        
        Custom Exception: ApplicationFailedException is defined at module scope for
        wrapping unexpected errors with full diagnostic context.

        Commit SHA Fix: Uses 'git rev-parse --short HEAD' instead of 'git log --oneline -1'
        to prevent including the commit subject line in the SHA, which contaminates logs.

        Edge Cases:
        - Detached HEAD: Returns empty string for branch (no exception thrown)
        - No commits: Throws InvalidOperationException with remediation guidance

    .EXAMPLE
        $gitInfo = Get-GitInfo
        Write-Host "Branch: $($gitInfo.Branch)"
        Write-Host "Commit: $($gitInfo.Commit)"
        Write-Host "Status: $($gitInfo.Status)"
    #>
    param()

    try {
        # Capture git output and errors separately
        $repoRootOutput = git rev-parse --show-toplevel 2>&1
        if ($LASTEXITCODE -ne 0) {
            $errorDetails = ($repoRootOutput | Out-String).Trim()
            $msg = @"
Not in a git repository. Git error (exit code $LASTEXITCODE): $errorDetails

Ensure you are in a git repository by running 'git status'. If you are in a git repository, check for corruption with 'git fsck'.
"@
            throw [System.InvalidOperationException]::new($msg)
        }
        # Handle potential null/empty output from git commands (can occur in CI shallow checkouts)
        $repoRoot = if ([string]::IsNullOrWhiteSpace($repoRootOutput)) { "" } else { ($repoRootOutput | Out-String).Trim() }

        $branchOutput = git branch --show-current 2>&1
        if ($LASTEXITCODE -ne 0) {
            $errorDetails = ($branchOutput | Out-String).Trim()
            $msg = @"
Failed to get current branch. Git error (exit code $LASTEXITCODE): $errorDetails

This usually means you are in a detached HEAD state or the repository is corrupted. Run 'git branch --show-current' manually to investigate.
"@
            throw [System.InvalidOperationException]::new($msg)
        }
        # Handle potential null/empty output (detached HEAD returns empty string, which is valid)
        $branch = if ([string]::IsNullOrWhiteSpace($branchOutput)) { "" } else { ($branchOutput | Out-String).Trim() }

        # FIX: Use 'git rev-parse --short HEAD' instead of 'git log --oneline -1'
        # This prevents including the commit subject line in the SHA, which contaminates session logs.
        # 'git log --oneline -1' returns: "abc1234 Subject line here"
        # 'git rev-parse --short HEAD' returns: "abc1234"
        $commitOutput = git rev-parse --short HEAD 2>&1
        if ($LASTEXITCODE -ne 0) {
            $errorDetails = ($commitOutput | Out-String).Trim()
            $msg = @"
Failed to get commit SHA. Git error (exit code $LASTEXITCODE): $errorDetails

This usually means the repository has no commits yet. Create an initial commit with 'git commit --allow-empty -m "Initial commit"'.
"@
            throw [System.InvalidOperationException]::new($msg)
        }
        # Handle potential null/empty output from git commands
        $commit = if ([string]::IsNullOrWhiteSpace($commitOutput)) { "" } else { ($commitOutput | Out-String).Trim() }

        $statusOutput = git status --short 2>&1
        if ($LASTEXITCODE -ne 0) {
            $errorDetails = $statusOutput -join "`n"
            $msg = @"
Failed to get git status. Git error (exit code $LASTEXITCODE): $errorDetails

This indicates repository corruption or permission issues. Run 'git status' manually to investigate.
"@
            throw [System.InvalidOperationException]::new($msg)
        }

        $gitStatus = if ([string]::IsNullOrWhiteSpace($statusOutput)) { "clean" } else { "dirty" }

        # Values are already trimmed above during assignment, return directly
        return @{
            RepoRoot = $repoRoot
            Branch = $branch
            Commit = $commit
            Status = $gitStatus
        }
    } catch [System.InvalidOperationException] {
        # Expected git operation failures - rethrow with detailed messages intact
        throw
    } catch {
        # Unexpected errors - wrap in ApplicationFailedException with diagnostic details
        $diagnosticMessage = @"
UNEXPECTED ERROR in Get-GitInfo
Exception Type: $($_.Exception.GetType().FullName)
Message: $($_.Exception.Message)
Stack Trace: $($_.ScriptStackTrace)

This is a bug. Please report this error with the above details.
"@
        
        $ex = [ApplicationFailedException]::new($diagnosticMessage, $_.Exception)
        throw $ex
    }
}

Export-ModuleMember -Function Get-GitInfo
