# Plan Critique: PRD - Fix Acknowledged vs Resolved Gap in PR Maintenance Workflow

**Verdict**: [APPROVED]

**Date**: 2025-12-26
**Reviewer**: critic agent
**Confidence Level**: High

## Summary

The PRD addresses a legitimate gap in the PR maintenance workflow where acknowledged comments (eyes reactions) are incorrectly treated as fully resolved. The plan proposes a clear solution: distinguish between "acknowledged" (eyes reaction added) and "resolved" (thread closed) states by querying the GraphQL API for thread resolution status.

The PRD is well-structured with measurable acceptance criteria, comprehensive test fixtures, and a phased implementation approach. All INVEST criteria are satisfied across the three user stories. The technical approach is sound and validated by existing GraphQL usage patterns in the codebase.

## Strengths

1. **Evidence-Based Problem Statement**: PR #365 is cited with specific data (5 acknowledged but unresolved threads), providing clear validation of the gap.

2. **Measurable Acceptance Criteria**: All 15 acceptance criteria across 3 user stories are boolean and testable (e.g., "Function returns empty array when all threads are resolved").

3. **Comprehensive Test Coverage**: Includes 3 detailed test fixtures covering edge cases (PR #365 equivalent, fully resolved PR, mixed state).

4. **Clear Semantic Model**: The Comment Lifecycle diagram (lines 219-232) explicitly defines state transitions from NEW → ACKNOWLEDGED → REPLIED → RESOLVED.

5. **Risk Mitigation**: Identifies 4 risks with probability/impact/mitigation strategies. GraphQL API failure has graceful fallback (return empty array).

6. **Backward Compatibility**: Preserves existing `Get-UnacknowledgedComments` function unchanged; adds new `Get-UnaddressedComments` function separately.

7. **Technical Feasibility**: The GraphQL query pattern (lines 106-123) matches the existing `Resolve-PRReviewThread.ps1` implementation at lines 84-100, confirming API availability.

8. **Quantified Performance Impact**: "+50ms per PR (GraphQL query latency), +1 second for 20 PRs" with justification against 45-minute timeout.

## Issues Found

### Critical (Must Fix)

None. All blocking issues have been addressed.

### Important (Should Fix)

1. **Assumption #3 Requires Validation** (Line 401)

   **Issue**: Assumes "All bot comments are part of review threads (not standalone issue comments)". PR #365 verification shows all 5 bot comments ARE in review threads, but this may not hold for all PRs.

   **Evidence from PR #365 GraphQL query**: All 5 threads have `comments.nodes[0].databaseId` values matching the REST API comment IDs, confirming they are review thread comments.

   **Recommendation**: Add defensive check in `Get-UnaddressedComments` to handle bot comments NOT in review threads (they should still be flagged if unacknowledged).

   **Code suggestion**:
   ```powershell
   # Extract comment IDs from unresolved threads
   $unresolvedCommentIds = $unresolvedThreads | ForEach-Object { $_.comments.nodes[0].databaseId }

   # Flag comments that are EITHER unacknowledged OR in unresolved threads
   $filtered = $botComments | Where-Object {
       ($_.reactions.eyes -eq 0) -or ($unresolvedCommentIds -contains $_.id)
   }
   ```

   This handles both review thread comments AND standalone bot comments.

2. **GraphQL Rate Limit Check Missing from FR4** (Lines 176-189)

   **Issue**: FR4 specifies updating line ~1401 to call `Get-UnaddressedComments`, but does NOT mention updating `Test-RateLimitSafe` to check `graphql` resource (mentioned in FR1 line 241).

   **Impact**: Script could hit GraphQL rate limits without warning, causing silent degradation to unacked-only mode.

   **Recommendation**: Add to "Files to Modify" table (line 385):

   ```markdown
   | `scripts/Invoke-PRMaintenance.ps1` | MODIFY | Line ~207: Add `graphql` to `Test-RateLimitSafe` check with threshold 100 |
   ```

   Already documented in "Technical Considerations" (lines 237-244), but missing from implementation plan.

### Minor (Consider)

1. **Open Question #1 Already Answered** (Lines 372-373)

   **Issue**: Question asks "Should GraphQL failure trigger script exit or continue with fallback?" but FR2 (lines 126-149) already specifies the answer: "Return empty array on API failure (log warning)".

   **Recommendation**: Move the answer to "Assumptions" section or remove the open question entirely. Reduces ambiguity for implementers.

2. **Pagination Not Addressed** (Line 110)

   **Issue**: GraphQL query uses `first: 100` but provides no handling for PRs with >100 review threads. `Resolve-PRReviewThread.ps1` has the same pattern with a comment at line 88: "# Note: first: 100 handles most PRs; pagination not implemented for edge cases with 100+ threads".

   **Impact**: Low risk (PRs rarely exceed 100 threads), but if it occurs, unresolved threads beyond the first 100 would be missed.

   **Recommendation**: Add to "Assumptions" section:

   ```markdown
   6. PRs have fewer than 100 review threads (pagination not implemented)
   ```

3. **Variable Naming Consistency** (Line 187)

   **Issue**: FR4 specifies changing `$unacked` to `$unaddressed` but does NOT update the corresponding variable name in the log message at line 1410.

   **Current**:
   ```powershell
   Write-Log "PR #$($pr.number): rjmurillo-bot is $role with $reason -> /pr-review" -Level WARN
   ```

   **Recommendation**: Ensure log messages reference the correct state. If the reason is "UNRESOLVED_THREADS", the log should say "with UNRESOLVED_THREADS" not just "$reason" (which is already correct, but worth validating during implementation).

## Questions for Planner

1. **Assumption #3 Validation**: Have you verified that ALL bot comments in the repository are review thread comments (not standalone issue comments)? If standalone comments exist, should they be handled separately?

2. **GraphQL Rate Limit Priority**: Is the `graphql` rate limit check (FR1 line 241) required for Phase 1 or can it be deferred to Phase 2 integration testing?

3. **Pagination Strategy**: For the rare case of PRs with >100 threads, should the script:
   - Fail-safe (warn and process first 100 only)
   - Implement pagination (fetch all threads)
   - Document as known limitation

## Recommendations

1. **Add defensive handling for non-thread bot comments** (Issue #1 above).

2. **Include `Test-RateLimitSafe` update in Files to Modify table** to ensure rate limit check is not forgotten during implementation.

3. **Clarify Open Question #1** by moving the answer to Assumptions or removing the question.

4. **Add pagination assumption** to document the 100-thread limit.

5. **Verify log message alignment** with new variable names and reason codes during implementation.

## Style Guide Compliance

### Evidence-Based Language

**[PASS]**: The PRD uses quantified claims throughout:

- "PR #365 had 5 bot comments" (line 7) - specific count
- "+50ms per PR, +1 second for 20 PRs" (lines 267-269) - quantified performance
- "reactions.eyes = 0" (line 9) - specific API field values
- "first: 100" (line 110) - explicit pagination limit
- "45-minute timeout, typical run time \<60s" (line 269) - measurable constraints

**No vague adjectives** like "significantly improved" or "complex" without data.

### Active Voice

**[PASS]**: Instructions use imperative form:

- "Query GraphQL API" (line 100)
- "Filter to threads where isResolved = false" (line 144)
- "Return empty array if no unresolved threads" (line 146)
- "Add GraphQL queries to Test-RateLimitSafe" (line 378)

No passive constructions like "The code should be updated".

### No Prohibited Phrases

**[PASS]**: No sycophantic or hedging language detected.

- No instances of "I think we should...", "It seems like..."
- Direct statements with rationale (e.g., "Decision: Use Option B for clarity and maintainability" - line 215)

### Status Indicators

**[PASS]**: Text-based status indicators used:

- "[NEW]", "[ACKNOWLEDGED]", "[REPLIED]", "[RESOLVED]" (lines 220-228)
- Table headers use "Status" (line 275)

No emoji-based status indicators.

### Quantified Estimates

**[PASS]**: Time/effort estimates are specific:

- "Phase 1", "Phase 2", "Phase 3" (lines 346-369) with clear acceptance gates
- "+50ms per PR" (line 267)
- "5000/hour" GraphQL rate limit (line 238)
- "threshold: 100" for rate limit checks (line 242)

No vague estimates like "This will take a while".

## Approval Conditions

The PRD is APPROVED with the following recommended improvements (none blocking):

1. Add defensive handling for non-thread bot comments (clarify Assumption #3)
2. Include `graphql` rate limit check in "Files to Modify" table
3. Document 100-thread pagination limit in Assumptions
4. Resolve Open Question #1 (already answered in FR2)

**These are enhancements, not blockers. The plan is implementation-ready as-is.**

## Completeness Assessment

### Completeness Score: 95%

| Checklist Item | Status | Evidence |
|---------------|--------|----------|
| All requirements addressed | [x] | 3 user stories with 15 acceptance criteria total |
| Acceptance criteria defined | [x] | Boolean criteria for each story (lines 42-95) |
| Dependencies identified | [x] | Table at lines 309-317 (4 dependencies listed) |
| Risks documented | [x] | Table at lines 320-343 (4 risks with mitigation) |
| Technical approach sound | [x] | GraphQL pattern validated in Resolve-PRReviewThread.ps1 |
| Scope realistic | [x] | 3 phases with clear acceptance gates |
| Dependencies available | [x] | GitHub GraphQL API, existing Get-PRComments function |
| Team skills sufficient | [x] | PowerShell + GitHub API (already in use) |
| Alignment verified | [x] | Closes issue #402, references ADR (bot-author-feedback-protocol.md) |
| Test strategy clear | [x] | 3 test fixtures (lines 414-471), 5 test cases (line 285) |
| Acceptance criteria measurable | [x] | All criteria are boolean (returns/does not return, passes/fails) |

**Deducted 5%**: Missing explicit pagination handling and non-thread comment edge case (Assumptions #3 and #6 recommended above).

## Feasibility Assessment

### Feasibility Score: 100%

**[PASS]** All feasibility criteria met:

1. **Technical Approach Sound**: GraphQL query pattern matches `Resolve-PRReviewThread.ps1` lines 84-100, confirming API is available and working.

2. **Scope Realistic**: 2 new functions + 1 line change + tests. Estimated as 3 phases with clear boundaries.

3. **Dependencies Available**:
   - GitHub GraphQL API: Confirmed working via PR #365 test query
   - `Get-PRComments`: Existing function at line ~437 of Invoke-PRMaintenance.ps1
   - PowerShell 7.0+: Already required
   - GitHub CLI (`gh`): Already required

4. **Team Skills**: PowerShell functions and GitHub API integration already in use throughout the codebase.

## Alignment Assessment

### Alignment Score: 100%

**[PASS]** Plan aligns with project requirements:

1. **Matches Original Requirements**: Issue #402 tracks PR maintenance visibility gap; PRD directly addresses the gap with PR #365 as evidence.

2. **Consistent with Architecture**: References `.agents/architecture/bot-author-feedback-protocol.md` (line 364) and ADR-017 naming convention (line 148).

3. **Follows Project Conventions**:
   - PowerShell function patterns (CmdletBinding, param blocks)
   - Skill-PowerShell-002: Return @() not $null (line 148)
   - Error handling: Log warning and fail-safe (lines 246-259)

4. **Supports Project Goals**: Improves bot-driven PR maintenance workflow, reduces false negatives where threads are missed.

## Testability Assessment

### Testability Score: 95%

**[PASS]** Test strategy is comprehensive:

1. **Each milestone can be verified**:
   - Phase 1: "Tests pass for all scenarios in Success Metrics table" (line 352)
   - Phase 2: "PR #365 scenario correctly classified as ActionRequired" (line 360)
   - Phase 3: "Documentation clearly explains state transitions" (line 368)

2. **Acceptance criteria measurable**: All 15 criteria are boolean checks (functions return/don't return, tests pass/fail).

3. **Test fixtures provided**: Lines 414-471 define 3 complete test cases with expected outputs.

**Deducted 5%**: No explicit test for GraphQL API failure scenario (mentioned in AC-4 of Story 1 line 47, but no fixture provided). Recommend adding:

```json
{
  "comments": [...],
  "threads": null,  // Simulate GraphQL failure
  "expectedBehavior": "Return empty array, log warning"
}
```

## Reversibility Assessment

**[PASS]** Changes are fully reversible:

1. **Rollback Capability**: New functions can be removed without breaking existing code. `Get-UnacknowledgedComments` is preserved unchanged (line 199).

2. **No Vendor Lock-In**: Uses GitHub's public GraphQL API (same as REST API already in use).

3. **Exit Strategy**: Revert line ~1401 from `Get-UnaddressedComments` back to `Get-UnacknowledgedComments`.

4. **Legacy System Impact**: None. Changes are additive. Existing workflow continues to work if new functions are removed.

5. **Data Migration**: Not applicable (no persistent data changes).

## Final Verdict

**[APPROVED]**

**Confidence Level**: High

**Justification**:

1. **Completeness**: 95% - All requirements addressed with measurable acceptance criteria. Minor gap: pagination and non-thread comment edge cases.

2. **Feasibility**: 100% - Technical approach validated by existing code patterns. All dependencies available.

3. **Alignment**: 100% - Matches issue #402, follows project conventions, references existing architecture documents.

4. **Testability**: 95% - Comprehensive test fixtures and boolean acceptance criteria. Missing GraphQL failure test case.

5. **Style Compliance**: 100% - Evidence-based language, active voice, quantified estimates, text-based status indicators.

**Overall Score**: 98/100

The PRD is implementation-ready. The identified issues are enhancements that can be addressed during implementation review or as follow-up improvements. None are blocking.

## Recommended Next Steps

1. **Route to implementer** for execution.
2. **Address recommendations** (non-blocking):
   - Clarify Assumption #3 (non-thread comments)
   - Add `graphql` rate limit check to Files to Modify table
   - Document 100-thread pagination limit
   - Add GraphQL failure test fixture

## Revision History

| Date | Version | Changes |
|------|---------|---------|
| 2025-12-26 | 1.0 | Initial critique (approved with recommendations) |
