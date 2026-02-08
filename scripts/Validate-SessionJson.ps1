<#
.SYNOPSIS
  Validates session logs in JSON format against schema.

.DESCRIPTION
  Simple, unambiguous validation using JSON schema instead of regex parsing.

.PARAMETER SessionPath
  Path to the session log JSON file.

.PARAMETER PreCommit
  Suppress verbose output when called from pre-commit hook.

.NOTES
  EXIT CODES:
  0  - Success: Session log is valid
  1  - Error: Session log validation failed (invalid JSON, missing fields, or schema violations)

  See: ADR-035 Exit Code Standardization

.OUTPUTS
  Boolean validation result with detailed error messages
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory)]
    [string]$SessionPath,

    [switch]$PreCommit
)

$ErrorActionPreference = 'Stop'

# Load session log
if (-not (Test-Path $SessionPath)) {
    Write-Error "Session file not found: $SessionPath"
    exit 1
}

$content = Get-Content $SessionPath -Raw
try {
    $session = $content | ConvertFrom-Json -AsHashtable
} catch {
    Write-Error "Invalid JSON in session file: $SessionPath"

    # Extract line/column information if available
    if ($_.Exception.Message -match 'line (\d+).*position (\d+)') {
        $line = $Matches[1]
        $pos = $Matches[2]
        Write-Error "Syntax error at line $line, position $pos"

        # Show context
        $lines = $content -split "`n"
        if ($line -le $lines.Count) {
            Write-Error "Near: $($lines[$line-1])"
        }
    }

    Write-Error "Error details: $($_.Exception.Message)"
    Write-Error ""
    Write-Error "Common fixes:"
    Write-Error "  - Remove trailing commas from arrays/objects"
    Write-Error "  - Ensure all strings are properly quoted"
    Write-Error "  - Validate JSON structure with: Get-Content '$SessionPath' | ConvertFrom-Json"
    exit 1
}

# Helper to get value case-insensitively
function Get-Key {
    param($Hash, $Key)
    foreach ($k in $Hash.Keys) {
        if ($k -ieq $Key) { return $Hash[$k] }
    }
    return $null
}

$errors = @()
$warnings = @()

# Required top-level
if (-not $session.ContainsKey('session')) { $errors += 'Missing: session' }
if (-not $session.ContainsKey('protocolCompliance')) { $errors += 'Missing: protocolCompliance' }

if ($session.ContainsKey('session')) {
    $s = $session.session

    # Required session fields
    @('number', 'date', 'branch', 'startingCommit', 'objective') | ForEach-Object {
        if (-not $s.ContainsKey($_) -or [string]::IsNullOrWhiteSpace($s[$_])) {
            $errors += "Missing: session.$_"
        }
    }

    # Branch pattern
    if ($s.branch -and $s.branch -notmatch '^(feat|fix|docs|chore|refactor|test|ci)/') {
        $warnings += "Branch '$($s.branch)' doesn't follow conventional naming"
    }

    # Commit SHA format
    if ($s.startingCommit -and $s.startingCommit -notmatch '^[a-f0-9]{7,40}$') {
        $errors += "Invalid commit SHA format: $($s.startingCommit)"
    }

    # Session number must match filename (CWE-362: detect race condition artifacts)
    $sessionFileName = [System.IO.Path]::GetFileNameWithoutExtension($SessionPath)
    if ($sessionFileName -match 'session-(\d+)') {
        $fileNumber = [int]$Matches[1]
        $jsonNumber = $s.number
        if ($jsonNumber -and $fileNumber -ne $jsonNumber) {
            $errors += "Session number mismatch: filename has $fileNumber but JSON has $jsonNumber"
        }
    }

    # Session number uniqueness check (defense-in-depth for CWE-362)
    $sessionsDir = Split-Path $SessionPath
    if (Test-Path $sessionsDir) {
        $thisNumber = $s.number
        if ($thisNumber) {
            $resolvedSessionPath = [System.IO.Path]::GetFullPath($SessionPath)
            $duplicates = @(Get-ChildItem $sessionsDir -Filter '*.json' |
                Where-Object { $_.FullName -ne $resolvedSessionPath } |
                Where-Object { $_.Name -match 'session-(\d+)' -and [int]$Matches[1] -eq $thisNumber })
            if ($duplicates.Count -gt 0) {
                $errors += "Duplicate session number $thisNumber found in: $($duplicates.Name -join ', ')"
            }
        }
    }
}

if ($session.ContainsKey('protocolCompliance')) {
    $pc = $session.protocolCompliance

    # Session Start MUST items
    if ($pc.ContainsKey('sessionStart')) {
        $mustItems = @('serenaActivated', 'serenaInstructions', 'handoffRead', 'sessionLogCreated', 'branchVerified', 'notOnMain')
        foreach ($item in $mustItems) {
            if ($pc.sessionStart.ContainsKey($item)) {
                $check = $pc.sessionStart[$item]
                $isComplete = Get-Key $check 'complete'
                $evidence = Get-Key $check 'evidence'
                $level = Get-Key $check 'level'
                if ($level -eq 'MUST' -and -not $isComplete) {
                    $errors += "Incomplete MUST: sessionStart.$item"
                }
                if ($level -eq 'MUST' -and $isComplete -and [string]::IsNullOrWhiteSpace($evidence)) {
                    $warnings += "Missing evidence: sessionStart.$item"
                }
            }
        }
    } else {
        $errors += 'Missing: protocolCompliance.sessionStart'
    }

    # Session End MUST items
    if ($pc.ContainsKey('sessionEnd')) {
        $mustItems = @('checklistComplete', 'handoffNotUpdated', 'serenaMemoryUpdated', 'markdownLintRun', 'changesCommitted', 'validationPassed')
        foreach ($item in $mustItems) {
            if ($pc.sessionEnd.ContainsKey($item)) {
                $check = $pc.sessionEnd[$item]
                $isComplete = Get-Key $check 'complete'
                $evidence = Get-Key $check 'evidence'
                $level = Get-Key $check 'level'
                if ($level -eq 'MUST' -and -not $isComplete) {
                    $errors += "Incomplete MUST: sessionEnd.$item"
                }
                if ($level -eq 'MUST' -and $isComplete -and [string]::IsNullOrWhiteSpace($evidence)) {
                    $warnings += "Missing evidence: sessionEnd.$item"
                }
            }
        }

        # MUST NOT check (handoff should NOT be updated)
        if ($pc.sessionEnd.ContainsKey('handoffNotUpdated')) {
            $check = $pc.sessionEnd.handoffNotUpdated
            $isComplete = Get-Key $check 'complete'
            $level = Get-Key $check 'level'
            if ($level -eq 'MUST NOT' -and $isComplete) {
                $errors += "MUST NOT violated: handoffNotUpdated should be false (HANDOFF.md is read-only)"
            }
        }
    } else {
        $errors += 'Missing: protocolCompliance.sessionEnd'
    }
}

# Investigation-Only Mode Validation (ADR-034)
# Check for "SKIPPED: investigation-only" pattern in any evidence field
$investigationOnly = $false
if ($session.ContainsKey('protocolCompliance')) {
    $pc = $session.protocolCompliance

    # Check all sessionEnd evidence fields for investigation-only pattern
    if ($pc.ContainsKey('sessionEnd')) {
        foreach ($key in $pc.sessionEnd.Keys) {
            $check = $pc.sessionEnd[$key]
            $evidence = Get-Key $check 'Evidence'
            if ($evidence -match '(?i)SKIPPED:\s*investigation-only') {
                $investigationOnly = $true
                break
            }
        }
    }
}

# If investigation-only mode is claimed, validate staged files against allowlist
if ($investigationOnly) {
    # Import shared allowlist module (single source of truth per Issue #840)
    Import-Module (Join-Path $PSScriptRoot 'modules' 'InvestigationAllowlist.psm1') -Force

    # Get staged files with error handling
    $gitOutput = @(git diff --cached --name-only 2>&1)
    if ($LASTEXITCODE -ne 0) {
        $errors += @"
E_GIT_COMMAND_FAILED: Failed to list staged files for investigation-only validation.
  git exit code: $LASTEXITCODE
  git output:
  $($gitOutput -join "`n  ")
"@
        $stagedFiles = @()
    } else {
        $stagedFiles = @($gitOutput)
    }

    # Filter for files not in allowlist
    $implementationFiles = @($stagedFiles | Where-Object { -not (Test-FileMatchesAllowlist -FilePath $_) })

    if ($implementationFiles.Count -gt 0) {
        $allowedDisplay = Get-InvestigationAllowlistDisplay
        $errorMsg = @"
E_INVESTIGATION_HAS_IMPL: Investigation skip claimed but staged files contain implementation artifacts:
  $($implementationFiles -join "`n  ")

Investigation sessions may only stage:
  $($allowedDisplay | ForEach-Object { "- $_ " } | Out-String)
Remove implementation artifacts or obtain QA validation.
"@
        $errors += $errorMsg
    } else {
        # Track metrics for investigation-only skips
        if (-not $PreCommit) {
            Write-Verbose "Investigation-only skip: $($stagedFiles.Count) files"
        }
    }
}

# Output
if (-not $PreCommit) {
    Write-Host "`n=== Session Validation ===" -ForegroundColor Cyan
    Write-Host "File: $SessionPath"
}

if ($errors.Count -eq 0) {
    if (-not $PreCommit) {
        Write-Host "`n[PASS] Session log is valid" -ForegroundColor Green
    }
} else {
    if ($PreCommit) {
        Write-Host "Session validation FAILED:" -ForegroundColor Red
        $errors | ForEach-Object { Write-Host "  $_" }
    } else {
        Write-Host "`n[FAIL] Validation errors:" -ForegroundColor Red
        $errors | ForEach-Object { Write-Host "  - $_" -ForegroundColor Red }
    }
}

if ($warnings.Count -gt 0 -and -not $PreCommit) {
    Write-Host "`n[WARN] Warnings:" -ForegroundColor Yellow
    $warnings | ForEach-Object { Write-Host "  - $_" -ForegroundColor Yellow }
}

exit ($errors.Count -gt 0 ? 1 : 0)
