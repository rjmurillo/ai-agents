# Plan Critique: ADR-020 Feature Request Review Step

**Date**: 2025-12-23
**Reviewer**: Critic Agent
**ADR**: ADR-020-feature-request-review-step.md
**Plan**: feature-review-workflow-changes.md

## Verdict

**NEEDS REVISION**

## Summary

ADR-020 proposes adding a new conditional workflow step that invokes the critic agent to perform sophisticated feature request reviews. The architecture is sound and aligns with established patterns (ADR-005, ADR-006), but the decision has critical gaps in scope, feasibility assessment, and implementation completeness.

## Strengths

1. **Good architectural alignment**: Follows ADR-005 (PowerShell-only) and ADR-006 (thin workflows, testable modules)
2. **Clear separation of concerns**: Analyst categorizes, critic evaluates, roadmap prioritizes
3. **Conditional execution**: Only runs for enhancement category, avoiding waste
4. **Testable implementation**: PowerShell parsing functions with Pester tests planned
5. **Tool limitation awareness**: Explicitly acknowledges Copilot CLI constraints

## Issues Found

### Critical (Must Fix)

- [ ] **P0: Missing action on parsed outputs** - ADR specifies parsing `recommendation`, `assignees`, and `labels` from feature review but does NOT specify workflow steps to ACT on these outputs. What happens after parsing? Are assignees auto-assigned? Are labels auto-applied? Without action steps, the feature review becomes a comment-only operation with no automation value.

- [ ] **P0: Incomplete prompt adaptation** - ADR Section "Prompt Adaptation for Copilot CLI" describes what to remove/retain but does NOT verify that the ACTUAL prompt file (`.github/prompts/issue-feature-review.md`) matches these requirements. The prompt file exists but was not validated against the adaptation checklist.

- [ ] **P0: Missing rollback impact on comment template** - Rollback plan says "remove feature review from triage summary template" but does NOT specify WHICH lines to remove from the PowerShell comment generation code. Without exact removal instructions, rollback becomes guesswork.

- [ ] **P0: No validation of category detection accuracy** - The conditional `if: steps.parse-categorize.outputs.category == 'enhancement'` depends on analyst agent correctly categorizing feature requests. There is NO validation that this works reliably. What is the false negative rate? What happens if analyst miscategorizes a feature as "question"?

- [ ] **P0: Agent role conflict unresolved** - The critic agent's documented role is "stress-tests planning documents before implementation" but this ADR uses critic for "evaluate feature requests." These are different concerns. The ADR does NOT resolve whether critic should expand scope or if a different agent should be used.

### Important (Should Fix)

- [ ] **P1: No impact analysis on workflow execution time** - ADR states "Adds ~2-3 minutes" but does NOT analyze cumulative impact. Current workflow has 3 steps (categorize, align, PRD). Adding a 4th step increases total time by what percentage? What is the p95 latency for feature request triage after this change?

- [ ] **P1: Prompt file location not validated against composite action** - ADR specifies `prompt-file: .github/prompts/issue-feature-review.md` but does NOT verify that `.github/actions/ai-review` composite action supports this path format. Does the action expect absolute or relative paths? Does it validate file existence before invocation?

- [ ] **P1: No error handling for parse failures** - The `Parse Feature Review Results` step uses `if: steps.review-feature.outcome == 'success'` but does NOT handle what happens if parsing FAILS after a successful review. If regex fails to extract recommendation, what is the fallback behavior?

- [ ] **P1: Comment template integration unclear** - Plan document shows adding `$featureRow` and `$featureDetails` variables but does NOT show WHERE in the existing comment template these get inserted. Without line numbers or anchor points, implementer must guess placement.

- [ ] **P1: No test coverage target specified** - ADR mentions Pester tests but does NOT specify coverage target. ADR-006 requires 80% coverage for modules. Does this apply to the three new parsing functions?

- [ ] **P1: Copilot model not specified** - Workflow step does NOT include `copilot-model:` parameter. Does this default to GPT-4? Should it use `claude-opus-4.5` like the PRD generation step?

### Minor (Consider)

- [ ] **P2: Duplicate effort with roadmap agent** - Roadmap agent already evaluates "strategic alignment" and "priority." Feature review step evaluates "Strategic Alignment" and "User Impact" for recommendations. There is overlap but no explanation of why both are needed or how outputs differ.

- [ ] **P2: No metrics for success** - ADR does NOT define how to measure if feature reviews improve outcomes. Should we track recommendation distribution? Submitter satisfaction? Acceptance rate of reviewed features?

- [ ] **P2: Prompt versioning not addressed** - The prompt file will evolve based on feedback. ADR does NOT specify how to version prompts or track changes. How do we know which prompt version produced a given review?

## Questions for Planner

1. **Action workflow**: After parsing `assignees` and `labels`, should the workflow automatically assign users and apply labels, or are these only suggestions in the comment?

2. **Agent scope**: Should critic agent's role be expanded to include feature evaluation, or should this use a different agent (e.g., analyst with different prompt)?

3. **Failure modes**: What should happen if:
   - Critic review times out?
   - Parsing returns UNKNOWN recommendation?
   - Assignees contain invalid usernames?

4. **Integration point**: Where exactly in the triage summary comment should feature review details appear? After roadmap alignment? Before PRD section?

5. **Coverage**: What percentage of feature requests do you expect will be categorized as `enhancement` by the analyst? Is this validated?

## Recommendations

### Architecture Fixes

1. **Define action steps**: Add workflow steps AFTER parsing to:
   - Apply suggested labels (if not "none")
   - Assign suggested users (if not "none suggested")
   - Post feature review as comment
   - Update issue milestone based on recommendation

2. **Validate prompt adaptation**: Create checklist comparing `.github/prompts/issue-feature-review.md` against "Prompt Adaptation for Copilot CLI" section. Verify all MCP tool references removed.

3. **Resolve agent role**: Either:
   - **Option A**: Expand critic role to include "feature evaluation" in addition to "plan validation"
   - **Option B**: Use analyst agent with feature-specific prompt
   - **Option C**: Create dedicated feature-reviewer agent (rejected in ADR but not with strong rationale)

4. **Specify model**: Add `copilot-model: claude-opus-4.5` to feature review step for consistency with PRD generation.

### Implementation Completeness

1. **Add action steps to workflow YAML**:

```yaml
- name: Apply Feature Review Suggestions
  if: steps.parse-review.outputs.recommendation != 'UNKNOWN'
  shell: pwsh
  env:
    ASSIGNEES: ${{ steps.parse-review.outputs.assignees }}
    LABELS: ${{ steps.parse-review.outputs.labels }}
  run: |
    # Apply labels if suggested
    if ($env:LABELS) {
      $labelList = $env:LABELS -split ','
      foreach ($label in $labelList) {
        gh issue edit $env:ISSUE_NUMBER --add-label $label
      }
    }
    # Assign users if suggested
    if ($env:ASSIGNEES) {
      gh issue edit $env:ISSUE_NUMBER --add-assignee $env:ASSIGNEES
    }
```

2. **Add validation step for category detection**:

```yaml
- name: Validate Category Detection
  if: github.event.issue.labels[*].name contains 'enhancement'
  run: |
    # Check if analyst detected enhancement
    if [ "${{ steps.parse-categorize.outputs.category }}" != "enhancement" ]; then
      echo "::warning::Issue labeled 'enhancement' but categorized as ${{ steps.parse-categorize.outputs.category }}"
    fi
```

3. **Document exact comment template insertion points**:

In plan document, replace vague "add after `$prdRow`" with:

```powershell
# Line 450 in ai-issue-triage.yml - INSERT AFTER
| **Milestone** | $milestoneDisplay |
$featureRow
$prdRow
```

### Testing Requirements

1. **Add Pester test cases for edge cases**:
   - Recommendation is UNKNOWN (parsing failed)
   - Multiple assignees with spaces: `@user1 , @user2`
   - Labels with special characters: `area:ci/cd`
   - Empty AI output (timeout or error)

2. **Add integration test scenario**:
   - Create test issue labeled `enhancement`
   - Verify analyst categorizes as `enhancement`
   - Verify critic review runs
   - Verify outputs parsed correctly
   - Verify suggested labels applied

### Rollback Specificity

Update rollback plan with exact changes:

```markdown
## Rollback Steps

1. Comment out lines 70-93 in `.github/workflows/ai-issue-triage.yml` (review-feature and parse-review steps)
2. Remove lines 450-470 in triage summary PowerShell script ($featureRow and $featureDetails)
3. Remove `FEATURE_REVIEW` and `FEATURE_REVIEW_OUTPUT` from env vars (lines 58-60)
4. Keep PowerShell parsing functions (tested, no side effects)
```

## Approval Conditions

ADR can be approved AFTER:

1. **Critical issues resolved**:
   - [ ] Action steps defined for parsed outputs (auto-assign, auto-label, or comment-only)
   - [ ] Prompt file validated against Copilot CLI adaptation requirements
   - [ ] Rollback plan specifies exact line numbers/changes
   - [ ] Category detection accuracy validated (or fallback defined)
   - [ ] Agent role conflict resolved (expand critic or use different agent)

2. **Important issues addressed**:
   - [ ] Workflow execution time impact quantified (percentage increase, p95 latency)
   - [ ] Prompt file path format verified with composite action
   - [ ] Error handling for parse failures specified
   - [ ] Comment template integration points documented with line numbers
   - [ ] Test coverage target confirmed (80% per ADR-006)
   - [ ] Copilot model specified in workflow step

3. **Plan updated**:
   - [ ] Implementation plan includes action steps (apply labels, assign users)
   - [ ] Validation checklist expanded with integration test
   - [ ] Rollback plan has exact change locations

## Impact Analysis Review

**Consultation Coverage**: N/A (no impact analysis performed)

**Cross-Domain Conflicts**: None detected

**Escalation Required**: No

**Unanimous Agreement**: N/A

## Recommended Next Steps

1. **Planner**: Address critical issues (P0) and answer questions above
2. **Planner**: Update ADR with action step specification and agent role resolution
3. **Planner**: Update plan document with exact comment template insertion points
4. **Architect**: Review agent role expansion (should critic handle feature evaluation?)
5. **Implementer**: After revision approval, implement with expanded test coverage

---

**Critique Version**: 1.0
**Next Review**: After planner addresses P0 issues
