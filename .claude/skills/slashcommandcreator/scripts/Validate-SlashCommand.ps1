#!/usr/bin/env pwsh
<#
.SYNOPSIS
  Validate slash command file for quality gates.

.DESCRIPTION
  Validates slash command (.md) files for 5 categories:
  1. Frontmatter - Required YAML frontmatter with description
  2. Arguments - Consistency between argument-hint and $ARGUMENTS usage
  3. Security - allowed-tools required when bash execution (!) is used
  4. Length - Warning if >200 lines (suggest converting to skill)
  5. Lint - Markdown lint via markdownlint-cli2

  Exit codes:
  - 0: All validations passed
  - 1: One or more BLOCKING violations found

.PARAMETER Path
  Path to slash command .md file to validate.

.PARAMETER SkipLint
  Skip markdown lint validation (useful for testing other validators).

.EXAMPLE
  .\Validate-SlashCommand.ps1 -Path .claude/commands/analyze.md
  Validates the analyze slash command.
#>

[CmdletBinding()]
param(
  [Parameter(Mandatory = $true)]
  [string]$Path,

  [switch]$SkipLint
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

# Exit codes
$EXIT_SUCCESS = 0
$EXIT_VIOLATION = 1

$violations = @()

# Validate file exists
if (-not (Test-Path -Path $Path)) {
  $resolvedPath = Resolve-Path -Path $Path -ErrorAction SilentlyContinue
  $currentDir = Get-Location
  Write-Host "[FAIL] File not found: $Path" -ForegroundColor Red
  Write-Host "  Current directory: $currentDir" -ForegroundColor Yellow
  if ($resolvedPath) {
    Write-Host "  Resolved path: $resolvedPath" -ForegroundColor Yellow
  }
  Write-Host "  Troubleshooting:" -ForegroundColor Cyan
  Write-Host "    - Verify file path is correct" -ForegroundColor Cyan
  Write-Host "    - Check if file has been moved or deleted" -ForegroundColor Cyan
  Write-Host "    - Use absolute path if relative path is ambiguous" -ForegroundColor Cyan
  exit $EXIT_VIOLATION
}

# 1. Frontmatter Validation
$content = Get-Content -Path $Path -Raw

# WHY: Use regex for YAML parsing instead of PowerShell-YAML module dependency
# LIMITATION: Won't handle multi-line YAML values or complex nesting
# MITIGATION: Pester tests validate against real-world command files (see M5-M6)
$hasArgHint = $false
$frontmatter = $null

if ($content -notmatch '(?s)^---\s*\n(.*?)\n---') {
  $violations += "BLOCKING: Missing YAML frontmatter block"
}
else {
  $frontmatter = $matches[1]

  # Parse description field
  if ($frontmatter -notmatch 'description:\s*(.+)') {
    $violations += "BLOCKING: Missing 'description' in frontmatter"
  }
  else {
    $description = $matches[1].Trim()
    # Trigger-based validation per creator-001
    if ($description -notmatch '^(Use when|Generate|Research|Invoke|Create|Analyze|Review|Search)') {
      $violations += "WARNING: Description should start with action verb or 'Use when...'"
    }
  }

  $hasArgHint = $frontmatter -match 'argument-hint:\s*(.+)'
  # Note: $argHintValue captured for potential future use in enhanced validation
  if ($hasArgHint) { $null = $matches[1].Trim() }
}

# 2. Argument Validation
$usesArguments = $content -match '\$ARGUMENTS|\$1|\$2|\$3'

if ($usesArguments -and -not $hasArgHint) {
  $violations += "BLOCKING: Prompt uses arguments but no 'argument-hint' in frontmatter"
}

if ($hasArgHint -and -not $usesArguments) {
  $violations += "WARNING: Frontmatter has 'argument-hint' but prompt doesn't use arguments"
}

# 3. Security Validation
$usesBashExecution = $content -match '!\s*\w+'

if ($usesBashExecution -and $null -ne $frontmatter) {
  $hasAllowedTools = $frontmatter -match 'allowed-tools:\s*\[(.+)\]'

  if (-not $hasAllowedTools) {
    $violations += "BLOCKING: Prompt uses bash execution (!) but no 'allowed-tools' in frontmatter"
  }
  else {
    $allowedTools = $matches[1]

    # Check for overly permissive wildcards
    # WHY: Allow scoped namespaces like mcp__*, mcp__serena__*, mcp__forgetful__*
    #      but reject bare *, **/*, or other overly permissive patterns
    # Pattern logic: detect wildcards NOT preceded by mcp__ prefix
    $hasOverlyPermissive = $false

    # Split by comma and check each tool entry
    $toolList = $allowedTools -split ',' | ForEach-Object { $_.Trim() }
    foreach ($tool in $toolList) {
      # If tool contains * but doesn't start with mcp__, it's overly permissive
      if ($tool -match '\*' -and $tool -notmatch '^mcp__') {
        $hasOverlyPermissive = $true
        break
      }
    }

    if ($hasOverlyPermissive) {
      $violations += "BLOCKING: 'allowed-tools' has overly permissive wildcard (use mcp__* for scoped namespaces)"
    }
  }

  # Verify common bash commands exist (warning only)
  $bashCommands = [regex]::Matches($content, '!\s*(\w+)') | ForEach-Object { $_.Groups[1].Value }
  foreach ($cmd in $bashCommands) {
    if ($cmd -in @('git', 'gh', 'npm', 'npx')) {
      try {
        $exists = Get-Command $cmd -ErrorAction Stop
      }
      catch [System.Management.Automation.CommandNotFoundException] {
        $violations += "WARNING: Bash command '$cmd' not found in PATH (runtime may fail)"
      }
      catch {
        # Other errors (execution policy, PATH corruption, etc.) should be surfaced
        Write-Warning "Error checking command '$cmd': $_"
      }
    }
  }
}

# 4. Length Validation
$lineCount = ($content -split '\n').Count

if ($lineCount -gt 200) {
  $violations += "WARNING: File has $lineCount lines (>200). Consider converting to skill."
}

# 5. Lint Validation
if (-not $SkipLint) {
  Write-Host "Running markdownlint-cli2..." -ForegroundColor Cyan
  $lintResult = npx markdownlint-cli2 $Path 2>&1

  if ($LASTEXITCODE -ne 0) {
    $violations += "BLOCKING: Markdown lint errors:"
    $violations += $lintResult
    $violations += ""
    $violations += "  To auto-fix: npx markdownlint-cli2 --fix $Path"
    $violations += "  Configuration: .markdownlint.json (if exists) or defaults"
  }
}

# Determine if any BLOCKING violations exist
# WHY: Wrap with @() to handle PowerShell gotcha where single/null results lose array semantics
$blockingCount = @($violations | Where-Object { $_ -match '^BLOCKING:' }).Count
$warningCount = @($violations | Where-Object { $_ -match '^WARNING:' }).Count

# Report violations
if ($violations.Count -gt 0) {
  Write-Host "`n[FAIL] Validation FAILED: $Path" -ForegroundColor Red
  Write-Host "`nViolations ($blockingCount blocking, $warningCount warnings):" -ForegroundColor Yellow
  $violations | ForEach-Object { Write-Host "  - $_" }

  if ($blockingCount -gt 0) {
    exit $EXIT_VIOLATION
  }
  else {
    # Warnings only - pass with warnings displayed
    Write-Host "`n[PASS] Validation PASSED with warnings: $Path" -ForegroundColor Yellow
    exit $EXIT_SUCCESS
  }
}
else {
  Write-Host "`n[PASS] Validation PASSED: $Path" -ForegroundColor Green
  exit $EXIT_SUCCESS
}
