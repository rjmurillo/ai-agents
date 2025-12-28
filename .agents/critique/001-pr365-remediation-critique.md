# Plan Critique: PR #365 Remediation

## Verdict

**APPROVED_WITH_CONDITIONS**

## Summary

The PRD for PR #365 remediation provides a comprehensive, well-structured approach to resolving merge conflicts and updating scope documentation. The plan demonstrates strong technical understanding of the root cause, clear success metrics, and INVEST-compliant user stories. However, three specific gaps require resolution before implementation begins to prevent rework or confusion.

## Strengths

- **Measurable success metrics**: Each metric has verifiable output (git status, CI checks, spec validation verdicts)
- **Root cause analysis**: Clear documentation of race condition timeline (lines 204-211)
- **Conflict resolution strategy**: Specific file-by-file actions with rationale (FR-1, lines 89-106, FR-3 table lines 127-135)
- **Scope clarity**: Explicitly bounded to 26 files with documentation of 35 files renamed elsewhere
- **INVEST-compliant user stories**: All three user stories pass INVEST validation with clear acceptance criteria
- **Phase definitions**: Three-phase implementation with time estimates and specific commands

## Issues Found

### Critical (Must Fix)

- [ ] **Missing verification step for index file merge conflicts** (Phase 1, lines 269-286)
  - **Location**: Implementation Approach, Phase 1
  - **Issue**: Manual merge instruction for `skills-analysis-index.md` and `skills-architecture-index.md` lacks verification command
  - **Risk**: Index files may have duplicate entries or missing references after merge
  - **Fix Required**: Add verification step after manual merge:
    ```bash
    # After manual merge of index files, verify no duplicates:
    sort skills-analysis-index.md | uniq -d  # Should return empty
    sort skills-architecture-index.md | uniq -d  # Should return empty
    ```

- [ ] **Ambiguous "combine both updates" instruction** (FR-1, line 101)
  - **Location**: FR-1: Conflict Resolution Strategy
  - **Issue**: "Combine updates from both branches, remove duplicate entries" does not specify merge logic
  - **Risk**: Implementer may resolve conflicts incorrectly, causing validation failures
  - **Fix Required**: Add explicit merge rule to FR-1:
    ```markdown
    **Merge Logic for Domain Index Files:**
    1. Accept all entries from main branch
    2. Add entries from PR branch that reference renamed files (26 files)
    3. Remove any duplicate entries (same file referenced twice)
    4. Sort entries alphabetically within each section
    ```

- [ ] **Missing rollback strategy** (No section defined)
  - **Location**: Entire PRD
  - **Issue**: No documented rollback procedure if rebase causes unexpected issues
  - **Risk**: If force push breaks CI or introduces bugs, no clear recovery path
  - **Fix Required**: Add section "Rollback Procedure" after Implementation Approach:
    ```markdown
    ## Rollback Procedure

    If rebase introduces issues:
    1. Reset branch to pre-rebase state: `git reset --hard origin/fix/memories`
    2. Switch to Option 2 (merge main into branch) instead
    3. Document reason for switching strategies in PR comment
    ```

### Important (Should Fix)

- [ ] **Phase 2 references non-existent file** (Phase 2, line 296)
  - **Location**: Phase 2: Update PR Documentation, step 3
  - **Issue**: References `.agents/qa/PR-402/2025-12-26-gap-diagnostics.md` without verifying file exists
  - **Risk**: Step may fail if file was moved or renamed
  - **Fix Required**: Add existence check or update reference if file path changed:
    ```bash
    # Before updating gap diagnostics, verify file exists:
    [ -f .agents/qa/PR-402/2025-12-26-gap-diagnostics.md ] || echo "Warning: Gap diagnostics file not found"
    ```

- [ ] **Success Metric #3 lacks numeric threshold** (Success Metrics, line 252)
  - **Location**: Success Metrics
  - **Issue**: "Spec Validation: COMPLETENESS_VERDICT: PASS and TRACE_VERDICT: PASS" does not specify what "PASS" means numerically
  - **Risk**: Ambiguity about when spec validation truly passes
  - **Fix Required**: Add expected values:
    ```markdown
    3. **Spec Validation**: `COMPLETENESS_VERDICT: PASS` (26/26 files = 100%) and `TRACE_VERDICT: PASS` (all issue references valid)
    ```

### Minor (Consider)

- [ ] **Open Question #2 resolution unclear** (Open Questions, lines 261-262)
  - **Location**: Open Questions
  - **Issue**: "Create new issue for batch rename after PR #365 merged" - no owner or timeline assigned
  - **Risk**: Follow-up work may be forgotten
  - **Fix Suggested**: Add assignment:
    ```markdown
    - **Recommendation**: Out of scope for this PR. @rjmurillo to create new issue for batch rename within 48 hours of PR #365 merge.
    ```

- [ ] **CI Check Details may be outdated** (CI Check Details, lines 229-246)
  - **Location**: Technical Considerations
  - **Issue**: URLs reference specific run IDs that may become stale after rebase
  - **Risk**: Links may 404 after CI re-runs
  - **Fix Suggested**: Add note:
    ```markdown
    **Note**: Run URLs will update after rebase. Use `gh run list --branch fix/memories` to find latest runs.
    ```

## Questions for Planner

1. **Index file merge verification**: What is the expected content of `skills-analysis-index.md` and `skills-architecture-index.md` after merge? Should they reference the 26 renamed files with new names?

2. **Force push safety**: Has branch protection been verified to allow force-with-lease? Some repos block force pushes even with lease.

3. **Issue #356 comment template date**: Line 187 has placeholder "2025-12-XX" - what is the actual issue creation date?

## Recommendations

1. **Add merge verification commands** to Phase 1 implementation steps
2. **Document explicit merge logic** for index files in FR-1
3. **Add rollback procedure** section for risk mitigation
4. **Verify file path** for gap diagnostics before referencing in Phase 2
5. **Quantify success metric thresholds** for spec validation

## Approval Conditions

Before implementation begins:

1. **Critical Issue #1 resolved**: Add index file verification step to Phase 1
2. **Critical Issue #2 resolved**: Define explicit merge logic for "combine both updates"
3. **Critical Issue #3 resolved**: Add rollback procedure section

Once these three conditions are met, the plan is ready for implementation.

## Impact Analysis Review

**Not Applicable**: This PRD does not include impact analysis from specialist agents. It is a tactical remediation plan for existing PR merge conflicts.

## Revision History

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | 2025-12-26 | Initial critique by critic agent |
