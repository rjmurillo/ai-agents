<#
.SYNOPSIS
  Validates Session Start and Session End protocol compliance for a single session log.

.DESCRIPTION
  Verification-based enforcement for Session Protocol, as defined in .agents/SESSION-PROTOCOL.md.

  This script validates BOTH:
  - Session Start requirements (Serena init, HANDOFF read, skill list, etc.)
  - Session End requirements (complete checklist, QA, commit, etc.)

  This script is intentionally FAIL-CLOSED:
  - If a requirement cannot be verified, it FAILS.
  - Agent self-attestation is ignored unless backed by artifacts (git state, files, tool exit codes).

  Exit codes:
    0 = PASS
    1 = FAIL (protocol violation)
    2 = FAIL (usage / environment)

.PARAMETER SessionLogPath
  Path to .agents/sessions/YYYY-MM-DD-session-NN*.md

.PARAMETER FixMarkdown
  If set, runs markdownlint with --fix before validating.

.NOTES
  Designed to be called by:
  - Orchestrator "Session End" gate
  - .githooks/pre-commit
  - CI
#>

[CmdletBinding()]
param(
  [Parameter(Mandatory = $true)]
  [string]$SessionLogPath,

  [switch]$FixMarkdown,

  [switch]$PreCommit
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

# Import session validation module
$ModulePath = Join-Path $PSScriptRoot "modules" "SessionValidation.psm1"
Import-Module $ModulePath -Force

function Fail([string]$Code, [string]$Message) {
  Write-Error "${Code}: $Message"
  exit 1
}

function RequireCommand([string]$Name) {
  if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
    Fail 'E_TOOL_MISSING' "Required command not found: $Name"
  }
}

function Get-RepoRoot([string]$StartDir) {
  RequireCommand 'git'
  # Use git rev-parse for robustness (handles worktrees, bare repos, etc.)
  try {
    $repoRoot = & git -C $StartDir rev-parse --show-toplevel 2>$null
    if ($LASTEXITCODE -eq 0 -and $repoRoot) {
      return $repoRoot.Trim().TrimEnd([char]'\', [char]'/')
    }
  } catch {
    # Fall through to fallback
  }

  # Fallback: walk up from StartDir until a .git directory or file is found
  # Note: .git can be a file (gitdir reference) in worktrees
  $dir = [System.IO.Path]::GetFullPath($StartDir)
  while ($true) {
    $gitPath = Join-Path $dir '.git'
    if (Test-Path -LiteralPath $gitPath) {
      return $dir.TrimEnd([char]'\', [char]'/')
    }
    $parent = Split-Path -Parent $dir
    if (-not $parent -or $parent -eq $dir) { Fail 'E_GIT_ROOT' "Could not find git repo root from: $StartDir" }
    $dir = $parent
  }
}

function Read-AllText([string]$Path) {
  if (-not (Test-Path -LiteralPath $Path)) { Fail 'E_SESSION_NOT_FOUND' "Session log not found: $Path" }
  return (Get-Content -LiteralPath $Path -Raw -Encoding UTF8)
}

function Get-RelativePath([string]$Root, [string]$FullPath) {
  $rootFull = (Resolve-Path -LiteralPath $Root).Path.TrimEnd('\','/')
  $full = (Resolve-Path -LiteralPath $FullPath).Path
  if ($full.StartsWith($rootFull)) {
    $rel = $full.Substring($rootFull.Length).TrimStart('\','/')
    return $rel -replace '\\','/'
  }
  return $FullPath -replace '\\','/'
}

function Get-HeadingTable([string[]]$Lines, [string]$HeadingRegex) {
  # Returns the first markdown table after a heading line matching HeadingRegex.
  $headingIdx = -1
  for ($i = 0; $i -lt $Lines.Count; $i++) {
    if ($Lines[$i] -match $HeadingRegex) { $headingIdx = $i; break }
  }
  if ($headingIdx -lt 0) { return $null }

  # Find table header row after heading
  $tableStart = -1
  for ($i = $headingIdx; $i -lt [Math]::Min($headingIdx + 80, $Lines.Count); $i++) {
    if ($Lines[$i] -match '^\|\s*Req\s*\|\s*Step\s*\|\s*Status\s*\|\s*Evidence\s*\|\s*$') { $tableStart = $i; break }
  }
  if ($tableStart -lt 0) { return $null }

  $tableLines = New-Object System.Collections.Generic.List[string]
  for ($i = $tableStart; $i -lt $Lines.Count; $i++) {
    $line = $Lines[$i]
    if ($line -match '^\|') {
      $tableLines.Add($line)
      continue
    }
    break
  }
  return $tableLines.ToArray()
}

# Functions Split-TableRow, Parse-ChecklistTable, Normalize-Step, and Test-MemoryEvidence
# are now imported from scripts/modules/SessionValidation.psm1

# --- Load inputs
$sessionFullPath = (Resolve-Path -LiteralPath $SessionLogPath).Path
$repoRoot = Get-RepoRoot (Split-Path -Parent $sessionFullPath)

# Security: Validate session log is under expected directory (CWE-22, see #214)
# Normalize paths and add trailing separator to prevent prefix bypass (e.g., .agents/sessions-evil)
$expectedDir = [System.IO.Path]::Combine($repoRoot, '.agents', 'sessions')
$expectedDirNormalized = [System.IO.Path]::GetFullPath($expectedDir).TrimEnd('\','/')
$sessionFullPathNormalized = [System.IO.Path]::GetFullPath($sessionFullPath)

# Diagnostics (visible with -Verbose)
Write-Verbose ("repoRoot={0}" -f $repoRoot)
Write-Verbose ("expectedDirNormalized={0}" -f $expectedDirNormalized)
Write-Verbose ("sessionFullPathNormalized={0}" -f $sessionFullPathNormalized)

# Robust containment check: ensure session path is inside expectedDir
# Use case-insensitive comparison for Windows filesystem compatibility
$ds = [System.IO.Path]::DirectorySeparatorChar
$ads = [System.IO.Path]::AltDirectorySeparatorChar
$prefix1 = "$expectedDirNormalized$ds"
$prefix2 = "$expectedDirNormalized$ads"
$isContained = $sessionFullPathNormalized.StartsWith($prefix1, [System.StringComparison]::OrdinalIgnoreCase) -or `
               $sessionFullPathNormalized.StartsWith($prefix2, [System.StringComparison]::OrdinalIgnoreCase)
if (-not $isContained) {
  Fail 'E_PATH_ESCAPE' "Session log must be under .agents/sessions/: $sessionFullPath`n  repoRoot=$repoRoot`n  expectedDirNormalized=$expectedDirNormalized`n  sessionFullPathNormalized=$sessionFullPathNormalized"
}

$sessionRel = Get-RelativePath $repoRoot $sessionFullPath

$protocolPath = Join-Path $repoRoot ".agents/SESSION-PROTOCOL.md"
if (-not (Test-Path -LiteralPath $protocolPath)) {
  Fail 'E_PROTOCOL_MISSING' "Missing canonical protocol file: .agents/SESSION-PROTOCOL.md"
}

$sessionText = Read-AllText $sessionFullPath
$protocolText = Read-AllText $protocolPath

$sessionLines = $sessionText -split "`r?`n"
$protocolLines = $protocolText -split "`r?`n"

# =============================================================================
# SESSION START VALIDATION
# =============================================================================
# Validates that Session Start requirements are met before checking Session End.
# This catches the gap where PRs pass local pre-commit but fail CI.
#
# CANONICAL FORMAT ONLY: Session logs MUST use the table format from SESSION-PROTOCOL.md:
#   | Req | Step | Status | Evidence |
#   |-----|------|--------|----------|
#   | MUST | Initialize Serena: `mcp__serena__activate_project` | [x] | Tool output present |
#
# Non-canonical formats (bullet lists, etc.) are NOT accepted.

Write-Output "Validating Session Start requirements..."

# --- Extract canonical Session Start checklist from protocol
$protocolStartTableLines = Get-HeadingTable -Lines $protocolLines -HeadingRegex '^\s*###\s+Session Start\s*\(COMPLETE ALL before work\)\s*$'
if (-not $protocolStartTableLines) {
  Fail 'E_PROTOCOL_START_TABLE_MISSING' "Could not find canonical 'Session Start' checklist table in SESSION-PROTOCOL.md"
}
$protocolStartRows = Parse-ChecklistTable $protocolStartTableLines
if ($protocolStartRows.Count -lt 1) {
  Fail 'E_PROTOCOL_START_TABLE_PARSE' "Canonical Session Start checklist table is empty or could not be parsed."
}

# --- Extract Session Start checklist from session log
$sessionStartTableLines = Get-HeadingTable -Lines $sessionLines -HeadingRegex '^\s*#{2,3}\s+.*Session Start.*$'
if (-not $sessionStartTableLines) {
  Fail 'E_SESSION_START_TABLE_MISSING' @"
Could not find Session Start checklist TABLE in session log.

REQUIRED: Copy the canonical table format from SESSION-PROTOCOL.md:

### Session Start (COMPLETE ALL before work)

| Req | Step | Status | Evidence |
|-----|------|--------|----------|
| MUST | Initialize Serena: ``mcp__serena__activate_project`` | [x] | Tool output present |
| MUST | Initialize Serena: ``mcp__serena__initial_instructions`` | [x] | Tool output present |
...

NOTE: Bullet-list format is NOT accepted. Use the table format.
"@
}
$sessionStartRows = Parse-ChecklistTable $sessionStartTableLines
if ($sessionStartRows.Count -lt 1) {
  Fail 'E_SESSION_START_TABLE_PARSE' @"
Session Start checklist table is empty or could not be parsed.

Ensure you're using the canonical table format:
| Req | Step | Status | Evidence |
|-----|------|--------|----------|

Copy the template from SESSION-PROTOCOL.md.
"@
}

# --- Enforce template match for Session Start (Req, Step) order
$protoStartKey = $protocolStartRows | ForEach-Object { "$($_.Req)|$(Normalize-Step $_.Step)" }
$sessStartKey  = $sessionStartRows   | ForEach-Object { "$($_.Req)|$(Normalize-Step $_.Step)" }

if ($protoStartKey.Count -ne $sessStartKey.Count) {
  Fail 'E_START_TEMPLATE_DRIFT' "Session Start checklist row count mismatch (protocol=$($protoStartKey.Count), session=$($sessStartKey.Count)). Copy the canonical checklist from SESSION-PROTOCOL.md."
}

for ($i = 0; $i -lt $protoStartKey.Count; $i++) {
  if ($protoStartKey[$i] -ne $sessStartKey[$i]) {
    Fail 'E_START_TEMPLATE_DRIFT' ("Session Start checklist mismatch at row {0}. Expected '{1}', got '{2}'. Copy the canonical checklist from SESSION-PROTOCOL.md." -f ($i+1), $protoStartKey[$i], $sessStartKey[$i])
  }
}

# --- Verify Session Start MUST rows are checked
$mustStartRows = $sessionStartRows | Where-Object { $_.Req -eq 'MUST' }
if ($mustStartRows.Count -eq 0) {
  Fail 'E_NO_START_MUST_ROWS' "No MUST rows found in Session Start checklist."
}

foreach ($row in $mustStartRows) {
  if ($row.Status -ne 'x') {
    Fail 'E_START_MUST_INCOMPLETE' "Session Start MUST item not complete: $($row.Step)"
  }
}

# =============================================================================
# ADR-007 MEMORY EVIDENCE VALIDATION (E2)
# =============================================================================
# Validates that the Evidence column for memory-related rows contains actual
# memory names that exist in .serena/memories/. This closes the trust gap where
# agents could self-report memory retrieval without actually doing it.
#
# Related: ADR-007, Issue #729, Session 63 (E2 implementation)
# Function Test-MemoryEvidence is now imported from scripts/modules/SessionValidation.psm1

# Run memory evidence validation
Write-Output "Validating memory retrieval evidence (ADR-007)..."
$memoryValidation = Test-MemoryEvidence -SessionRows $sessionStartRows -RepoRoot $repoRoot

if (-not $memoryValidation.IsValid) {
  $memoryErrors = if ($memoryValidation.Errors -and $memoryValidation.Errors.Count -gt 0) { $memoryValidation.Errors -join '; ' } else { 'Memory evidence validation failed.' }
  Fail 'E_MEMORY_EVIDENCE_INVALID' $memoryErrors
}

if ($memoryValidation.Warnings) {
  $warningArray = @($memoryValidation.Warnings)
  if ($warningArray.Count -gt 0) {
    Write-Warning "Memory evidence warnings: $($warningArray -join '; ')"
  }
}

Write-Output "OK: Session Start validation passed ($($mustStartRows.Count) MUST requirements verified)"

# =============================================================================
# SESSION END VALIDATION
# =============================================================================

Write-Output "Validating Session End requirements..."

# --- Extract canonical Session End checklist from protocol
$protocolTableLines = Get-HeadingTable -Lines $protocolLines -HeadingRegex '^\s*##\s+Session End Checklist\s*$'
if (-not $protocolTableLines) {
  Fail 'E_PROTOCOL_TABLE_MISSING' "Could not find canonical 'Session End Checklist' table in SESSION-PROTOCOL.md"
}
$protocolRows = Parse-ChecklistTable $protocolTableLines
if ($protocolRows.Count -lt 3) {
  Fail 'E_PROTOCOL_TABLE_PARSE' "Canonical Session End checklist table could not be parsed."
}

# --- Extract Session End checklist from session log
$sessionTableLines = Get-HeadingTable -Lines $sessionLines -HeadingRegex '^\s*#{2,3}\s+.*Session End.*$'
if (-not $sessionTableLines) {
  Fail 'E_SESSION_END_TABLE_MISSING' "Could not find Session End checklist table in session log."
}
$sessionRows = Parse-ChecklistTable $sessionTableLines
if ($sessionRows.Count -lt 3) {
  Fail 'E_SESSION_END_TABLE_PARSE' "Session End checklist table could not be parsed."
}

# --- Enforce template match for (Req, Step) order
$protoKey = $protocolRows | ForEach-Object { "$($_.Req)|$(Normalize-Step $_.Step)" }
$sessKey  = $sessionRows   | ForEach-Object { "$($_.Req)|$(Normalize-Step $_.Step)" }

if ($protoKey.Count -ne $sessKey.Count) {
  Fail 'E_TEMPLATE_DRIFT' "Session End checklist row count mismatch (protocol=$($protoKey.Count), session=$($sessKey.Count)). Copy the canonical checklist from SESSION-PROTOCOL.md."
}

for ($i = 0; $i -lt $protoKey.Count; $i++) {
  if ($protoKey[$i] -ne $sessKey[$i]) {
    Fail 'E_TEMPLATE_DRIFT' ("Checklist mismatch at row {0}. Expected '{1}', got '{2}'. Copy the canonical checklist from SESSION-PROTOCOL.md." -f ($i+1), $protoKey[$i], $sessKey[$i])
  }
}

# --- Verify MUST rows checked, with QA skip rules
# Determine doc-only vs code/config changes using Starting Commit if present.
$startingCommit = $null
if ($sessionText -match '(?m)^\s*-\s*\*\*Starting Commit\*\*\s*:\s*`?([0-9a-f]{7,40})`?\s*$') {
  $startingCommit = $Matches[1]
} elseif ($sessionText -match '(?m)^\s*Starting Commit\s*:\s*([0-9a-f]{7,40})\s*$') {
  $startingCommit = $Matches[1]
}

$changedFiles = @()
# In pre-commit mode, check staged files (not full session diff) to avoid false positives
# when fixing session log format on branches with prior code changes. Issue #551.
if ($PreCommit) {
  try {
    $changedFiles = @((& git -C $repoRoot diff --staged --name-only) -split "`r?`n" | Where-Object { $_ -and $_.Trim() -ne '' })
  } catch {
    # Fallback to starting commit comparison if staged files check fails
    Write-Warning "Git staged diff failed: $($_.Exception.Message). Falling back to starting commit comparison."
    $changedFiles = @()
  }
}
# If not pre-commit or no staged files, use starting commit comparison
if ($changedFiles.Count -eq 0 -and $startingCommit) {
  try {
    # Wrap in @() to ensure result is always an array (fixes Count property error when single file)
    $changedFiles = @((& git -C $repoRoot diff --name-only "$startingCommit..HEAD") -split "`r?`n" | Where-Object { $_ -and $_.Trim() -ne '' })
  } catch {
    Fail 'E_GIT_DIFF_FAIL' "Could not compute changed files from Starting Commit $startingCommit. Ensure Starting Commit is valid."
  }
}

function Test-DocsOnly([string[]]$Files) {
  if (-not $Files -or $Files.Count -eq 0) { return $true } # conservative: treat unknown as docs-only? No.
  foreach ($f in $Files) {
    $ext = [IO.Path]::GetExtension($f).ToLowerInvariant()
    if ($ext -ne '.md') { return $false }
  }
  return $true
}

# Investigation-only allowlist patterns (ADR-034)
# Sessions that only modify these paths can skip QA with "SKIPPED: investigation-only"
$script:InvestigationAllowlist = @(
  '^\.agents/sessions/',        # Session logs
  '^\.agents/analysis/',        # Investigation outputs
  '^\.agents/retrospective/',   # Learnings
  '^\.serena/memories($|/)',    # Cross-session context
  '^\.agents/security/'         # Security assessments
)

# Session audit artifacts that are exempt from QA validation
# These are audit trail files, not implementation
$script:AuditArtifacts = @(
  '^\.agents/sessions/',        # Session logs (audit trail)
  '^\.agents/analysis/',        # Investigation outputs
  '^\.serena/memories($|/)'     # Cross-session context
)

function Test-InvestigationOnlyEligibility {
  [CmdletBinding()]
  param(
    [string[]]$Files
  )
  <#
  .SYNOPSIS
    Tests if all staged files are in the investigation-only allowlist.

  .DESCRIPTION
    Returns a hashtable with:
    - IsEligible: $true if all files match allowlist patterns
    - ImplementationFiles: array of files that don't match (empty if eligible)

  .NOTES
    Per ADR-034, investigation sessions that only produce analysis artifacts
    can skip QA validation.
  #>
  $result = @{
    IsEligible = $true
    ImplementationFiles = @()
  }

  if (-not $Files -or $Files.Count -eq 0) {
    # No files = no commit, pass
    return $result
  }

  $implementationFiles = [System.Collections.Generic.List[string]]::new()
  foreach ($file in $Files) {
    # Normalize path separators
    $normalizedFile = $file -replace '\\', '/'

    $isAllowed = $false
    foreach ($pattern in $script:InvestigationAllowlist) {
      if ($normalizedFile -match $pattern) {
        $isAllowed = $true
        break
      }
    }

    if (-not $isAllowed) {
      $implementationFiles.Add($file)
    }
  }

  if ($implementationFiles.Count -gt 0) {
    $result.IsEligible = $false
    $result.ImplementationFiles = $implementationFiles.ToArray()
  }

  return $result
}

function Get-ImplementationFiles {
  [CmdletBinding()]
  param(
    [string[]]$Files
  )
  <#
  .SYNOPSIS
    Filters out audit artifacts (session logs, analysis, memories) from file list.

  .DESCRIPTION
    Returns only files that are implementation (code, ADRs, config, tests, etc.)
    by filtering out audit trail artifacts.
    
    This allows session logs to be committed WITH implementation files without
    requiring investigation-only skip or separate commits.

  .NOTES
    Session logs are audit trail, not implementation. They should not trigger
    QA requirements when committed alongside code changes.
  #>
  if (-not $Files -or $Files.Count -eq 0) {
    return @()
  }

  $implementationFiles = [System.Collections.Generic.List[string]]::new()
  foreach ($file in $Files) {
    # Normalize path separators
    $normalizedFile = $file -replace '\\', '/'

    $isAuditArtifact = $false
    foreach ($pattern in $script:AuditArtifacts) {
      if ($normalizedFile -match $pattern) {
        $isAuditArtifact = $true
        break
      }
    }

    if (-not $isAuditArtifact) {
      $implementationFiles.Add($file)
    }
  }

  return $implementationFiles.ToArray()
}

$docsOnly = $false
$investigationResult = @{ IsEligible = $false; ImplementationFiles = @() }

# Check if we have files to analyze (from starting commit diff or pre-commit staged files)
if (($startingCommit -or $PreCommit) -and $changedFiles.Count -gt 0) {
  # Filter out audit artifacts (session logs, analysis, memories) before checking docs-only
  # This allows session logs to be committed WITH implementation without triggering false positives
  $implFiles = Get-ImplementationFiles $changedFiles
  $docsOnly = Test-DocsOnly $implFiles
  $investigationResult = Test-InvestigationOnlyEligibility $changedFiles
}
# else: If we cannot prove docs-only, treat as NOT docs-only (default values above)

$mustRows = $sessionRows | Where-Object { $_.Req -eq 'MUST' }
if ($mustRows.Count -eq 0) { Fail 'E_NO_MUST_ROWS' "No MUST rows found in Session End checklist." }

# Metrics: track QA skip types
$script:QaSkipType = $null  # 'docs-only', 'investigation-only', or $null (QA required)

foreach ($row in $mustRows) {
  $stepNorm = Normalize-Step $row.Step

  # Special handling for Commit row: skip during pre-commit since commit hasn't happened yet
  $isCommitRow = $stepNorm -match 'Commit all changes'
  if ($isCommitRow -and $PreCommit) {
    # Pre-commit runs before commit exists; validate commit row in CI only
    continue
  }

  # Special handling for QA row: can be skipped ONLY on docs-only or investigation-only sessions.
  $isQaRow = $stepNorm -match 'Route to qa agent'
  if ($isQaRow) {
    # Check if evidence claims investigation-only skip
    $claimsInvestigationOnly = $row.Evidence -match '(?i)SKIPPED:\s*investigation-only'

    if ($claimsInvestigationOnly) {
      # Validate investigation-only claim
      if ($row.Status -ne 'x') {
        Fail 'E_QA_SKIP_NOT_MARKED' "Investigation-only session: QA may be skipped, but you MUST mark the QA row complete."
      }
      if (-not $investigationResult.IsEligible) {
        # E_INVESTIGATION_HAS_IMPL: Staged files include non-investigation content
        $implFiles = $investigationResult.ImplementationFiles -join ', '
        # Generate allowed directories dynamically from the allowlist
        $allowedDirs = ($script:InvestigationAllowlist | ForEach-Object { "  - " + ($_ -replace '^\^\\', '' -replace '/$', '') }) -join "`n"
        Fail 'E_INVESTIGATION_HAS_IMPL' @"
Investigation-only QA skip claimed but staged files include implementation:
  $implFiles

Investigation sessions may ONLY modify files in these directories:
$allowedDirs

To fix: Either (1) move implementation to a new session, or (2) complete QA validation.
"@
      }
      # Valid investigation-only skip
      $script:QaSkipType = 'investigation-only'
      continue
    }

    if (-not $docsOnly) {
      if ($row.Status -ne 'x') { Fail 'E_QA_REQUIRED' "QA is required (non-doc changes detected). Check the QA row and include QA report path in Evidence." }
      if ($row.Evidence -notmatch '\.agents/qa/.*\.md') { Fail 'E_QA_EVIDENCE' "QA row checked but Evidence missing QA report path under .agents/qa/." }
      $qaPath = $row.Evidence -replace '.*?(\.agents/qa/[^ )\]]+\.md).*','$1'
      $qaFull = Join-Path $repoRoot ($qaPath -replace '/','\')
      if (-not (Test-Path -LiteralPath $qaFull)) { Fail 'E_QA_REPORT_MISSING' "QA report referenced but file not found: $qaPath" }
    } else {
      # docs-only: require explicit SKIPPED evidence and the row checked to avoid silent skips
      if ($row.Status -ne 'x') { Fail 'E_QA_SKIP_NOT_MARKED' "Docs-only session: QA may be skipped, but you MUST mark the QA row complete and set Evidence to 'SKIPPED: docs-only'." }
      if ($row.Evidence -notmatch '(?i)SKIPPED:\s*docs-only') { Fail 'E_QA_SKIP_EVIDENCE' "Docs-only QA skip must be explicit. Evidence should include 'SKIPPED: docs-only'." }
      $script:QaSkipType = 'docs-only'
    }
    continue
  }

  if ($row.Status -ne 'x') {
    Fail 'E_MUST_INCOMPLETE' "MUST checklist item not complete: $($row.Step)"
  }
}

# NOTE: HANDOFF.md link check removed per SESSION-PROTOCOL v1.4
# HANDOFF.md is now READ-ONLY - agents must not modify it.
# Session context goes to session logs and Serena memory instead.

# --- Verify git is clean (skip during pre-commit, which runs before commit)
if (-not $PreCommit) {
  $porcelain = (& git -C $repoRoot status --porcelain)
  if ($porcelain -and $porcelain.Trim().Length -gt 0) {
    Fail 'E_DIRTY_WORKTREE' "git status is not clean. Stage + commit all changes (including .agents/*)."
  }
}

# --- Verify at least one commit since Starting Commit (skip during pre-commit)
if (-not $PreCommit -and $startingCommit) {
  $head = (& git -C $repoRoot rev-parse HEAD).Trim()
  if ($head.StartsWith($startingCommit)) {
    Fail 'E_NO_COMMITS_SINCE_START' "No commits since Starting Commit ($startingCommit)."
  }
}

# --- Verify Commit SHA evidence exists and is valid (skip during pre-commit)
if (-not $PreCommit) {
  $commitRow = $mustRows | Where-Object { (Normalize-Step $_.Step) -match 'Commit all changes' } | Select-Object -First 1
  if (-not $commitRow) { Fail 'E_COMMIT_ROW_MISSING' "Could not find 'Commit all changes' row in MUST checklist." }

  $sha = $null
  if ($commitRow.Evidence -match '(?i)Commit\s+SHA:\s*`?([0-9a-f]{7,40})`?') { $sha = $Matches[1] }
  if (-not $sha) { Fail 'E_COMMIT_SHA_MISSING' "Commit row checked but Evidence missing 'Commit SHA: <sha>'." }

  # Validate commit exists
  & git -C $repoRoot cat-file -e "$sha^{commit}" 2>$null
  if ($LASTEXITCODE -ne 0) { Fail 'E_COMMIT_SHA_INVALID' "Commit SHA not found in git history: $sha" }

  # Ensure session log changed since Starting Commit
  # NOTE: HANDOFF.md check removed per SESSION-PROTOCOL v1.4 (read-only)
  if ($startingCommit) {
    $changed = (& git -C $repoRoot diff --name-only "$startingCommit..HEAD") -split "`r?`n" | Where-Object { $_ -and $_.Trim() -ne '' } | ForEach-Object { $_.Trim() }
    if ($changed -notcontains $sessionRel) { Fail 'E_SESSION_NOT_UPDATED' "Session log was not changed since Starting Commit ($startingCommit): $sessionRel" }
  }
}

# --- Markdown lint
RequireCommand 'npx'
if ($FixMarkdown) {
  & npx markdownlint-cli2 --fix "**/*.md" | Out-Host
  if ($LASTEXITCODE -ne 0) { Fail 'E_MARKDOWNLINT_FIX_FAIL' "markdownlint --fix failed. Resolve lint errors manually." }
}
& npx markdownlint-cli2 "**/*.md" | Out-Host
if ($LASTEXITCODE -ne 0) {
  Fail 'E_MARKDOWNLINT_FAIL' "markdownlint failed. Run: npx markdownlint-cli2 --fix ""**/*.md"""
}

Write-Output ""
Write-Output "OK: Session Protocol validation PASSED"
Write-Output "  Session Start: $($mustStartRows.Count) MUST requirements verified"
Write-Output "  Session End: $($mustRows.Count) MUST requirements verified"
Write-Output "  Session: $sessionRel"
if ($startingCommit) { Write-Output "  StartingCommit: $startingCommit" }
if (-not $PreCommit -and $sha) { Write-Output "  Commit: $sha" }
if ($script:QaSkipType) { Write-Output "  QA Skip: $($script:QaSkipType)" }
exit 0
