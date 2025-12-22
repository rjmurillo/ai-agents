<#
.SYNOPSIS
  Creates a validated PR with all guardrails enforced.

.DESCRIPTION
  Wrapper around `gh pr create` that runs all validation scripts before creating PR.
  Implements the "Validated PR Creation Wrapper" from Local Guardrails spec.
  
  Validations run (in order):
  1. Session End validation (if .agents/ changes)
  2. PR Description validation
  3. Skill violation detection (WARNING)
  4. Test coverage detection (WARNING)
  
  This implements FR-3 from Local Guardrails consolidation (Issue #230).

.PARAMETER Title
  PR title (required if not using --web)

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

.PARAMETER Web
  Open browser to create PR interactively

.PARAMETER Force
  Skip validations (use sparingly, logged for audit)

.EXAMPLE
  .\New-ValidatedPR.ps1 -Title "feat: Add feature" -Body "Description"
  Creates PR after running all validations

.EXAMPLE
  .\New-ValidatedPR.ps1 -Web
  Opens browser to create PR interactively (no validation)
  
.EXAMPLE
  .\New-ValidatedPR.ps1 -Title "hotfix" -Force
  Creates PR bypassing validation (audit logged)
#>

[CmdletBinding()]
param(
  [string]$Title = "",
  [string]$Body = "",
  [string]$BodyFile = "",
  [string]$Base = "main",
  [string]$Head = "",
  [switch]$Draft,
  [switch]$Web,
  [switch]$Force
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Get-RepoRoot {
  $root = (& git rev-parse --show-toplevel 2>$null)
  if (-not $root) { 
    Write-Error "Not in a git repository"
    exit 2
  }
  return $root.Trim()
}

$repoRoot = Get-RepoRoot

# Require gh CLI
if (-not (Get-Command gh -ErrorAction SilentlyContinue)) {
  Write-Error "gh CLI not found. Install: https://cli.github.com/"
  exit 2
}

# If --web flag, skip validation and use web interface
if ($Web) {
  Write-Host "Opening web interface (no validation in interactive mode)..."
  $ghArgs = @('pr', 'create', '--web')
  if ($Base) { $ghArgs += @('--base', $Base) }
  & gh @ghArgs
  exit $LASTEXITCODE
}

# Validate inputs
if (-not $Title -and -not $Force) {
  Write-Error "Title required (use -Title or -Web)"
  exit 2
}

# Get current branch if Head not specified
if (-not $Head) {
  $Head = (& git branch --show-current).Trim()
}

Write-Host "Preparing to create PR: $Head → $Base"
Write-Host "Title: $Title"
Write-Host ""

# Force mode audit trail
if ($Force) {
  Write-Warning "FORCE MODE: Skipping validations (audit logged)"
  $auditDir = Join-Path $repoRoot ".agents/audit"
  if (-not (Test-Path $auditDir)) {
    New-Item -ItemType Directory -Path $auditDir -Force | Out-Null
  }
  
  $auditEntry = @"
Timestamp: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')
Branch: $Head → $Base
Title: $Title
User: $env:USERNAME
Force: true
"@
  
  $auditFile = Join-Path $auditDir "pr-creation-force-$(Get-Date -Format 'yyyyMMdd-HHmmss').txt"
  $auditEntry | Set-Content $auditFile
  Write-Host "Audit logged: $auditFile"
  Write-Host ""
  
  # Skip to PR creation
} else {
  Write-Host "Running validations..."
  Write-Host ""
  
  # Validation 1: Session End (if .agents/ files changed)
  Write-Host "[1/4] Checking Session End protocol..."
  $agentsChanged = & git diff --name-only "$Base...$Head" | Select-String -Pattern '^\.agents/' -Quiet
  
  if ($agentsChanged) {
    $sessionLog = & git diff --name-only "$Base...$Head" | 
      Select-String -Pattern '^\.agents/sessions/.*\.md$' | 
      Select-Object -Last 1 -ExpandProperty Line
    
    if ($sessionLog) {
      $validateScript = Join-Path $repoRoot "scripts/Validate-SessionEnd.ps1"
      if (Test-Path $validateScript) {
        $sessionLogPath = Join-Path $repoRoot $sessionLog
        & pwsh -NoProfile -File $validateScript -SessionLogPath $sessionLogPath
        if ($LASTEXITCODE -ne 0) {
          Write-Error "Session End validation failed"
          exit 1
        }
      } else {
        Write-Warning "Session End validation script not found"
      }
    } else {
      Write-Warning "No session log found but .agents/ files changed"
    }
  } else {
    Write-Host "  No .agents/ changes, skipping"
  }
  
  # Validation 2: Skill violation detection (WARNING)
  Write-Host ""
  Write-Host "[2/4] Checking for skill violations..."
  $skillScript = Join-Path $repoRoot "scripts/Detect-SkillViolation.ps1"
  if (Test-Path $skillScript) {
    & pwsh -NoProfile -File $skillScript
    # Non-blocking, continue regardless
  } else {
    Write-Host "  Script not found, skipping"
  }
  
  # Validation 3: Test coverage detection (WARNING)
  Write-Host ""
  Write-Host "[3/4] Checking test coverage..."
  $testScript = Join-Path $repoRoot "scripts/Detect-TestCoverageGaps.ps1"
  if (Test-Path $testScript) {
    & pwsh -NoProfile -File $testScript
    # Non-blocking, continue regardless
  } else {
    Write-Host "  Script not found, skipping"
  }
  
  # Validation 4: PR description validation (BLOCKING - but we can't validate yet since PR doesn't exist)
  Write-Host ""
  Write-Host "[4/4] PR description validation"
  Write-Host "  Will be validated after PR creation (see CI workflow)"
  
  Write-Host ""
  Write-Host "All pre-creation validations passed!"
  Write-Host ""
}

# Build gh pr create command
$ghArgs = @('pr', 'create', '--base', $Base, '--head', $Head)

if ($Title) {
  $ghArgs += @('--title', $Title)
}

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
Write-Host "Command: gh $($ghArgs -join ' ')"
Write-Host ""

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
