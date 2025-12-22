<#
.SYNOPSIS
  Validates PR description matches actual code changes.

.DESCRIPTION
  BLOCKING validation that prevents PR description vs diff mismatches.
  Detects when PR description claims files were changed that are not in the diff,
  or when major changes are not mentioned in the description.
  
  This prevents Analyst CRITICAL_FAIL verdicts as seen in PR #199.
  Implements FR-2 from Local Guardrails consolidation (Issue #230).

.PARAMETER PRNumber
  PR number to validate

.PARAMETER Owner
  Repository owner (default: from git remote)

.PARAMETER Repo
  Repository name (default: from git remote)

.PARAMETER CI
  CI mode: exit non-zero on validation failure

.EXAMPLE
  .\Validate-PRDescription.ps1 -PRNumber 226 -CI
  Validates PR #226 description against its diff
#>

[CmdletBinding()]
param(
  [Parameter(Mandatory = $true)]
  [int]$PRNumber,
  
  [string]$Owner = "",
  [string]$Repo = "",
  [switch]$CI
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Get-RepoInfo {
  $remoteUrl = (& git remote get-url origin 2>$null)
  if (-not $remoteUrl) {
    throw "Could not determine git remote origin"
  }
  
  # Parse GitHub URL (supports both HTTPS and SSH)
  if ($remoteUrl -match 'github\.com[:/]([^/]+)/([^/\.]+)') {
    return @{
      Owner = $Matches[1]
      Repo = $Matches[2]
    }
  }
  
  throw "Could not parse GitHub owner/repo from remote URL: $remoteUrl"
}

# Get repo info if not provided
if (-not $Owner -or -not $Repo) {
  $repoInfo = Get-RepoInfo
  if (-not $Owner) { $Owner = $repoInfo.Owner }
  if (-not $Repo) { $Repo = $repoInfo.Repo }
}

# Require gh CLI
if (-not (Get-Command gh -ErrorAction SilentlyContinue)) {
  Write-Error "gh CLI not found. Install: https://cli.github.com/"
  exit 2
}

# Fetch PR data
Write-Host "Fetching PR #$PRNumber data..."
$prJson = & gh pr view $PRNumber --json title,body,files --repo "$Owner/$Repo"
if ($LASTEXITCODE -ne 0) {
  Write-Error "Failed to fetch PR #$PRNumber"
  exit 2
}

$pr = $prJson | ConvertFrom-Json

# Extract files mentioned in PR description
$description = $pr.body
$filesInPR = $pr.files | ForEach-Object { $_.path }

Write-Host "PR has $($filesInPR.Count) changed files"

# Extract file paths from description using common patterns
$mentionedFiles = @()
$patterns = @(
  '`([^`]+\.(ps1|md|yml|yaml|json|cs|ts|js|py|sh|bash))`',  # Inline code
  '\*\*([^*]+\.(ps1|md|yml|yaml|json|cs|ts|js|py|sh|bash))\*\*',  # Bold
  '^\s*[-*+]\s+([^\s]+\.(ps1|md|yml|yaml|json|cs|ts|js|py|sh|bash))',  # List items
  '\[([^\]]+\.(ps1|md|yml|yaml|json|cs|ts|js|py|sh|bash))\]'  # Markdown links
)

foreach ($pattern in $patterns) {
  $matches = [regex]::Matches($description, $pattern, [System.Text.RegularExpressions.RegexOptions]::Multiline)
  foreach ($match in $matches) {
    $file = $match.Groups[1].Value.Trim()
    # Normalize path separators
    $file = $file -replace '\\', '/'
    # Remove leading ./
    $file = $file -replace '^\./', ''
    $mentionedFiles += $file
  }
}

$mentionedFiles = $mentionedFiles | Select-Object -Unique
Write-Host "Description mentions $($mentionedFiles.Count) files"

# Check for mismatches
$issues = @()

# Check 1: Files mentioned but not in diff (CRITICAL)
foreach ($mentioned in $mentionedFiles) {
  $found = $false
  foreach ($actual in $filesInPR) {
    # Match both exact and suffix (e.g., "file.ps1" matches "path/to/file.ps1")
    if ($actual -eq $mentioned -or $actual -like "*/$mentioned" -or $actual -like "*\$mentioned") {
      $found = $true
      break
    }
  }
  
  if (-not $found) {
    $issues += [PSCustomObject]@{
      Severity = "CRITICAL"
      Type = "File mentioned but not in diff"
      File = $mentioned
      Message = "Description claims this file was changed, but it's not in the PR diff"
    }
  }
}

# Check 2: Major files changed but not mentioned (WARNING)
$significantExtensions = @('.ps1', '.cs', '.ts', '.js', '.py', '.yml', '.yaml')
$significantChanges = $filesInPR | Where-Object { 
  $ext = [IO.Path]::GetExtension($_)
  $ext -in $significantExtensions
}

foreach ($changed in $significantChanges) {
  $isMentioned = $false
  foreach ($mentionedFile in $mentionedFiles) {
    if ($changed -eq $mentionedFile -or $changed -like "*/$mentionedFile" -or $changed -like "*\$mentionedFile") {
      $isMentioned = $true
      break
    }
  }
  
  if (-not $isMentioned) {
    # Only warn about files in key directories
    if ($changed -match '^(\.github|scripts|src|\.agents)') {
      $issues += [PSCustomObject]@{
        Severity = "WARNING"
        Type = "Significant file not mentioned"
        File = $changed
        Message = "This file was changed but not mentioned in the description"
      }
    }
  }
}

# Report results
Write-Host ""
if ($issues.Count -eq 0) {
  Write-Host "✓ PR description matches diff (no mismatches found)"
  exit 0
}

$criticalCount = ($issues | Where-Object { $_.Severity -eq "CRITICAL" }).Count
$warningCount = ($issues | Where-Object { $_.Severity -eq "WARNING" }).Count

Write-Host "Found $($issues.Count) issue(s):"
Write-Host "  CRITICAL: $criticalCount"
Write-Host "  WARNING: $warningCount"
Write-Host ""

foreach ($issue in $issues) {
  $color = if ($issue.Severity -eq "CRITICAL") { "Red" } else { "Yellow" }
  Write-Host "[$($issue.Severity)] $($issue.Type)" -ForegroundColor $color
  Write-Host "  File: $($issue.File)"
  Write-Host "  $($issue.Message)"
  Write-Host ""
}

if ($criticalCount -gt 0) {
  Write-Host "CRITICAL issues found. Update PR description to match actual changes." -ForegroundColor Red
  if ($CI) { exit 1 }
} elseif ($warningCount -gt 0) {
  Write-Host "Warnings found. Consider mentioning significant files in PR description." -ForegroundColor Yellow
  # Warnings are non-blocking
  exit 0
}

exit 0
