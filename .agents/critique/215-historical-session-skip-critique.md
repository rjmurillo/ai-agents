# Plan Critique: Issue #215 Historical Session Validation Skip

## Verdict

**APPROVED_WITH_CONDITIONS**

## Summary

Implementation correctly solves the core issue (historical sessions failing validation) with a pragmatic date-based filtering approach. Date comparison logic is sound, edge cases are handled, logging is clear. Minor concerns about bash usage in workflow YAML and lack of test coverage.

## Strengths

1. **Correct root cause fix**: Targets the exact problem (retroactive application of Session End checklist requirement)
2. **Pragmatic cutoff date**: 2025-12-21 matches when the requirement was introduced (commit eba5b59)
3. **Safe default for edge cases**: Non-standard filenames included for validation (fail-safe approach)
4. **Clear operational visibility**: Separate logging for skipped vs validated files
5. **Preserves validation for new sessions**: Only exempts historical files, maintains quality gate for current work
6. **Minimal workflow disruption**: No breaking changes to downstream jobs

## Issues Found

### Critical (Must Fix)

None

### Important (Should Fix)

1. **Constraint Violation: Bash logic in workflow YAML**

   **Location**: Lines 48-108 in `.github/workflows/ai-session-protocol.yml`

   **Issue**: ADR-006 ("Thin Workflows, Testable Modules") requires business logic in PowerShell modules, not YAML. This implementation has 60+ lines of bash logic directly in the workflow.

   **Evidence from ADR-006**:
   ```text
   | Constraint | Source | Verification |
   |------------|--------|--------------|
   | MUST NOT put business logic in workflow YAML | ADR-006 | Code review |
   | SHOULD keep workflows under 100 lines (orchestration only) | ADR-006 | Lint check |
   | MUST put complex logic in .psm1 modules | ADR-006 | Code review |
   ```

   **Impact**: No local testing possible for this logic. Changes require push-wait-check cycle. Increases COGS for debugging.

   **Recommendation**: Extract to PowerShell module (e.g., `.github/scripts/SessionValidation.psm1`) with functions like `Get-ValidatableSessionFiles` that can be Pester-tested.

   **Severity**: Important (not Critical) - implementation works correctly but violates architectural constraints.

2. **Missing test coverage**

   **Issue**: No automated tests for date extraction and comparison logic.

   **Risk**: Future changes could break edge case handling (non-standard filenames, malformed dates, boundary conditions).

   **Recommendation**: If logic extracted to PowerShell module (per issue 1), add Pester tests covering:
   - Standard filename format (YYYY-MM-DD-session-NN.md)
   - Extended filename format (YYYY-MM-DD-session-NN-description.md)
   - Non-standard filenames (edge case)
   - Boundary date (2025-12-21 vs 2025-12-20)
   - Malformed dates (missing hyphens, wrong format)

### Minor (Consider)

1. **Hardcoded cutoff date**

   **Issue**: CUTOFF_DATE="2025-12-21" is hardcoded in workflow YAML.

   **Consideration**: If Session Protocol evolves with new requirements, will need workflow updates each time. Could extract to environment variable or config file for easier maintenance.

   **Counter-argument**: Cutoff date changes are rare (only when MUST requirements added). Current approach is simple and explicit.

   **Verdict**: Acceptable as-is. Document in commit message or inline comment.

2. **Bash string comparison**

   **Line**: 73 - `if [[ "$file_date" < "$CUTOFF_DATE" ]]; then`

   **Observation**: Lexicographic string comparison works correctly for YYYY-MM-DD format but is implicit.

   **Consideration**: More explicit would be to convert to epoch time or use date comparison utilities.

   **Counter-argument**: String comparison for ISO 8601 dates (YYYY-MM-DD) is standard practice and works reliably.

   **Verdict**: Acceptable. Format is documented in comment.

## Questions for Implementer

1. **ADR-006 Compliance**: Was the decision to use bash in workflow YAML (vs. PowerShell module) intentional? If so, what was the rationale for deviating from ADR-006?

2. **Future-proofing**: If Session Protocol adds new MUST requirements in the future, is the expectation to update CUTOFF_DATE or add multiple date thresholds?

## Recommendations

1. **Short-term (this PR)**: Document ADR-006 deviation in commit message. Add inline comment explaining why bash logic in workflow YAML was chosen.

2. **Medium-term (follow-up issue)**: Extract date filtering logic to PowerShell module with Pester tests. This aligns with ADR-006 and enables local testing.

3. **Documentation**: Add comment in workflow YAML explaining cutoff date rationale:
   ```yaml
   # Issue #215: Session End checklist requirement introduced 2025-12-21 (commit eba5b59)
   # Sessions created before this date lack required checklist format
   # Historical sessions are exempt from validation (not retroactively enforceable)
   CUTOFF_DATE: "2025-12-21"
   ```

## Approval Conditions

### MUST (Blocking)

None - implementation is functionally correct and solves the stated issue.

### SHOULD (Non-blocking)

1. Document ADR-006 deviation rationale in commit message or PR description
2. Consider follow-up issue to refactor to PowerShell module (alignment with ADR-006)

## Impact Analysis Review

No impact analysis present (not required for bug fix). Implementation is isolated to workflow YAML with no cross-domain concerns.

## Technical Details

### Date Comparison Verification

**Logic**: Lines 72-77
```bash
if [[ "$file_date" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}$ ]]; then
  if [[ "$file_date" < "$CUTOFF_DATE" ]]; then
    SKIPPED_FILES="${SKIPPED_FILES}${file}"$'\n'
  else
    CHANGED_FILES="${CHANGED_FILES}${file}"$'\n'
  fi
```

**Verification**:
- Regex pattern `^[0-9]{4}-[0-9]{2}-[0-9]{2}$` correctly validates YYYY-MM-DD format
- Bash string comparison `<` works correctly for ISO 8601 dates (lexicographic order matches chronological order)
- Files matching 2025-12-20 and earlier: skipped
- Files matching 2025-12-21 and later: validated
- Files not matching pattern: validated (safe default)

**Edge Cases Handled**:
1. Non-standard filenames: Included for validation (line 80)
2. Empty results after filtering: Handled (lines 94-98)
3. All files historical: Short-circuits with `has_sessions=false` (line 97)

### Risks

**Low Risk**:
- Implementation is additive (no breaking changes)
- Affects only `detect-changes` job (upstream job)
- Downstream `validate` and `aggregate` jobs unchanged
- Clear logging allows troubleshooting

**No Rollback Issues**:
- Can revert commit if issues found
- No data migration or state changes

## Verdict Rules Applied

**APPROVED_WITH_CONDITIONS** because:
- All Critical issues: 0 (none found)
- Important issues: 2 (ADR-006 violation, no tests)
- Important issues are documented with mitigation path
- Functional implementation is correct
- Ready for implementation WITH acknowledgment of deviation

**Conditions for approval**:
1. Implementer acknowledges ADR-006 deviation
2. Deviation rationale documented (commit message or PR)
3. Follow-up issue created for PowerShell module extraction (optional but recommended)

## Handoff Recommendation

**Target**: orchestrator

**Reason**: Subagent cannot delegate directly. Return critique to orchestrator for routing decision.

**Recommended Next Steps**:
1. If implementer acknowledges conditions: Route to implementer for commit message update and PR creation
2. If ADR-006 compliance required: Route to implementer for refactoring to PowerShell module
3. If questions need clarification: Route to analyst for architecture decision consultation

---

**Critique Date**: 2025-12-29
**Reviewed By**: critic agent
**Issue**: #215
**Implementation Branch**: refactor/144-pester-path-deduplication
