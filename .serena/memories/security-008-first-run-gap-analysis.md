# Skill-Security-008: First-Run Gap Analysis

**Statement**: When reviewing conditional security checks, verify they cover creation scenarios, not just modification scenarios.

**Context**: When security code uses existence checks (`if file exists then validate`)

**Evidence**: PR #52 - `if (Test-Path $DestinationPath)` meant symlink check only ran on updates, not creates

**Atomicity**: 91%

**Pattern**:

```powershell
# WRONG: Only validates when file exists
if (Test-Path $Path) {
    if ((Get-Item $Path).LinkType) { throw "symlink" }
}
# First-run creates file without validation!

# RIGHT: Validate after creation too
$result = Create-File $Path
if ((Get-Item $Path).LinkType) { throw "symlink detected" }
```

**Checklist**:

- [ ] Does security check run on file creation?
- [ ] Does security check run on file modification?
- [ ] Does security check run on file deletion?
- [ ] Is there a gap between check and action?

**Source**: `.agents/retrospective/pr-52-symlink-retrospective.md`
