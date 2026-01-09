<#
.SYNOPSIS
  Migrates markdown session logs to JSON format.

.PARAMETER Path
  Path to markdown session log or directory of logs.

.PARAMETER Force
  Overwrite existing JSON files.

.PARAMETER DryRun
  Show what would be migrated without writing files.

.OUTPUTS
  Array of migrated file paths.
#>
[CmdletBinding()]
param(
  [Parameter(Mandatory)]
  [string]$Path,
  
  [switch]$Force,
  [switch]$DryRun
)

$ErrorActionPreference = 'Stop'

function Find-ChecklistItem {
  param([string]$Content, [string]$Pattern)
  
  # Look for table rows with [x] that match the pattern
  $matches = [regex]::Matches($Content, "\|[^|]*\|[^|]*$Pattern[^|]*\|\s*\[x\]\s*\|([^|]*)\|", 'IgnoreCase')
  if ($matches.Count -gt 0) {
    return @{
      Complete = $true
      Evidence = $matches[0].Groups[1].Value.Trim()
    }
  }
  return @{ Complete = $false; Evidence = '' }
}

function ConvertFrom-MarkdownSession {
  param([string]$Content, [string]$FileName)
  
  # Extract session number from filename
  $sessionNum = 0
  if ($FileName -match 'session-(\d+)') {
    $sessionNum = [int]$Matches[1]
  }
  
  # Extract date from filename
  $sessionDate = ''
  if ($FileName -match '^(\d{4}-\d{2}-\d{2})') {
    $sessionDate = $Matches[1]
  }
  
  # Extract branch
  $branch = ''
  if ($Content -match '\*?\*?Branch\*?\*?:\s*([^\n\r]+)') {
    $branch = $Matches[1].Trim()
  }
  
  # Extract commit
  $commit = ''
  if ($Content -match '\*?\*?(?:Starting\s+)?Commit\*?\*?:\s*`?([a-f0-9]{7,40})`?') {
    $commit = $Matches[1]
  }
  
  # Extract objective
  $objective = ''
  if ($Content -match '##\s*Objective\s*\n+([^\n#]+)') {
    $objective = $Matches[1].Trim()
  }
  
  # Build session start checks
  $sessionStart = @{
    serenaActivated = Find-ChecklistItem $Content 'activate_project'
    serenaInstructions = Find-ChecklistItem $Content 'initial_instructions'
    handoffRead = Find-ChecklistItem $Content 'HANDOFF\.md'
    sessionLogCreated = Find-ChecklistItem $Content 'Create.*session.*log|session.*log.*exist|this.*file'
    skillScriptsListed = Find-ChecklistItem $Content 'skill.*script'
    usageMandatoryRead = Find-ChecklistItem $Content 'usage-mandatory'
    constraintsRead = Find-ChecklistItem $Content 'CONSTRAINTS'
    memoriesLoaded = Find-ChecklistItem $Content 'memor'
    branchVerified = Find-ChecklistItem $Content 'verify.*branch|branch.*verif|declare.*branch'
    notOnMain = Find-ChecklistItem $Content 'not.*main|Confirm.*main'
    gitStatusVerified = Find-ChecklistItem $Content 'git.*status'
    startingCommitNoted = Find-ChecklistItem $Content 'starting.*commit|Note.*commit'
  }
  
  # Add level info
  foreach ($key in @('serenaActivated','serenaInstructions','handoffRead','sessionLogCreated','skillScriptsListed','usageMandatoryRead','constraintsRead','memoriesLoaded','branchVerified','notOnMain')) {
    $sessionStart[$key].level = 'MUST'
  }
  foreach ($key in @('gitStatusVerified','startingCommitNoted')) {
    $sessionStart[$key].level = 'SHOULD'
  }
  
  # Build session end checks
  $sessionEnd = @{
    checklistComplete = Find-ChecklistItem $Content 'Complete.*session.*log|session.*log.*complete|all.*section'
    handoffNotUpdated = @{ level = 'MUST NOT'; complete = $false; evidence = (Find-ChecklistItem $Content 'HANDOFF.*read-only|Update.*HANDOFF').Evidence }
    serenaMemoryUpdated = Find-ChecklistItem $Content 'Serena.*memory|Update.*memory|memory.*updat'
    markdownLintRun = Find-ChecklistItem $Content 'markdownlint|markdown.*lint|Run.*lint'
    changesCommitted = Find-ChecklistItem $Content 'Commit.*change|change.*commit'
    validationPassed = Find-ChecklistItem $Content 'Validate.*Session|validation.*pass|Route.*qa'
    tasksUpdated = Find-ChecklistItem $Content 'PROJECT-PLAN|task.*checkbox'
    retrospectiveInvoked = Find-ChecklistItem $Content 'retrospective'
  }
  
  # Add level info
  foreach ($key in @('checklistComplete','serenaMemoryUpdated','markdownLintRun','changesCommitted','validationPassed')) {
    $sessionEnd[$key].level = 'MUST'
  }
  foreach ($key in @('tasksUpdated','retrospectiveInvoked')) {
    $sessionEnd[$key].level = 'SHOULD'
  }
  
  return @{
    session = @{
      number = $sessionNum
      date = $sessionDate
      branch = $branch
      startingCommit = $commit
      objective = if ($objective) { $objective } else { "[Migrated from markdown]" }
    }
    protocolCompliance = @{
      sessionStart = $sessionStart
      sessionEnd = $sessionEnd
    }
    workLog = @()
    endingCommit = ''
    nextSteps = @()
  }
}

# Get files to migrate
$files = @()
if (Test-Path $Path -PathType Container) {
  $files = Get-ChildItem $Path -Filter '*.md' | Where-Object { $_.Name -match '^\d{4}-\d{2}-\d{2}-session' }
} elseif (Test-Path $Path -PathType Leaf) {
  $files = @(Get-Item $Path)
} else {
  Write-Error "Path not found: $Path"
  exit 1
}

$migrated = @()
$skipped = @()
$failed = @()

foreach ($file in $files) {
  $jsonPath = $file.FullName -replace '\.md$', '.json'
  
  if ((Test-Path $jsonPath) -and -not $Force) {
    $skipped += $file.Name
    continue
  }
  
  try {
    $content = Get-Content $file.FullName -Raw
    $session = ConvertFrom-MarkdownSession -Content $content -FileName $file.Name
    
    if ($DryRun) {
      Write-Host "[DRY RUN] Would migrate: $($file.Name) -> $(Split-Path $jsonPath -Leaf)"
      $migrated += $jsonPath
    } else {
      $session | ConvertTo-Json -Depth 10 | Set-Content $jsonPath -Encoding utf8
      Write-Host "[OK] Migrated: $($file.Name) -> $(Split-Path $jsonPath -Leaf)"
      $migrated += $jsonPath
    }
  } catch {
    Write-Host "[FAIL] $($file.Name): $_" -ForegroundColor Red
    $failed += $file.Name
  }
}

Write-Host "`n=== Migration Summary ===" -ForegroundColor Cyan
Write-Host "Migrated: $($migrated.Count)"
Write-Host "Skipped (JSON exists): $($skipped.Count)"
Write-Host "Failed: $($failed.Count)"

if ($failed.Count -gt 0) {
  exit 1
}

return $migrated
