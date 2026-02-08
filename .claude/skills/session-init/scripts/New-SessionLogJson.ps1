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

# CWE-400: Reject session number jumps larger than 10 above max existing
$maxExisting = Get-ChildItem $sessionsDir -Filter '*.json' |
    Where-Object { $_.Name -match 'session-(\d+)' } |
    ForEach-Object { [int]$Matches[1] } |
    Sort-Object -Descending |
    Select-Object -First 1
if ($maxExisting -and $SessionNumber -gt ($maxExisting + 10)) {
  Write-Error "Session number $SessionNumber exceeds ceiling (max existing: $maxExisting, ceiling: $($maxExisting + 10)). This prevents DoS via large session numbers."
  exit 1
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

# Write file with atomic creation (CWE-362: prevent race condition)
$json = $session | ConvertTo-Json -Depth 10
$maxRetries = 5
$created = $false

for ($retry = 0; $retry -lt $maxRetries; $retry++) {
  $fileName = "$date-session-$SessionNumber.json"
  $filePath = Join-Path $sessionsDir $fileName

  try {
    # Atomic creation: throws IOException if file already exists
    $stream = [System.IO.File]::Open($filePath, [System.IO.FileMode]::CreateNew, [System.IO.FileAccess]::Write)
    try {
      $writer = [System.IO.StreamWriter]::new($stream, [System.Text.UTF8Encoding]::new($false))
      $writer.Write($json)
      $writer.Flush()
    } finally {
      if ($writer) { $writer.Dispose() }
      if ($stream) { $stream.Dispose() }
    }
    $created = $true
    break
  } catch [System.IO.IOException] {
    # Only retry if the file actually exists (collision). Re-throw for disk-full, path errors, etc.
    if (-not (Test-Path $filePath)) { throw }
    Write-Warning "Session $SessionNumber already exists, trying $($SessionNumber + 1)"
    $SessionNumber++
    # Update session number in the JSON
    $session.session.number = $SessionNumber
    $json = $session | ConvertTo-Json -Depth 10
  }
}

if (-not $created) {
  Write-Error "Failed to create session log after $maxRetries attempts. Last tried: session-$SessionNumber"
  exit 2
}

Write-Host "Created: $filePath" -ForegroundColor Green
Write-Host "Session: $SessionNumber" -ForegroundColor Cyan
Write-Host "Branch: $branch" -ForegroundColor Cyan
Write-Host "Commit: $commit" -ForegroundColor Cyan

return $filePath
