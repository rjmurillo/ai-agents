<#
.SYNOPSIS
Validates Session End protocol compliance in session logs.

.DESCRIPTION
Checks session log for Session End checklist completion per SESSION-PROTOCOL.md.
Verifies:
- Session End section exists with correct format
- All MUST requirements are checked [x]
- Required evidence is present

Exits with code 0 (PASS) or 1 (FAIL).

.PARAMETER SessionLogPath
Path to session log markdown file to validate.

.EXAMPLE
.\scripts\Validate-SessionEnd.ps1 -SessionLogPath ".agents/sessions/2025-12-20-session-44.md"

.NOTES
Part of Session Protocol enforcement (SESSION-PROTOCOL.md).
Used by pre-commit git hook and orchestrator handoff validation.
#>

param(
    [Parameter(Mandatory=$true)]
    [string]$SessionLogPath
)

# Verify file exists
if (-not (Test-Path $SessionLogPath)) {
    Write-Error "Session log not found: $SessionLogPath"
    exit 1
}

$content = Get-Content $SessionLogPath -Raw

# Check 1: Session End section exists with correct format
$sessionEndPattern = "## Session End.*\(COMPLETE ALL before closing\)"
if ($content -notmatch $sessionEndPattern) {
    Write-Error "❌ FAIL: Session End section missing or incorrect format"
    Write-Error "   Expected: '## Session End (COMPLETE ALL before closing)'"
    Write-Error "   Session: $SessionLogPath"
    exit 1
}

# Check 2: MUST requirements checklist format
# These are from SESSION-PROTOCOL.md lines 300-313
# Supports both table format (canonical) and checkbox format
$mustRequirements = @(
    @{
        # Matches table row: | MUST | Update `.agents/HANDOFF.md` ... | [x] |
        # OR checkbox format: - [x] Update HANDOFF.md
        Pattern = "(?:MUST.*Update.*HANDOFF\.md.*\[x\])|(?:\[x\].*Update.*HANDOFF\.md)"
        Name = "Update HANDOFF.md"
    },
    @{
        Pattern = "(?:MUST.*Complete session log.*\[x\])|(?:\[x\].*Complete session log)"
        Name = "Complete session log"
    },
    @{
        Pattern = "(?:MUST.*markdown lint.*\[x\])|(?:\[x\].*markdown lint)"
        Name = "Run markdown lint"
    },
    @{
        Pattern = "(?:MUST.*Commit.*changes.*\[x\])|(?:\[x\].*Commit.*changes)|(?:Commit SHA:.*[a-f0-9]{7})"
        Name = "Commit all changes"
    }
)

$failures = @()

foreach ($req in $mustRequirements) {
    if ($content -notmatch $req.Pattern) {
        $failures += $req.Name
    }
}

if ($failures.Count -gt 0) {
    Write-Error "❌ FAIL: Session End MUST requirements incomplete"
    Write-Error "   Session: $SessionLogPath"
    Write-Error ""
    Write-Error "   Unchecked requirements:"
    foreach ($failure in $failures) {
        Write-Error "   - $failure"
    }
    Write-Error ""
    Write-Error "   Fix: Mark all checkboxes [x] in Session End section"
    exit 1
}

# Check 3: Evidence present (commit SHA if commit is checked)
if ($content -match "\[x\].*Commit all changes") {
    if ($content -notmatch "Commit SHA:.*[a-f0-9]{7,40}") {
        Write-Error "❌ FAIL: Commit checkbox marked but no commit SHA documented"
        Write-Error "   Session: $SessionLogPath"
        Write-Error "   Fix: Add 'Commit SHA: <sha>' below checklist"
        exit 1
    }
}

Write-Output "✅ PASS: Session End validation complete"
Write-Output "   Session: $SessionLogPath"
Write-Output "   All MUST requirements checked"
exit 0
