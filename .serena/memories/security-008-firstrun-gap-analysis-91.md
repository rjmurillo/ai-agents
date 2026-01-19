# Security: Firstrun Gap Analysis 91

## Skill-Security-008: First-Run Gap Analysis (91%)

**Statement**: When reviewing conditional security checks, verify they cover creation scenarios, not just modification scenarios

**Context**: When security code uses existence checks (`if file exists then validate`)

**Evidence**: PR #52 - `if (Test-Path $DestinationPath)` meant symlink check only ran on updates, not creates

**Atomicity**: 91%

**Tag**: helpful (security)

**Impact**: 8/10

**Pattern**:

```powershell
# WRONG: Only validates when file exists
if (Test-Path $Path) {
    if ((Get-Item $Path).LinkType) { throw "symlink" }
}
# First-run creates file without validation!

# RIGHT: Validate after creation too
$result = Create-File $Path
if ((Get-Item $Path).LinkType) { throw "symlink" }
```

**Source**: `.agents/retrospective/pr-52-symlink-retrospective.md`

---

## Related

- [security-001-twophase-security-review](security-001-twophase-security-review.md)
- [security-002-input-validation-first-88](security-002-input-validation-first-88.md)
- [security-002-input-validation-first](security-002-input-validation-first.md)
- [security-003-secure-error-handling-90](security-003-secure-error-handling-90.md)
- [security-003-secure-error-handling](security-003-secure-error-handling.md)
