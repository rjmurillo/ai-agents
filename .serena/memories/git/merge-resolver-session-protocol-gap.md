# Merge-Resolver: Session Protocol Validation Gap

## Root Cause Analysis (2025-12-27)

**Issue**: User reports "template sync check often fails after merge conflict resolution"

**Reality**: Template sync check PASSES. Session Protocol Validation FAILS.

## The Misdiagnosis

### User's Mental Model (INCORRECT)
- Merge conflict resolution → Template sync check fails → CI blocked

### Actual Pattern (VERIFIED)
- Merge conflict resolution → Session protocol incomplete → CI blocked
- Template sync validation: **PASSED** in PR #246
- Session protocol validation: **FAILED** (9 MUST violations)

## Evidence: PR #246

### Checks Status
- `Validate Generated Files`: **PASS** (10s)
- `Aggregate Results (Session Protocol)`: **FAIL** (16s)

### Session Violations
- `session-64-guardrails-premortem.md`: 3 MUST failures
- `session-64a-guardrails-task-validation.md`: 3 MUST failures
- `session-65-guardrails-analyst-critique.md`: 3 MUST failures

### Pattern
Session logs from merge resolution work did NOT complete Session End requirements:
- [ ] Session End checklist incomplete
- [ ] Protocol Compliance section not filled
- [ ] Evidence not recorded
- [ ] Memory not updated

## The Gap in Merge-Resolver Workflow

### Current Workflow
```
1. Fetch PR context
2. Identify conflicts
3. Auto-resolve templates (accept main)
4. git push ← MISSING: Session protocol validation
```

### Missing Pre-Check

Before push, merge-resolver MUST verify:
- [ ] Session log exists at `.agents/sessions/YYYY-MM-DD-session-NN.json`
- [ ] Session End checklist completed
- [ ] Protocol Compliance section complete
- [ ] Evidence recorded (commit SHA, validation result)
- [ ] Memory updated
- [ ] `pwsh scripts/Validate-SessionEnd.ps1` passed

## Template Auto-Resolution (WORKS CORRECTLY)

### Auto-Resolvable Patterns
From `Resolve-PRConflicts.ps1` lines 93-96:
```powershell
'templates/*',
'templates/*/*',
'templates/*/*/*',
```

### Process
1. Detect template conflict
2. Accept main branch version (`git checkout --theirs`)
3. Regenerate platform outputs (copilot-cli, vs-code-agents)
4. Commit resolved files

**Status**: ✓ WORKING AS DESIGNED

Evidence: PR #246 template validation passed

## Recommendations

### P0: Add Session Protocol Gate to Merge-Resolver

**Location**: `.claude/skills/merge-resolver/scripts/Resolve-PRConflicts.ps1`

**Before push**:
```powershell
# Validate session protocol compliance
$sessionLog = Get-ChildItem -Path ".agents/sessions" -Filter "*-session-*.md" | Sort-Object LastWriteTime -Descending | Select-Object -First 1

if ($sessionLog) {
    $validationResult = & ./scripts/Validate-SessionEnd.ps1 -SessionLogPath $sessionLog.FullName
    if ($LASTEXITCODE -ne 0) {
        throw "Session protocol validation failed. Complete session requirements before pushing."
    }
}
```

### P1: Document Session Protocol in Merge-Resolver

**Add to** `.claude/skills/merge-resolver/SKILL.md`:

```markdown
## Step 7: Validate Session Protocol

Before pushing resolved conflicts, verify session requirements:

- Session log created
- Protocol Compliance section complete
- Session End checklist checked
- Evidence recorded
- Memory updated
- Validation script passed

Use: `pwsh scripts/Validate-SessionEnd.ps1 -SessionLogPath ".agents/sessions/[log].md"`
```

### P2: Update Merge-Resolver Memory Pattern

**Add to** `merge-resolver-auto-resolvable-patterns.md`:

```markdown
## Session Protocol Requirements

After resolving conflicts, MUST complete before push:
1. Session log at `.agents/sessions/YYYY-MM-DD-session-NN.json`
2. Protocol Compliance section (all checkboxes)
3. Session End checklist
4. Evidence (commit SHA, validation result)
5. Memory updated
6. Validation: `pwsh scripts/Validate-SessionEnd.ps1`

**Gate**: Validation MUST pass before `git push`
```

## Cross-References

- Analysis: `.agents/analysis/001-merge-resolver-session-protocol-gap.md`
- Session: `.agents/sessions/2025-12-27-session-68-template-sync-check-analysis.md`
- Skill: `.claude/skills/merge-resolver/SKILL.md`
- Memory: [merge-resolver-auto-resolvable-patterns](merge-resolver-auto-resolvable-patterns.md)
- Protocol: `.agents/SESSION-PROTOCOL.md`

## Metrics

| Metric | Value |
|--------|-------|
| Template sync check (PR #246) | PASS |
| Session protocol check (PR #246) | FAIL (9 MUST violations) |
| Session files with violations | 3 of 10 |
| Auto-resolvable template patterns | 3 depth levels |

## Impact

**Before fix**: Merge resolutions push incomplete sessions → CI blocks → confusion

**After fix**: Merge-resolver validates session protocol → block push early → clear error message

**User benefit**: Correct diagnosis → faster resolution

---

**Created**: 2025-12-27
**Source**: Analyst investigation (Session 68)
**Status**: Validated (PR #246 case study)

## Related

- [merge-resolver-auto-resolvable-patterns](merge-resolver-auto-resolvable-patterns.md)
