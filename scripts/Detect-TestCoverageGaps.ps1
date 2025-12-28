<#
.SYNOPSIS
  Detects PowerShell files without corresponding test files.

.DESCRIPTION
  Non-blocking WARNING that detects .ps1 files without corresponding .Tests.ps1 files.
  Helps identify test coverage gaps before they cause QA failures.
  
  This implements FR-4 from Local Guardrails consolidation (Issue #230).

.PARAMETER Path
  Root path to scan (default: repository root)

.PARAMETER StagedOnly
  If set, only checks git-staged files

.PARAMETER IgnoreFile
  Path to file containing patterns to ignore (one per line)

.EXAMPLE
  .\Detect-TestCoverageGaps.ps1 -StagedOnly
  Checks only staged files for missing tests
#>

[CmdletBinding()]
param(
  [string]$Path = ".",
  [switch]$StagedOnly,
  [string]$IgnoreFile = ""
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

# Load ignore patterns if provided
$ignorePatterns = @()
if ($IgnoreFile -and (Test-Path $IgnoreFile)) {
  $ignorePatterns = Get-Content $IgnoreFile | Where-Object { $_ -and $_ -notmatch '^\s*#' } | ForEach-Object { $_.Trim() }
}

# Default patterns to ignore
$defaultIgnore = @(
  '\.Tests\.ps1$',           # Test files themselves
  'tests?[\\/]',             # Test directories
  'build[\\/]',              # Build scripts
  '\.github[\\/]',           # GitHub workflows and scripts
  'install.*\.ps1$',         # Installation scripts
  'Common\.psm1$',           # Common modules (tested via consumers)
  'AIReviewCommon\.psm1$'    # Shared modules
)

$ignorePatterns += $defaultIgnore

# Get PowerShell files to check
$filesToCheck = @()
if ($StagedOnly) {
  $staged = (& git -C $repoRoot diff --cached --name-only --diff-filter=ACMR 2>$null) -split "`r?`n" | Where-Object { $_ -and $_.Trim() }
  if ($staged) {
    $filesToCheck = @($staged | Where-Object { $_ -match '\.ps1$' -and $_ -notmatch '\.Tests\.ps1$' })
  }
} else {
  $allFiles = Get-ChildItem -Path $repoRoot -Recurse -Filter "*.ps1" -File -ErrorAction SilentlyContinue | 
    Where-Object { $_.Name -notmatch '\.Tests\.ps1$' -and $_.FullName -notmatch '[\\/]\.git[\\/]' -and $_.FullName -notmatch '[\\/]node_modules[\\/]' }
  if ($allFiles) {
    $filesToCheck = @($allFiles | ForEach-Object { $_.FullName.Replace($repoRoot + [IO.Path]::DirectorySeparatorChar, '').Replace('\', '/') })
  }
}

# Ensure $filesToCheck is always an array
if ($filesToCheck -isnot [array]) {
  $filesToCheck = @($filesToCheck)
}

if ($filesToCheck.Count -eq 0) {
  Write-Host "No PowerShell files to check for test coverage"
  exit 0
}

$missingTests = @()

foreach ($file in $filesToCheck) {
  # Check ignore patterns
  $shouldIgnore = $false
  foreach ($pattern in $ignorePatterns) {
    if ($file -match $pattern) {
      $shouldIgnore = $true
      break
    }
  }
  
  if ($shouldIgnore) { continue }
  
  # Calculate expected test file path
  $fileWithoutExt = [IO.Path]::GetFileNameWithoutExtension($file)
  $fileDir = [IO.Path]::GetDirectoryName($file)
  
  # Check for test file in same directory
  $testFileName = "$fileWithoutExt.Tests.ps1"
  $testPath = if ($fileDir) { 
    Join-Path $fileDir $testFileName 
  } else { 
    $testFileName 
  }
  
  $testFullPath = Join-Path $repoRoot $testPath
  
  # Also check for tests/ subdirectory pattern
  $testsDir = if ($fileDir) { Join-Path $fileDir "tests" } else { "tests" }
  $testsDirPath = Join-Path $repoRoot $testsDir
  $testInSubdir = Join-Path $testsDirPath $testFileName
  
  if (-not (Test-Path $testFullPath) -and -not (Test-Path $testInSubdir)) {
    $missingTests += [PSCustomObject]@{
      File = $file
      ExpectedTest = $testPath
    }
  }
}

# Report missing tests
if ($missingTests.Count -gt 0) {
  Write-Host ""
  Write-Warning "Detected PowerShell files without test coverage"
  Write-Host "  Consider adding test files to improve quality and catch regressions"
  Write-Host ""
  
  foreach ($mt in $missingTests) {
    Write-Host "  $($mt.File)"
    Write-Host "    → Missing: $($mt.ExpectedTest)"
  }
  
  Write-Host ""
  Write-Host "This is a WARNING (non-blocking). To suppress, add patterns to ignore file."
  Write-Host "See: .github/instructions/testing.instructions.md"
  
  # Non-blocking: return success but warn
  exit 0
} else {
  Write-Host "All PowerShell files have corresponding test coverage"
  exit 0
}
