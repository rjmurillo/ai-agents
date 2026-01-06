<#
.SYNOPSIS
  Creates a GitHub PR with validation guardrails.

.DESCRIPTION
  Core PR creation logic with validation gates. This script is called by
  New-ValidatedPR.ps1 wrapper and can also be used directly by skills.
  
  Exit codes:
    0 = Success
    1 = Validation failure
    2 = Usage/environment error

.PARAMETER Title
  PR title in conventional commit format (required)

.PARAMETER Body
  PR description body

.PARAMETER BodyFile
  Path to file containing PR body

.PARAMETER Base
  Target branch (default: main)

.PARAMETER Head
  Source branch (default: current branch)

.PARAMETER Draft
  Create as draft PR

.PARAMETER SkipValidation
  Skip validation checks (requires -AuditReason)

.PARAMETER AuditReason
  Required when -SkipValidation is used. Logged for audit trail.

.EXAMPLE
  .\New-PR.ps1 -Title "feat: Add feature" -Body "Description"
  
.EXAMPLE
  .\New-PR.ps1 -Title "fix: Bug fix" -SkipValidation -AuditReason "Hotfix for production incident #123"
#>

[CmdletBinding()]
param(
  [Parameter(Mandatory = $true)]
  [string]$Title,
  
  [string]$Body = "",
  [string]$BodyFile = "",
  [string]$Base = "main",
  [string]$Head = "",
  [switch]$Draft,
  [switch]$SkipValidation,
  [string]$AuditReason = ""
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

#region Helper Functions

function Get-RepoRoot {
  $root = (& git rev-parse --show-toplevel 2>$null)
  if (-not $root) { 
    Write-Error "Not in a git repository"
    exit 2
  }
  return $root.Trim()
}

function Test-ConventionalCommit {
  param([string]$Title)
  
  # Conventional commit format: type(scope): description
  # type: feat, fix, docs, style, refactor, perf, test, chore, ci, build, revert
  $pattern = '^(feat|fix|docs|style|refactor|perf|test|chore|ci|build|revert)(\(.+\))?!?: .+'
  
  if ($Title -notmatch $pattern) {
    Write-Error "Title must follow conventional commit format: type(scope): description"
    Write-Host "  Valid types: feat, fix, docs, style, refactor, perf, test, chore, ci, build, revert"
    Write-Host "  Example: feat: Add new feature"
    Write-Host "  Example: fix(auth): Resolve login issue"
    return $false
  }
  
  return $true
}

function Invoke-Validation {
  param(
    [string]$RepoRoot,
    [string]$Base,
    [string]$Head
  )
  
  Write-Host "Running validations..."
  Write-Host ""
  
  # Validation 1: Session End (if .agents/ files changed)
  Write-Host "[1/3] Checking Session End protocol..."
  $agentsChanged = & git diff --name-only "$Base...$Head" | Select-String -Pattern '^\.agents/' -Quiet
  
  if ($agentsChanged) {
    $sessionLog = & git diff --name-only "$Base...$Head" | 
      Select-String -Pattern '^\.agents/sessions/.*\.md$' | 
      Select-Object -Last 1 -ExpandProperty Line
    
    if ($sessionLog) {
      $validateScript = Join-Path $RepoRoot "scripts/Validate-Session.ps1"
      if (Test-Path $validateScript) {
        $sessionLogPath = Join-Path $RepoRoot $sessionLog
        & pwsh -NoProfile -File $validateScript -SessionPath $sessionLogPath
        if ($LASTEXITCODE -ne 0) {
          throw "Session End validation failed"
        }
      }
    } else {
      Write-Warning "No session log found but .agents/ files changed"
    }
  } else {
    Write-Host "  No .agents/ changes, skipping"
  }
  
  # Validation 2: Skill violation detection (WARNING)
  Write-Host ""
  Write-Host "[2/3] Checking for skill violations..."
  $skillScript = Join-Path $RepoRoot "scripts/Detect-SkillViolation.ps1"
  if (Test-Path $skillScript) {
    & pwsh -NoProfile -File $skillScript
  }
  
  # Validation 3: Test coverage detection (WARNING)
  Write-Host ""
  Write-Host "[3/3] Checking test coverage..."
  $testScript = Join-Path $RepoRoot "scripts/Detect-TestCoverageGaps.ps1"
  if (Test-Path $testScript) {
    & pwsh -NoProfile -File $testScript
  }
  
  Write-Host ""
  Write-Host "All pre-creation validations passed!"
  Write-Host ""
}

function Write-AuditLog {
  param(
    [string]$RepoRoot,
    [string]$Head,
    [string]$Base,
    [string]$Title,
    [string]$Reason
  )
  
  $auditDir = Join-Path $RepoRoot ".agents/audit"
  if (-not (Test-Path $auditDir)) {
    New-Item -ItemType Directory -Path $auditDir -Force | Out-Null
  }
  
  # Cross-platform username detection (Windows: USERNAME, Linux/macOS: USER)
  $username = if ($env:USERNAME) { $env:USERNAME } else { $env:USER }
  if (-not $username) {
    # Fallback to whoami if env vars not set
    $username = (whoami 2>$null) -replace '.*[/\\]', ''
  }

  $auditEntry = @"
Timestamp: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')
Branch: $Head → $Base
Title: $Title
User: $username
Validation: SKIPPED
Reason: $Reason
"@
  
  $auditFile = Join-Path $auditDir "pr-creation-skip-$(Get-Date -Format 'yyyyMMdd-HHmmss').txt"
  $auditEntry | Set-Content $auditFile
  Write-Host "Audit logged: $auditFile"
}

#endregion

# Main execution
$repoRoot = Get-RepoRoot

# Require gh CLI
if (-not (Get-Command gh -ErrorAction SilentlyContinue)) {
  Write-Error "gh CLI not found. Install: https://cli.github.com/"
  exit 2
}

# Get current branch if Head not specified
if (-not $Head) {
  $Head = (& git branch --show-current).Trim()
  if (-not $Head) {
    Write-Error "Could not determine current branch"
    exit 2
  }
}

# Validate conventional commit format
if (-not (Test-ConventionalCommit -Title $Title)) {
  exit 2
}

Write-Host "Preparing to create PR: $Head → $Base"
Write-Host "Title: $Title"
Write-Host ""

# Handle validation skip with audit
if ($SkipValidation) {
  if (-not $AuditReason) {
    Write-Error "-SkipValidation requires -AuditReason for audit trail"
    exit 2
  }
  
  Write-Warning "VALIDATION SKIPPED (audit logged)"
  Write-AuditLog -RepoRoot $repoRoot -Head $Head -Base $Base -Title $Title -Reason $AuditReason
  Write-Host ""
} else {
  # Run validations
  try {
    Invoke-Validation -RepoRoot $repoRoot -Base $Base -Head $Head
  } catch {
    Write-Error "Validation failed: $_"
    exit 1
  }
}

# Build gh pr create command
$ghArgs = @('pr', 'create', '--base', $Base, '--head', $Head, '--title', $Title)

if ($Body) {
  $ghArgs += @('--body', $Body)
} elseif ($BodyFile) {
  if (-not (Test-Path $BodyFile)) {
    Write-Error "Body file not found: $BodyFile"
    exit 2
  }
  $ghArgs += @('--body-file', $BodyFile)
}

if ($Draft) {
  $ghArgs += '--draft'
}

# Create PR
Write-Host "Creating PR..."
& gh @ghArgs
$exitCode = $LASTEXITCODE

if ($exitCode -eq 0) {
  Write-Host ""
  Write-Host "✓ PR created successfully!"
  Write-Host ""
  Write-Host "Next steps:"
  Write-Host "  - CI will run additional validations (PR description, QA, security)"
  Write-Host "  - Address any validation failures before merge"
  Write-Host "  - Wait for required approvals"
} else {
  Write-Error "PR creation failed (exit code: $exitCode)"
}

exit $exitCode
