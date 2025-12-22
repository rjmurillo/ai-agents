<#
.SYNOPSIS
  Creates a validated PR with all guardrails enforced.

.DESCRIPTION
  Wrapper around the New-PR skill that provides a convenient interface for
  creating PRs with validation. This script delegates to the skill for better
  cohesion and reusability.
  
  Exit codes:
    0 = Success
    1 = Validation failure  
    2 = Usage/environment error

.PARAMETER Title
  PR title in conventional commit format (e.g., "feat: Add feature")

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
  Open browser to create PR interactively (bypasses validation)

.PARAMETER SkipValidation
  Skip validation checks. Requires -AuditReason. Use sparingly for emergencies only.

.PARAMETER AuditReason
  Required when -SkipValidation is used. Documents reason for skipping validation.

.EXAMPLE
  .\New-ValidatedPR.ps1 -Title "feat: Add feature" -Body "Description"
  Creates PR after running all validations

.EXAMPLE
  .\New-ValidatedPR.ps1 -Title "feat: Feature" -BodyFile "pr-body.md" -Draft
  Creates draft PR with body from file

.EXAMPLE
  .\New-ValidatedPR.ps1 -Web
  Opens browser for interactive PR creation (no validation)
  
.EXAMPLE
  .\New-ValidatedPR.ps1 -Title "fix: Hotfix" -SkipValidation -AuditReason "Production incident #123"
  Creates PR without validation (audit logged)

.NOTES
  This is a thin wrapper around .claude/skills/github/scripts/pr/New-PR.ps1
  which contains the core logic. The skill can be used directly for more control.
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
  [switch]$SkipValidation,
  [string]$AuditReason = ""
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

# Get repository root
$repoRoot = (& git rev-parse --show-toplevel 2>$null)
if (-not $repoRoot) {
  Write-Error "Not in a git repository"
  exit 2
}
$repoRoot = $repoRoot.Trim()

# Require gh CLI
if (-not (Get-Command gh -ErrorAction SilentlyContinue)) {
  Write-Error "gh CLI not found. Install: https://cli.github.com/"
  exit 2
}

# Handle --web flag (interactive mode, no validation)
if ($Web) {
  # Check if we're in a CI/headless environment
  if ($env:CI -or $env:GITHUB_ACTIONS -or -not $env:DISPLAY) {
    Write-Error "Web mode is not available in CI or headless environments"
    Write-Host "Use -Title and -Body parameters instead, or run in an interactive environment"
    exit 2
  }
  
  Write-Host "Opening web interface (no validation in interactive mode)..."
  $ghArgs = @('pr', 'create', '--web')
  if ($Base) { $ghArgs += @('--base', $Base) }
  & gh @ghArgs
  exit $LASTEXITCODE
}

# Validate required parameters
if (-not $Title) {
  Write-Error "Title required (use -Title or -Web)"
  Write-Host "Example: .\New-ValidatedPR.ps1 -Title 'feat: Add feature' -Body 'Description'"
  exit 2
}

# Delegate to the skill
$skillScript = Join-Path $repoRoot ".claude/skills/github/scripts/pr/New-PR.ps1"
if (-not (Test-Path $skillScript)) {
  Write-Error "PR creation skill not found: $skillScript"
  exit 2
}

# Build arguments for the skill
$skillArgs = @(
  '-Title', $Title,
  '-Base', $Base
)

if ($Head) { $skillArgs += @('-Head', $Head) }
if ($Body) { $skillArgs += @('-Body', $Body) }
if ($BodyFile) { $skillArgs += @('-BodyFile', $BodyFile) }
if ($Draft) { $skillArgs += '-Draft' }
if ($SkipValidation) { 
  $skillArgs += '-SkipValidation'
  if ($AuditReason) {
    $skillArgs += @('-AuditReason', $AuditReason)
  }
}

# Execute the skill
& pwsh -NoProfile -File $skillScript @skillArgs
exit $LASTEXITCODE
