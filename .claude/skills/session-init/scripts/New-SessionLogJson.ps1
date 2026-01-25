<#
.SYNOPSIS
  Creates a new session log in JSON format.

.PARAMETER SessionNumber
  Session number. Auto-detects from existing files if not provided.

.PARAMETER Objective
  Session objective description.

.NOTES
  EXIT CODES:
  0  - Success: Session log created successfully

  See: ADR-035 Exit Code Standardization

.OUTPUTS
  Path to created session log.
#>
[CmdletBinding()]
param(
  [int]$SessionNumber = 0,
  [string]$Objective = ""
)

$ErrorActionPreference = 'Stop'

# Get repo root (go up from skills/session-init/scripts to repo root)
$repoRoot = Split-Path (Split-Path (Split-Path (Split-Path $PSScriptRoot)))
$sessionsDir = Join-Path $repoRoot '.agents/sessions'

# Ensure directory exists
if (-not (Test-Path $sessionsDir)) {
  New-Item -ItemType Directory -Path $sessionsDir -Force | Out-Null
}

# Auto-detect session number
if ($SessionNumber -eq 0) {
  $existing = Get-ChildItem $sessionsDir -Filter '*.json' | 
    Where-Object { $_.Name -match 'session-(\d+)' } |
    ForEach-Object { [int]$Matches[1] } |
    Sort-Object -Descending |
    Select-Object -First 1
  $SessionNumber = if ($existing) { $existing + 1 } else { 1 }
}

# Get git info
$date = Get-Date -Format 'yyyy-MM-dd'

# Get branch with proper error handling
$branchOutput = git branch --show-current 2>&1
if ($LASTEXITCODE -ne 0) {
  $errorDetails = ($branchOutput | Out-String).Trim()
  Write-Warning "Failed to get current branch. Git error (exit code $LASTEXITCODE): $errorDetails"
  Write-Warning "Using 'unknown' as branch. Ensure you are in a git repository."
  $branch = 'unknown'
} else {
  $branch = if ([string]::IsNullOrWhiteSpace($branchOutput)) { 'unknown' } else { ($branchOutput | Out-String).Trim() }
}

# Get commit SHA with proper error handling
$commitOutput = git rev-parse --short HEAD 2>&1
if ($LASTEXITCODE -ne 0) {
  $errorDetails = ($commitOutput | Out-String).Trim()
  Write-Warning "Failed to get commit SHA. Git error (exit code $LASTEXITCODE): $errorDetails"
  Write-Warning "Using 'unknown' as commit. Ensure you are in a git repository with at least one commit."
  $commit = 'unknown'
} else {
  $commit = if ([string]::IsNullOrWhiteSpace($commitOutput)) { 'unknown' } else { ($commitOutput | Out-String).Trim() }
}

# Build session object
$session = @{
  session = @{
    number = $SessionNumber
    date = $date
    branch = $branch
    startingCommit = $commit
    objective = if ($Objective) { $Objective } else { "[TODO: Describe objective]" }
  }
  protocolCompliance = @{
    sessionStart = @{
      serenaActivated = @{ level = 'MUST'; Complete = $false; Evidence = '' }
      serenaInstructions = @{ level = 'MUST'; Complete = $false; Evidence = '' }
      handoffRead = @{ level = 'MUST'; Complete = $false; Evidence = '' }
      sessionLogCreated = @{ level = 'MUST'; Complete = $true; Evidence = 'This file' }
      skillScriptsListed = @{ level = 'MUST'; Complete = $false; Evidence = '' }
      usageMandatoryRead = @{ level = 'MUST'; Complete = $false; Evidence = '' }
      constraintsRead = @{ level = 'MUST'; Complete = $false; Evidence = '' }
      memoriesLoaded = @{ level = 'MUST'; Complete = $false; Evidence = '' }
      branchVerified = @{ level = 'MUST'; Complete = $true; Evidence = $branch }
      notOnMain = @{ level = 'MUST'; Complete = ($branch -notmatch '^(main|master)$'); Evidence = "On $branch" }
      gitStatusVerified = @{ level = 'SHOULD'; Complete = $false; Evidence = '' }
      startingCommitNoted = @{ level = 'SHOULD'; Complete = $true; Evidence = $commit }
    }
    sessionEnd = @{
      checklistComplete = @{ level = 'MUST'; Complete = $false; Evidence = '' }
      handoffNotUpdated = @{ level = 'MUST NOT'; Complete = $false; Evidence = '' }
      serenaMemoryUpdated = @{ level = 'MUST'; Complete = $false; Evidence = '' }
      markdownLintRun = @{ level = 'MUST'; Complete = $false; Evidence = '' }
      changesCommitted = @{ level = 'MUST'; Complete = $false; Evidence = '' }
      validationPassed = @{ level = 'MUST'; Complete = $false; Evidence = '' }
      tasksUpdated = @{ level = 'SHOULD'; Complete = $false; Evidence = '' }
      retrospectiveInvoked = @{ level = 'SHOULD'; Complete = $false; Evidence = '' }
    }
  }
  workLog = @()
  endingCommit = ''
  nextSteps = @()
}

# Write file
$fileName = "$date-session-$SessionNumber.json"
$filePath = Join-Path $sessionsDir $fileName

$session | ConvertTo-Json -Depth 10 | Set-Content $filePath -Encoding utf8

Write-Host "Created: $filePath" -ForegroundColor Green
Write-Host "Session: $SessionNumber" -ForegroundColor Cyan
Write-Host "Branch: $branch" -ForegroundColor Cyan
Write-Host "Commit: $commit" -ForegroundColor Cyan

return $filePath
