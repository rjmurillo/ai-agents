# Plan Critique: Extract CI Check Verification as GitHub Skill Script

## Verdict
**[APPROVED WITH CONDITIONS]**

## Summary

The analyst's research is thorough and well-structured. The recommendation to extract `Test-PRHasFailingChecks` as a GraphQL-based `Get-PRChecks.ps1` skill script is sound. Research demonstrates strong evidence, clear trade-off analysis, and identifies a critical documentation gap in PR #471 (non-existent `--json` flag).

The research quality is high: verified facts are clearly distinguished from hypotheses, all sources are cited, and the analyst discovered during research that documented `gh pr checks --json` syntax does not exist.

## Strengths

1. **Evidence-Based Analysis**: All findings include source references with line numbers
2. **Trade-off Matrix**: Clear comparison of GraphQL vs bash vs REST approaches
3. **Test Coverage Verification**: Confirmed 13 unit tests with 100% coverage for existing logic
4. **Critical Discovery**: Identified documentation error in PR #471 (`--json` flag does not exist)
5. **Structured Output**: Proposed schema with exit codes follows existing GitHub skill patterns
6. **Risk Assessment**: Clear "Risk if ignored" section quantifies impact

## Issues Found

### Critical (Must Fix)

- [ ] **Ambiguous scope relationship to PR #471**: Research identifies PR #471 uses bash approach but does not explicitly recommend whether new script should:
  - Replace bash code in PR #471 templates (breaking change)
  - Coexist alongside bash code (duplication)
  - Be documented as alternative approach (requires coordination)

  **Impact**: Without clarifying relationship to PR #471, implementer may create Get-PRChecks.ps1 without addressing the bash text parsing fragility that motivated this extraction.

  **Recommendation**: Add "Integration with PR #471" section specifying whether new script replaces or augments bash approach.

### Important (Should Fix)

- [ ] **Missing acceptance criteria for extraction**: Recommendations list P0-P3 priorities but lack measurable success criteria. What constitutes "complete" for Get-PRChecks.ps1?

  **Example missing criteria**:
  - Passes all 13 unit tests migrated from Invoke-PRMaintenance.Tests.ps1
  - Returns same boolean result as Test-PRHasFailingChecks for equivalent input
  - Exit codes follow `.claude/skills/github/references/api-reference.md` patterns
  - Script added to SKILL.md decision tree

  **Recommendation**: Add "Extraction Acceptance Criteria" section with measurable outcomes.

- [ ] **Hypothesis validation path undefined**: Section 4 lists three hypotheses as "Unverified" but does not specify:
  - Whether hypotheses need verification before extraction
  - Who validates hypotheses (architect? implementer during extraction?)
  - What happens if hypotheses prove false

  **Example**: "GraphQL pagination limit of 100 contexts might be insufficient" - if true during implementation, does extraction abort or adapt?

  **Recommendation**: Clarify which hypotheses are blockers vs nice-to-know.

### Minor (Consider)

- [ ] **Test strategy for GraphQL wrapper**: Research references existing 13 unit tests for Test-PRHasFailingChecks but does not specify how to test the GraphQL query wrapper portion of Get-PRChecks.ps1.

  **Suggestion**: Reference existing GraphQL test patterns in Invoke-PRMaintenance.Tests.ps1 or `scripts/pr/Get-PRContext.Tests.ps1` for mocking `gh api graphql`.

- [ ] **PR #471 coordination risk**: Analysis concludes GraphQL approach is superior but PR #471 (already in review) implements bash approach. No guidance on merge conflict resolution if both land.

  **Suggestion**: Recommend filing issue with "depends on #471" or "supersedes #471" relationship to clarify sequencing.

## Questions for Planner

1. **Issue vs Augment**: Should this be a new issue or should it augment Issue #369?
   - Analyst research addresses root cause of #369 (missing CI verification)
   - PR #471 already addresses #369 with bash approach
   - New script would provide alternate (better) solution

2. **PR #471 Relationship**: If Get-PRChecks.ps1 is created:
   - Should PR #471 be updated to use new script before merge?
   - Should both approaches coexist (PowerShell + bash)?
   - Should new script supersede PR #471 entirely?

3. **Hypothesis Validation**: Are the three unverified hypotheses (REST API parity, pagination limits, rollup replication) blockers or can extraction proceed with documented limitations?

## Recommendations

### Before Implementation

1. **Clarify PR #471 integration strategy** - decide whether new script replaces, augments, or coexists with bash approach
2. **Add measurable acceptance criteria** - define success metrics for extraction completion
3. **Validate or defer hypotheses** - mark as blockers or document as future work

### During Implementation

1. **Reuse existing test patterns** - migrate 13 unit tests from Invoke-PRMaintenance.Tests.ps1
2. **Document REST API alternative** - if pagination limit hypothesis proves true, document REST fallback
3. **Update SKILL.md** - add Get-PRChecks.ps1 to decision tree

## Approval Conditions

**APPROVED** contingent on:

1. **Critical Issue Resolved**: Add "Integration with PR #471" section clarifying relationship (replace/augment/coexist)
2. **Important Issue Resolved**: Add "Extraction Acceptance Criteria" with measurable outcomes

Once these sections are added to the research document, implementer can proceed with extraction.

## Impact Analysis Review

N/A - This is research validation, not a plan with impact analysis.

## Handoff Recommendation

**Recommend orchestrator routes to planner** to create implementation plan addressing:
- PR #471 integration strategy
- Extraction milestones with acceptance criteria
- Test migration strategy

**Alternative**: If user confirms "create Get-PRChecks.ps1 as coexisting alternative to PR #471", route directly to implementer with:
- Analyst research (002-pr-checks-skill-extraction.md)
- This critique (001-pr-checks-extraction-critique.md)
- Acceptance criteria: Passes 13 migrated unit tests, follows GitHub skill exit code patterns, added to SKILL.md

---

## Critique Metadata

**Reviewed Document**: `.agents/analysis/002-pr-checks-skill-extraction.md`
**Reviewer**: critic agent
**Review Date**: 2025-12-28
**Verdict**: APPROVED WITH CONDITIONS
**Blocking Issues**: 1 Critical (PR #471 integration strategy)
**Next Agent**: planner (for implementation plan) OR user (for clarification on PR #471 relationship)
