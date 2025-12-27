# Plan Critique: PRD-pr-maintenance-authority.md

**Date**: 2025-12-26
**Critic**: critic agent
**PRD**: .agents/planning/PRD-pr-maintenance-authority.md
**Diagnostics**: .agents/qa/PR-402/2025-12-26-gap-diagnostics.md

## Verdict
**NEEDS REVISION**

## Summary
The PRD addresses all 4 gaps from diagnostics with clear user stories and technical requirements. However, there are critical issues with INVEST compliance, missing technical details, and protocol documentation gaps that must be resolved before task generation.

## Strengths
- All 4 gaps from diagnostics are covered with dedicated user stories
- Acceptance criteria use Given/When/Then format
- Technical requirements specify exact file locations and line numbers
- Success metrics are quantifiable with zero-tolerance targets
- Data structures are defined with explicit fields

## Issues Found

### Critical (Must Fix)

- [ ] **Story 3 INVEST Violation - Not Small** (Lines 89-108)
  - **Issue**: "Can be implemented in one session" is incorrect
  - **Evidence**: Requires creating a new function (`Invoke-CopilotSynthesis`), detecting copilot authorship, collecting comments from 3+ bots, generating synthesis prompts, posting comments via GitHub API, and adding ActionRequired logic
  - **Impact**: Task estimation will be incorrect, leading to incomplete implementation
  - **Correction**: Split into 2 stories:
    1. "Detect copilot-swe-agent PRs and collect other bot feedback"
    2. "Generate and post @copilot synthesis prompts"

- [ ] **Missing Technical Requirement for Comment Detection** (Lines 131-179)
  - **Issue**: FR3 (lines 152-159) does not specify HOW to detect unaddressed comments
  - **Evidence**: Diagnostics line 119 shows `Get-UnacknowledgedComments(...)` exists, but PRD doesn't define what makes a comment "unaddressed"
  - **Impact**: Implementer will have to make assumptions about comment state
  - **Correction**: Add to FR3:
    ```markdown
    **Comment State Detection**:
    - Unaddressed = comment has no replies OR all replies are from the commenter
    - Eyes reaction does NOT count as "addressed"
    - Use existing Get-UnacknowledgedComments function
    ```

- [ ] **Missing Protocol Update Specification** (Lines 189-193)
  - **Issue**: Line 191 states "Add scenario: Bot as reviewer on mention-triggered PR" but does not specify WHERE in the protocol document or WHAT content to add
  - **Evidence**: Diagnostics lines 205-210 identify this as SPEC_GAP requiring protocol changes
  - **Impact**: Protocol changes will be incomplete or inconsistent
  - **Correction**: Add to FR4:
    ```markdown
    **Protocol Document Updates** (.agents/architecture/bot-author-feedback-protocol.md):
    - Add to Scenarios section: "Scenario 3: Bot Reviewer on Mention-Triggered PR"
    - Add decision table row: Author=copilot-swe-agent, Reviewer=rjmurillo-bot -> Action=Synthesize
    - Define bot authority boundary: "Bot reviewer CANNOT directly modify mention-triggered PRs"
    ```

### Important (Should Fix)

- [ ] **Acceptance Criteria Missing Negative Cases** (Lines 54-61, 76-83)
  - **Issue**: Stories 1-2 only test positive path (bot-authored PRs)
  - **Evidence**: Should verify human-authored PRs are NOT affected
  - **Impact**: Risk of breaking existing human PR handling
  - **Correction**: Add negative acceptance criteria to each story:
    ```markdown
    **And** human-authored PRs with conflicts are still added to Blocked (not ActionRequired)
    ```

- [ ] **FR5 Implementation Detail Missing** (Lines 171-179)
  - **Issue**: "Check if PR already exists" but doesn't specify the check logic
  - **Evidence**: Diagnostics lines 271-274 show specific check: `$results.ActionRequired | Where-Object { $_.PR -eq $pr.number }`
  - **Impact**: Implementer may use wrong property for comparison
  - **Correction**: Update FR5 implementation to:
    ```powershell
    $alreadyInActionRequired = $results.ActionRequired | Where-Object { $_.PR -eq $pr.number }
    if ($alreadyInActionRequired) {
        # Update existing entry
    }
    ```

- [ ] **Test Coverage Missing Integration Test** (Lines 216-223)
  - **Issue**: All tests are unit-level Pester tests
  - **Evidence**: Success metrics (lines 268-274) require "Run PR maintenance workflow on current PR set"
  - **Impact**: May pass unit tests but fail end-to-end
  - **Correction**: Add to Test Coverage:
    ```markdown
    6. **Integration Test**: Run Invoke-PRMaintenance against 6 affected PRs (#365, #353, #301, #255, #247, #235) and verify disposition matches expected behavior
    ```

### Minor (Consider)

- [ ] **Copilot Synthesis Format Example Missing Variation** (Lines 243-258)
  - **Issue**: Example only shows case with both coderabbitai and cursor[bot]
  - **Evidence**: Should show edge case (only 1 bot, or 0 bots)
  - **Impact**: Implementer may not handle edge cases
  - **Correction**: Add note:
    ```markdown
    **Edge Cases**:
    - If only 1 bot has comments: still generate synthesis
    - If 0 other bots: do NOT post synthesis (no COPILOT_SYNTHESIS_NEEDED reason)
    ```

## Questions for Planner

1. **Story 3 Scope**: How should the copilot synthesis story be split to meet the "Small" INVEST criterion? Should detection logic be separate from synthesis logic?

2. **Comment State Definition**: What constitutes an "unaddressed" comment? Does the existing `Get-UnacknowledgedComments` function match the required behavior, or does it need modification?

3. **Protocol Update Location**: Where in `bot-author-feedback-protocol.md` should the new scenario be added? Should it be a new section or added to existing decision tables?

4. **Edge Case Handling**: What should happen when a copilot-swe-agent PR has 0 comments from other bots but rjmurillo-bot has CHANGES_REQUESTED? Should it still synthesize (empty prompt) or fall back to a different action?

## Recommendations

1. **Split Story 3** into two independent stories to meet INVEST "Small" criterion
2. **Add FR3 detail** specifying comment detection logic (reference existing function or define new behavior)
3. **Expand FR4** with specific protocol document changes (section, content, format)
4. **Add negative test cases** to acceptance criteria to prevent regressions in human PR handling
5. **Add integration test** to test coverage that validates end-to-end workflow on affected PRs
6. **Document edge cases** for copilot synthesis (0 bots, 1 bot, missing comments scenarios)

## Approval Conditions

### Must Be Addressed Before Approval

1. Story 3 INVEST violation resolved (split or justify single-session scope)
2. FR3 comment detection logic specified
3. FR4 protocol update details added
4. Negative acceptance criteria added to Stories 1-2
5. Integration test added to test coverage

### Should Be Addressed (Strongly Recommended)

1. FR5 implementation check logic specified
2. Copilot synthesis edge cases documented

## Impact Analysis Review

**Consultation Coverage**: N/A (no impact analysis present)
**Cross-Domain Conflicts**: N/A
**Escalation Required**: No

**Note**: This PRD does not include specialist consultations. Given the scope (workflow logic changes, no new dependencies, no security risks identified in diagnostics), this is acceptable. However, if implementer encounters cross-cutting concerns during implementation, they should escalate for specialist review.

---

## Completeness Assessment

| Criterion | Status | Notes |
|-----------|--------|-------|
| All 4 gaps addressed | [PASS] | Stories 1-4 map to Gaps 1-4 |
| INVEST compliance | [FAIL] | Story 3 violates "Small" |
| Acceptance criteria testable | [PASS] | Given/When/Then format with specific conditions |
| Technical requirements actionable | [FAIL] | FR3, FR4, FR5 missing implementation details |
| Success metrics measurable | [PASS] | Zero-tolerance targets with clear measurement |
| Negative cases covered | [FAIL] | No verification that human PRs are unaffected |
| Test coverage complete | [WARNING] | Missing integration test |

---

## Final Verdict: NEEDS REVISION

**Rationale**: The PRD successfully addresses all 4 gaps from diagnostics and provides a solid foundation. However, 3 critical issues block approval:

1. **Story 3 INVEST violation** creates estimation risk
2. **Missing technical details** (FR3, FR4, FR5) will force implementer to make assumptions
3. **No negative test cases** risk breaking existing human PR handling

**Confidence Level**: HIGH - Issues are specific, actionable, and well-evidenced from diagnostics.

**Recommendation**: Orchestrator should route back to planner to address Critical issues. Once resolved, PRD will be ready for task generation.
