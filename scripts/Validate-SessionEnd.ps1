<#
.SYNOPSIS
  Validates Session End protocol compliance for a single session log.

.DESCRIPTION
  Verification-based enforcement for Session End, as defined in .agents/SESSION-PROTOCOL.md.

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
  $root = (& git -C $StartDir rev-parse --show-toplevel 2>$null)
  if (-not $root) { Fail 'E_GIT_ROOT' "Could not find git repo root from: $StartDir" }
  return $root.Trim()
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

function Parse-ChecklistTable([string[]]$TableLines) {
  # Returns ordered rows: @{ Req = 'MUST'; Step='...'; Status='x'/' '; Evidence='...' }
  $rows = New-Object System.Collections.Generic.List[hashtable]
  foreach ($line in $TableLines) {
    if ($line -match '^\|\s*-+\s*\|') { continue } # separator row
    if ($line -match '^\|\s*Req\s*\|') { continue } # header row

    # Split 4 columns, trimming outer pipes.
    $parts = ($line.Trim() -replace '^\|','' -replace '\|$','').Split('|') | ForEach-Object { $_.Trim() }
    if ($parts.Count -lt 4) { continue }

    $req = ($parts[0] -replace '\*','').Trim().ToUpperInvariant()
    $step = $parts[1].Trim()
    $statusRaw = $parts[2].Trim()
    $evidence = $parts[3].Trim()

    $status = ' '
    if ($statusRaw -match '\[\s*[xX]\s*\]') { $status = 'x' }

    $rows.Add(@{ Req = $req; Step = $step; Status = $status; Evidence = $evidence; Raw = $line })
  }
  return $rows.ToArray()
}

function Normalize-Step([string]$s) {
  return ($s -replace '\s+',' ' -replace '\*','').Trim()
}

# --- Load inputs
$sessionFullPath = (Resolve-Path -LiteralPath $SessionLogPath).Path
$repoRoot = Get-RepoRoot (Split-Path -Parent $sessionFullPath)

# Security: Validate session log is under expected directory (CWE-22, see #214)
# Normalize paths and add trailing separator to prevent prefix bypass (e.g., .agents/sessions-evil)
$expectedDir = Join-Path $repoRoot ".agents" "sessions"
$expectedDirNormalized = [System.IO.Path]::GetFullPath($expectedDir).TrimEnd('\','/')
$expectedDirWithSep = $expectedDirNormalized + [System.IO.Path]::DirectorySeparatorChar
$sessionFullPathNormalized = [System.IO.Path]::GetFullPath($sessionFullPath)
if (-not $sessionFullPathNormalized.StartsWith($expectedDirWithSep, [System.StringComparison]::OrdinalIgnoreCase)) {
  Fail 'E_PATH_ESCAPE' "Session log must be under .agents/sessions/: $sessionFullPath"
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
# Determine doc-only vs code/config changes.
# Pre-commit mode: check staged files (what's actually being committed)
# Normal mode: check diff from Starting Commit to HEAD (session's full change set)

function Is-DocsOnly([string[]]$Files) {
  if (-not $Files -or $Files.Count -eq 0) { return $false } # No files = cannot prove docs-only
  foreach ($f in $Files) {
    $ext = [IO.Path]::GetExtension($f).ToLowerInvariant()
    if ($ext -ne '.md') { return $false }
  }
  return $true
}

# Extract Starting Commit from session log (needed for later validations)
$startingCommit = $null
if ($sessionText -match '(?m)^\s*-\s*\*\*Starting Commit\*\*\s*:\s*`?([0-9a-f]{7,40})`?\s*$') {
  $startingCommit = $Matches[1]
} elseif ($sessionText -match '(?m)^\s*Starting Commit\s*:\s*([0-9a-f]{7,40})\s*$') {
  $startingCommit = $Matches[1]
}

$changedFiles = @()
$docsOnly = $false

if ($PreCommit) {
  # Pre-commit: check only staged files (fixes false positive on docs-only commits)
  # Issue #551: Without this, docs-only commits would be detected as "non-doc changes"
  # because git diff $startingCommit..HEAD includes all session changes, not just staged files
  try {
    $stagedFiles = @((& git -C $repoRoot diff --staged --name-only) -split "`r?`n" | Where-Object { $_ -and $_.Trim() -ne '' })
    if ($stagedFiles.Count -gt 0) {
      $changedFiles = $stagedFiles
      $docsOnly = Is-DocsOnly $stagedFiles
    }
  } catch {
    # If staged files check fails, fall back to conservative (not docs-only)
    $docsOnly = $false
  }
} elseif ($startingCommit) {
  # Normal mode: use Starting Commit to HEAD diff
  try {
    # Wrap in @() to ensure result is always an array (fixes Count property error when single file)
    $changedFiles = @((& git -C $repoRoot diff --name-only "$startingCommit..HEAD") -split "`r?`n" | Where-Object { $_ -and $_.Trim() -ne '' })
    if ($changedFiles.Count -gt 0) {
      $docsOnly = Is-DocsOnly $changedFiles
    }
  } catch {
    Fail 'E_GIT_DIFF_FAIL' "Could not compute changed files from Starting Commit $startingCommit. Ensure Starting Commit is valid."
  }
}

$mustRows = $sessionRows | Where-Object { $_.Req -eq 'MUST' }
if ($mustRows.Count -eq 0) { Fail 'E_NO_MUST_ROWS' "No MUST rows found in Session End checklist." }

foreach ($row in $mustRows) {
  $stepNorm = Normalize-Step $row.Step

  # Special handling for QA row: can be skipped ONLY on docs-only sessions, but must be explicitly marked.
  $isQaRow = $stepNorm -match 'Route to qa agent'
  if ($isQaRow) {
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
    }
    continue
  }

  if ($row.Status -ne 'x') {
    Fail 'E_MUST_INCOMPLETE' "MUST checklist item not complete: $($row.Step)"
  }
}

# --- Verify HANDOFF contains a link to this session log
# Skip on feature branches: HANDOFF.md is read-only per ADR-014/SESSION-PROTOCOL v1.4
$currentBranch = (& git -C $repoRoot branch --show-current).Trim()
$isMainBranch = $currentBranch -eq 'main'

if ($isMainBranch) {
  $handoffPath = Join-Path $repoRoot ".agents/HANDOFF.md"
  if (-not (Test-Path -LiteralPath $handoffPath)) { Fail 'E_HANDOFF_MISSING' "Missing .agents/HANDOFF.md" }
  $handoff = Read-AllText $handoffPath

  # Accept either [Session NN](./sessions/...) or raw path.
  if ($handoff -notmatch [Regex]::Escape(($sessionRel -replace '^\.agents/',''))) {
    # The typical link omits ".agents/" prefix (because HANDOFF lives in .agents/)
    $relFromHandoff = $sessionRel -replace '^\.agents/',''
    if ($handoff -notmatch [Regex]::Escape($relFromHandoff)) {
      Fail 'E_HANDOFF_LINK_MISSING' "HANDOFF.md does not reference this session log: $relFromHandoff"
    }
  }
}

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

  # Ensure session + handoff changed since Starting Commit (stronger than single-commit containment)
  if ($startingCommit) {
    $changed = (& git -C $repoRoot diff --name-only "$startingCommit..HEAD") -split "`r?`n" | Where-Object { $_ -and $_.Trim() -ne '' } | ForEach-Object { $_.Trim() }
    if ($changed -notcontains ".agents/HANDOFF.md") { Fail 'E_HANDOFF_NOT_UPDATED' "HANDOFF.md was not changed since Starting Commit ($startingCommit)." }
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

Write-Output "OK: Session End validation passed"
Write-Output "Session: $sessionRel"
if ($startingCommit) { Write-Output "StartingCommit: $startingCommit" }
if (-not $PreCommit -and $sha) { Write-Output "Commit: $sha" }
exit 0
