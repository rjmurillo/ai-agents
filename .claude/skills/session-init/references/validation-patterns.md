# Validation Patterns

How to validate session logs and handle common issues.

---

## Validation Script

**Script**: `scripts/Validate-SessionJson.ps1`

### Basic Usage

```powershell
pwsh scripts/Validate-SessionJson.ps1 `
    -SessionPath ".agents/sessions/.agents/sessions/2026-01-05-session-375.json" `
    
```

### CI Mode

For GitHub Actions:

```powershell
pwsh scripts/Validate-SessionJson.ps1 `
    -SessionPath ".agents/sessions/.agents/sessions/2026-01-05-session-375.json" `
     `
    -CI
```

---

## Exit Codes

| Code | Meaning | Action |
|------|---------|--------|
| 0 | PASS - All MUST requirements met | Proceed with session |
| 1 | FAIL - One or more MUST requirements failed | Fix issues before proceeding |

---

## Output Format (Markdown)

```markdown
# Session Protocol Validation Report

**Date**: 2026-01-05 23:10
**RFC 2119**: MUST = error, SHOULD = warning

## Session: 2026-01-05-session-375.md

**Status**: PASSED

### Validation Results

| Check | Level | Status | Issues |
|-------|-------|--------|--------|
| HandoffUpdated | MUST | PASS | - |
| ProtocolComplianceSection | MUST | PASS | - |
| ShouldRequirements | SHOULD | PASS | - |
| CommitEvidence | MUST | PASS | - |
| MustNotRequirements |  | PASS | - |
| MustRequirements | MUST | PASS | - |
| SessionLogExists | MUST | PASS | - |
| SessionLogCompleteness | SHOULD | PASS | - |
```

---

## Common Validation Failures

### 1. Missing Session End Checklist Header

**Error**:

```text
| ProtocolComplianceSection | MUST | FAIL | Missing Session End checklist header |
```

**Cause**: Session End header is `## Session End` instead of `### Session End (COMPLETE ALL before closing)`

**Fix**:

```markdown
### Session End (COMPLETE ALL before closing)
```

### 2. Missing Protocol Compliance Section

**Error**:

```text
| ProtocolComplianceSection | MUST | FAIL | Missing Protocol Compliance section |
```

**Cause**: Session log does not have `## Protocol Compliance` section

**Fix**: Add the Protocol Compliance section from the template

### 3. Missing Session Start Checklist

**Error**:

```text
| ProtocolComplianceSection | MUST | FAIL | Missing Session Start checklist header |
```

**Cause**: Session Start header is incorrect or missing

**Fix**:

```markdown
### Session Start (COMPLETE ALL before work)
```

### 4. Incomplete Session Log

**Error**:

```text
| SessionLogCompleteness | SHOULD | FAIL | Missing section: Session Info; Missing section: Work Log |
```

**Cause**: Template sections were not included

**Fix**: Ensure all template sections are present:

- Session Info
- Protocol Compliance
- Work Log
- Session End

---

## Validation Checks Explained

### ProtocolComplianceSection (MUST)

Checks for:

1. `## Protocol Compliance` heading exists
2. `### Session Start (COMPLETE ALL before work)` header
3. `### Session End (COMPLETE ALL before closing)` header

Regex patterns:

```regex
# Session Start
(?i)Session\s+Start.*COMPLETE\s+ALL|Start.*before.*work

# Session End
(?i)Session\s+End.*COMPLETE\s+ALL|End.*before.*closing
```

### SessionLogCompleteness (SHOULD)

Checks for required sections:

```powershell
$expectedSections = @(
    @{ Pattern = '(?i)##\s*Session\s+Info'; Name = 'Session Info' }
    @{ Pattern = '(?i)##\s*Protocol\s+Compliance'; Name = 'Protocol Compliance' }
    @{ Pattern = '(?i)##\s*Work\s+Log|##\s*Tasks?\s+Completed'; Name = 'Work Log' }
    @{ Pattern = '(?i)##\s*Session\s+End|Session\s+End.*COMPLETE'; Name = 'Session End' }
)
```

### HandoffUpdated (MUST)

Verifies HANDOFF.md was NOT modified (read-only policy).

### CommitEvidence (MUST)

Checks for commit SHA evidence in the session log.

---

## Self-Validation Script

For session-init skill, run validation immediately after creating the session log:

```powershell
$sessionPath = ".agents/sessions/.agents/sessions/2026-01-05-session-375.json"

# Run validation
$result = & pwsh scripts/Validate-SessionJson.ps1 `
    -SessionPath $sessionPath `
    

$exitCode = $LASTEXITCODE

if ($exitCode -eq 0) {
    Write-Host "Session log validated successfully" -ForegroundColor Green
} else {
    Write-Host "Validation failed:" -ForegroundColor Red
    Write-Host $result
    exit 1
}
```

---

## Debugging Validation Issues

### View Full Validation Output

```powershell
pwsh scripts/Validate-SessionJson.ps1 `
    -SessionPath ".agents/sessions/.agents/sessions/2026-01-05-session-375.json" `
     `
    -Verbose
```

### Check Specific Patterns

```powershell
$content = Get-Content -Path ".agents/sessions/.agents/sessions/2026-01-05-session-375.json" -Raw

# Check Session End header
if ($content -match '(?i)Session\s+End.*COMPLETE\s+ALL') {
    Write-Host "Session End header: OK"
} else {
    Write-Host "Session End header: MISSING REQUIRED TEXT"
}
```

---

## Prevention vs. Remediation

| Approach | Tool | When |
|----------|------|------|
| **Prevention** | session-init skill | Session creation |
| **Remediation** | session-log-fixer skill | After CI failure |

Always prefer prevention. Use session-init skill to create session logs.
