<#
.SYNOPSIS
  Detects raw gh command usage when GitHub skills exist.

.DESCRIPTION
  Non-blocking WARNING that detects raw `gh` commands in markdown and PowerShell files
  when equivalent GitHub skill scripts exist in .claude/skills/github/.
  
  This implements Phase 1 guardrail from Issue #230.

.PARAMETER Path
  Root path to scan (default: repository root)

.PARAMETER StagedOnly
  If set, only checks git-staged files

.EXAMPLE
  .\Detect-SkillViolation.ps1 -StagedOnly
  Checks only staged files for skill violations
#>

[CmdletBinding()]
param(
  [string]$Path = ".",
  [switch]$StagedOnly
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Get-RepoRoot([string]$StartDir) {
  $root = (& git -C $StartDir rev-parse --show-toplevel 2>$null)
  if (-not $root) { 
    Write-Error "Could not find git repo root from: $StartDir"
    exit 1
  }
  return $root.Trim()
}

$repoRoot = Get-RepoRoot (Resolve-Path $Path).Path
$skillsDir = Join-Path $repoRoot ".claude/skills/github/scripts"

# Check if skills directory exists
if (-not (Test-Path $skillsDir)) {
  Write-Warning "GitHub skills directory not found: $skillsDir"
  exit 0
}

# Get files to check
$filesToCheck = @()
if ($StagedOnly) {
  $staged = (& git -C $repoRoot diff --cached --name-only --diff-filter=ACMR 2>$null) -split "`r?`n" | Where-Object { $_ -and $_.Trim() }
  if ($staged) {
    $filesToCheck = @($staged | Where-Object { $_ -match '\.(md|ps1|psm1)$' })
  }
} else {
  $allFiles = Get-ChildItem -Path $repoRoot -Recurse -Include *.md,*.ps1,*.psm1 -File -ErrorAction SilentlyContinue | 
    Where-Object { $_.FullName -notmatch '[\\/]\.git[\\/]' -and $_.FullName -notmatch '[\\/]node_modules[\\/]' }
  if ($allFiles) {
    $filesToCheck = @($allFiles | ForEach-Object { $_.FullName.Replace($repoRoot + [IO.Path]::DirectorySeparatorChar, '').Replace('\', '/') })
  }
}

# Ensure $filesToCheck is always an array
if ($filesToCheck -isnot [array]) {
  $filesToCheck = @($filesToCheck)
}

if ($filesToCheck.Count -eq 0) {
  Write-Host "No files to check for skill violations"
  exit 0
}

# Patterns to detect raw gh usage
$ghPatterns = @(
  'gh\s+pr\s+(create|merge|close|view|list|diff)',
  'gh\s+issue\s+(create|close|view|list)',
  'gh\s+api\s+',
  'gh\s+repo\s+'
)

$violations = @()

foreach ($file in $filesToCheck) {
  $fullPath = Join-Path $repoRoot $file
  if (-not (Test-Path $fullPath)) { continue }
  
  try {
    $content = Get-Content -Path $fullPath -Raw -ErrorAction SilentlyContinue
    if (-not $content) { continue }
    
    foreach ($pattern in $ghPatterns) {
      if ($content -match $pattern) {
        $violations += [PSCustomObject]@{
          File = $file
          Pattern = $pattern
          Line = ($content -split "`r?`n" | Select-String -Pattern $pattern | Select-Object -First 1 -ExpandProperty LineNumber)
        }
        break  # Only report once per file
      }
    }
  } catch {
    Write-Warning "Could not read file: $file"
  }
}

# Report violations
if ($violations.Count -gt 0) {
  Write-Host ""
  Write-Warning "Detected raw 'gh' command usage (skill violations)"
  Write-Host "  These commands indicate missing GitHub skill capabilities."
  Write-Host "  Use .claude/skills/github/ scripts instead, or file an issue to add the capability."
  Write-Host ""
  
  # Track violations for capability improvement
  $capabilityGaps = @()
  
  foreach ($v in $violations) {
    Write-Host "  $($v.File):$($v.Line) - matches '$($v.Pattern)'"
    
    # Extract the specific command for capability tracking
    $pattern = $v.Pattern
    if ($pattern -match 'gh\s+(\w+)\s+') {
      $command = $Matches[1]
      if ($capabilityGaps -notcontains $command) {
        $capabilityGaps += $command
      }
    }
  }
  
  Write-Host ""
  Write-Host "Missing skill capabilities detected:"
  foreach ($gap in $capabilityGaps) {
    Write-Host "  - gh $gap (consider adding to .claude/skills/github/)"
  }
  
  Write-Host ""
  Write-Host "REMINDER: Use GitHub skills for better error handling, consistency, and auditability."
  Write-Host "  Before using raw 'gh' commands, check: Get-ChildItem .claude/skills/github/scripts -Recurse"
  Write-Host "  If the capability you need doesn't exist, create a skill script or file an issue."
  Write-Host ""
  Write-Host "See: .serena/memories/skill-usage-mandatory.md"
  
  # Non-blocking: return warning status but don't fail
  exit 0
} else {
  Write-Host "No skill violations detected"
  exit 0
}
