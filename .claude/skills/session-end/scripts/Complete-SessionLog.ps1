<#
.SYNOPSIS
  Completes a session log by auto-populating session end evidence and validating.

.DESCRIPTION
  Finds the current session log, auto-populates session end checklist items
  with evidence gathered from git state and file changes, runs validation,
  and reports status. Designed to run before committing session work.

.PARAMETER SessionPath
  Path to the session log JSON file. Auto-detects most recent if not provided.

.PARAMETER DryRun
  Show what would change without writing to the file.

.NOTES
  EXIT CODES:
  0  - Success: Session log completed and validated
  1  - Error: Validation failed or missing required items

  See: ADR-035 Exit Code Standardization

.OUTPUTS
  Validation result with details of completed items.
#>
[CmdletBinding()]
param(
    [string]$SessionPath = '',
    [switch]$DryRun
)

$ErrorActionPreference = 'Stop'

# Get repo root
$repoRoot = Split-Path (Split-Path (Split-Path (Split-Path $PSScriptRoot)))
$sessionsDir = Join-Path $repoRoot '.agents' 'sessions'

#region Find Session Log

function Find-CurrentSessionLog {
    param([string]$SearchDir)

    $today = Get-Date -Format 'yyyy-MM-dd'

    # Look for today's session logs first, then most recent
    $candidates = Get-ChildItem $SearchDir -Filter '*.json' -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -match '^\d{4}-\d{2}-\d{2}-session-\d+' } |
        Sort-Object LastWriteTime -Descending

    if ($candidates.Count -eq 0) {
        return $null
    }

    # Prefer today's sessions
    $todaySessions = $candidates | Where-Object { $_.Name -like "$today*" }
    if ($todaySessions.Count -gt 0) {
        return $todaySessions[0].FullName
    }

    # Fall back to most recent
    return $candidates[0].FullName
}

#endregion

#region Evidence Gathering

function Get-EndingCommit {
    $output = git rev-parse --short HEAD 2>&1
    if ($LASTEXITCODE -ne 0) {
        Write-Warning "Failed to get commit SHA: $output"
        return $null
    }
    return ($output | Out-String).Trim()
}

function Test-HandoffModified {
    # Check staged changes
    $staged = git diff --cached --name-only 2>&1
    if ($LASTEXITCODE -eq 0 -and $staged -match 'HANDOFF\.md') {
        return $true
    }

    # Check unstaged changes
    $unstaged = git diff --name-only 2>&1
    if ($LASTEXITCODE -eq 0 -and $unstaged -match 'HANDOFF\.md') {
        return $true
    }

    return $false
}

function Test-SerenaMemoryUpdated {
    # Check for staged or unstaged changes in memory directory
    $staged = git diff --cached --name-only 2>&1
    $unstaged = git diff --name-only 2>&1
    $untracked = git ls-files --others --exclude-standard 2>&1

    $allChanges = @()
    if ($LASTEXITCODE -eq 0) {
        $allChanges += @($staged) + @($unstaged) + @($untracked)
    }

    $memoryChanges = $allChanges | Where-Object { $_ -like '.serena/memories/*' -or $_ -like '.serena/memories\*' }
    return ($memoryChanges.Count -gt 0)
}

function Invoke-MarkdownLint {
    # Get changed markdown files
    $staged = @(git diff --cached --name-only --diff-filter=ACMR 2>&1 | Where-Object { $_ -like '*.md' })
    $unstaged = @(git diff --name-only --diff-filter=ACMR 2>&1 | Where-Object { $_ -like '*.md' })
    $changedMd = @($staged) + @($unstaged) | Select-Object -Unique | Where-Object { $_ }

    if ($changedMd.Count -eq 0) {
        return @{ Success = $true; Output = 'No markdown files changed' }
    }

    # Run markdownlint on changed files individually to prevent command injection (CWE-78)
    $allOutput = @()
    $allSuccess = $true
    foreach ($file in $changedMd) {
        $lintResult = npx markdownlint-cli2 --fix "$file" 2>&1
        if ($LASTEXITCODE -ne 0) {
            $allSuccess = $false
            $allOutput += ($lintResult | Out-String).Trim()
        }
    }

    return @{
        Success = $allSuccess
        Output = if ($allSuccess) { "$($changedMd.Count) files linted" } else { ($allOutput -join "`n") }
    }
}

function Test-UncommittedChange {
    $status = git status --porcelain 2>&1
    if ($LASTEXITCODE -ne 0) {
        Write-Warning "Failed to check git status: $status"
        return $true
    }
    return ([string]::IsNullOrWhiteSpace(($status | Out-String).Trim()) -eq $false)
}

#endregion

#region Main Logic

# Find session log
if ([string]::IsNullOrWhiteSpace($SessionPath)) {
    $SessionPath = Find-CurrentSessionLog -SearchDir $sessionsDir
    if (-not $SessionPath) {
        Write-Host '[FAIL] No session log found in .agents/sessions/' -ForegroundColor Red
        Write-Host '  Create one first: pwsh .claude/skills/session-init/scripts/New-SessionLogJson.ps1' -ForegroundColor Yellow
        exit 1
    }
    Write-Host "Auto-detected session log: $SessionPath" -ForegroundColor Cyan
} else {
    # Validate path exists and is within the allowed sessions directory (CWE-22 prevention)
    if (-not (Test-Path $SessionPath)) {
        Write-Host "[FAIL] Session file not found: $SessionPath" -ForegroundColor Red
        exit 1
    }
    try {
        $resolvedPath = [IO.Path]::GetFullPath((Resolve-Path -LiteralPath $SessionPath -ErrorAction Stop))
    } catch {
        Write-Host "[FAIL] Session file not found or path is invalid: $SessionPath" -ForegroundColor Red
        exit 1
    }
    $resolvedBase = [IO.Path]::GetFullPath($sessionsDir) + [IO.Path]::DirectorySeparatorChar
    if (-not $resolvedPath.StartsWith($resolvedBase, [StringComparison]::OrdinalIgnoreCase)) {
        Write-Host "[FAIL] Session path must be inside '$sessionsDir'." -ForegroundColor Red
        exit 1
    }
    $SessionPath = $resolvedPath
}

# Read session log
$content = Get-Content $SessionPath -Raw
try {
    $session = $content | ConvertFrom-Json -AsHashtable
} catch {
    Write-Host "[FAIL] Invalid JSON in session file: $SessionPath" -ForegroundColor Red
    Write-Host "  Error: $($_.Exception.Message)" -ForegroundColor Red
    Write-Host '  Fix with: /session-log-fixer' -ForegroundColor Yellow
    exit 1
}

# Verify structure
if (-not $session.ContainsKey('protocolCompliance') -or
    -not $session.protocolCompliance.ContainsKey('sessionEnd')) {
    Write-Host '[FAIL] Session log missing protocolCompliance.sessionEnd section' -ForegroundColor Red
    exit 1
}

$sessionEnd = $session.protocolCompliance.sessionEnd
$changes = @()

Write-Host ''
Write-Host '=== Session End Completion ===' -ForegroundColor Cyan
Write-Host "File: $SessionPath"
Write-Host ''

# 1. Ending commit
$endingCommit = Get-EndingCommit
if ($endingCommit) {
    if ([string]::IsNullOrWhiteSpace($session.endingCommit) -or $session.endingCommit -eq '') {
        $session.endingCommit = $endingCommit
        $changes += "Set endingCommit: $endingCommit"
    }
}

# 2. handoffNotUpdated (MUST NOT - should be false/not-complete)
$handoffModified = Test-HandoffModified
if ($sessionEnd.ContainsKey('handoffNotUpdated')) {
    $check = $sessionEnd.handoffNotUpdated
    if ($handoffModified) {
        $check.Complete = $true  # This will FAIL validation (MUST NOT violated)
        $check.Evidence = 'WARNING: HANDOFF.md was modified - this violates MUST NOT'
        $changes += '[WARN] HANDOFF.md was modified (MUST NOT violation)'
    } else {
        $check.Complete = $false
        $check.Evidence = 'HANDOFF.md not modified (read-only respected)'
        $changes += 'Confirmed HANDOFF.md not modified'
    }
}

# 3. serenaMemoryUpdated
$memoryUpdated = Test-SerenaMemoryUpdated
if ($sessionEnd.ContainsKey('serenaMemoryUpdated')) {
    $check = $sessionEnd.serenaMemoryUpdated
    if ($memoryUpdated) {
        $check.Complete = $true
        $check.Evidence = '.serena/memories/ has changes'
        $changes += 'Confirmed Serena memory updated'
    } elseif (-not $check.Complete) {
        $changes += '[TODO] Serena memory not updated - update .serena/memories/ before completing'
    }
}

# 4. markdownLintRun
Write-Host 'Running markdown lint...' -ForegroundColor Gray
$lintResult = Invoke-MarkdownLint
if ($sessionEnd.ContainsKey('markdownLintRun')) {
    $check = $sessionEnd.markdownLintRun
    $check.Complete = $lintResult.Success
    $check.Evidence = $lintResult.Output
    $changes += "Markdown lint: $($lintResult.Output)"
}

# 5. changesCommitted
$hasUncommitted = Test-UncommittedChange
if ($sessionEnd.ContainsKey('changesCommitted')) {
    $check = $sessionEnd.changesCommitted
    if (-not $hasUncommitted) {
        $check.Complete = $true
        $check.Evidence = "All changes committed (HEAD: $endingCommit)"
        $changes += 'All changes committed'
    } else {
        $changes += '[TODO] Uncommitted changes exist - commit before completing'
    }
}

# 6. checklistComplete - evaluate after all others
$mustItems = @('handoffNotUpdated', 'serenaMemoryUpdated', 'markdownLintRun', 'changesCommitted', 'validationPassed')
$allMustComplete = $true
foreach ($item in $mustItems) {
    if ($sessionEnd.ContainsKey($item)) {
        $check = $sessionEnd[$item]
        $level = if ($check.ContainsKey('level')) { $check.level } else { '' }
        $isComplete = if ($check.ContainsKey('Complete')) { $check.Complete } else { $false }

        if ($level -eq 'MUST' -and -not $isComplete) {
            $allMustComplete = $false
        }
        # MUST NOT items should NOT be complete
        if ($level -eq 'MUST NOT' -and $isComplete) {
            $allMustComplete = $false
        }
    }
}

if ($sessionEnd.ContainsKey('checklistComplete')) {
    $check = $sessionEnd.checklistComplete
    $check.Complete = $allMustComplete
    $check.Evidence = if ($allMustComplete) { 'All MUST items verified' } else { 'Some MUST items still incomplete' }
}

# Report changes
Write-Host ''
Write-Host '--- Changes ---' -ForegroundColor Cyan
foreach ($change in $changes) {
    $color = if ($change -like '*TODO*') { 'Yellow' } `
        elseif ($change -like '*WARN*') { 'Red' } `
        else { 'Green' }
    Write-Host "  $change" -ForegroundColor $color
}

# Write updated session log
if (-not $DryRun) {
    $session | ConvertTo-Json -Depth 10 | Set-Content $SessionPath -Encoding utf8
    Write-Host ''
    Write-Host "Updated: $SessionPath" -ForegroundColor Green
} else {
    Write-Host ''
    Write-Host '[DRY RUN] No changes written' -ForegroundColor Yellow
}

# Run validation
Write-Host ''
Write-Host 'Running validation...' -ForegroundColor Cyan
$validateScript = Join-Path $repoRoot 'scripts' 'validate_session_json.py'

if (Test-Path $validateScript) {
    & python3 $validateScript $SessionPath
    $validationExitCode = $LASTEXITCODE

    # Update validationPassed based on result
    if (-not $DryRun -and $sessionEnd.ContainsKey('validationPassed')) {
        $check = $sessionEnd.validationPassed
        $check.Complete = ($validationExitCode -eq 0)
        $check.Evidence = if ($validationExitCode -eq 0) { 'validate_session_json.py passed' } else { 'validate_session_json.py failed' }

        # Re-evaluate checklistComplete
        if ($validationExitCode -eq 0 -and $allMustComplete) {
            $sessionEnd.checklistComplete.Complete = $true
            $sessionEnd.checklistComplete.Evidence = 'All MUST items verified and validation passed'
        }

        # Write final state
        $session | ConvertTo-Json -Depth 10 | Set-Content $SessionPath -Encoding utf8
    }

    if ($validationExitCode -ne 0) {
        Write-Host ''
        Write-Host '[FAIL] Session validation failed. Fix issues above and re-run.' -ForegroundColor Red
        exit 1
    }
} else {
    Write-Warning "Validation script not found: $validateScript"
}

Write-Host ''
Write-Host '[PASS] Session log completed and validated' -ForegroundColor Green
exit 0

#endregion
