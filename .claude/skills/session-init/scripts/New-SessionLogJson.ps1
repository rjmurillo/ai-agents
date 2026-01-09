<#
.SYNOPSIS
  Creates a new session log in JSON format.

.PARAMETER SessionNumber
  Session number. Auto-detects from existing files if not provided.

.PARAMETER Objective
  Session objective description.

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
$branch = git branch --show-current 2>$null
$commit = git rev-parse --short HEAD 2>$null

if (-not $branch) { $branch = 'unknown' }
if (-not $commit) { $commit = 'unknown' }

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
      serenaActivated = @{ level = 'MUST'; complete = $false; evidence = '' }
      serenaInstructions = @{ level = 'MUST'; complete = $false; evidence = '' }
      handoffRead = @{ level = 'MUST'; complete = $false; evidence = '' }
      sessionLogCreated = @{ level = 'MUST'; complete = $true; evidence = 'This file' }
      skillScriptsListed = @{ level = 'MUST'; complete = $false; evidence = '' }
      usageMandatoryRead = @{ level = 'MUST'; complete = $false; evidence = '' }
      constraintsRead = @{ level = 'MUST'; complete = $false; evidence = '' }
      memoriesLoaded = @{ level = 'MUST'; complete = $false; evidence = '' }
      branchVerified = @{ level = 'MUST'; complete = $true; evidence = $branch }
      notOnMain = @{ level = 'MUST'; complete = ($branch -notmatch '^(main|master)$'); evidence = "On $branch" }
      gitStatusVerified = @{ level = 'SHOULD'; complete = $false; evidence = '' }
      startingCommitNoted = @{ level = 'SHOULD'; complete = $true; evidence = $commit }
    }
    sessionEnd = @{
      checklistComplete = @{ level = 'MUST'; complete = $false; evidence = '' }
      handoffNotUpdated = @{ level = 'MUST NOT'; complete = $false; evidence = '' }
      serenaMemoryUpdated = @{ level = 'MUST'; complete = $false; evidence = '' }
      markdownLintRun = @{ level = 'MUST'; complete = $false; evidence = '' }
      changesCommitted = @{ level = 'MUST'; complete = $false; evidence = '' }
      validationPassed = @{ level = 'MUST'; complete = $false; evidence = '' }
      tasksUpdated = @{ level = 'SHOULD'; complete = $false; evidence = '' }
      retrospectiveInvoked = @{ level = 'SHOULD'; complete = $false; evidence = '' }
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
