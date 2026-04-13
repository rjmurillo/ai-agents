# Plan Critique: Local Guardrails Implementation

**Document ID**: CRITIQUE-051
**Date**: 2025-12-22
**Reviewer**: critic agent
**Documents Reviewed**:
- SPEC-local-guardrails.md
- PLAN-local-guardrails.md

## Verdict

**APPROVED WITH CONCERNS**

**Confidence Level**: HIGH (85%)

**Rationale**: The spec and plan are well-structured with clear requirements, phased implementation, and measurable acceptance criteria. The technical approach is sound and aligns with existing infrastructure (ADR-005, existing validation scripts). However, three important concerns exist around scope clarity, acceptance criteria specificity, and rollback strategy. These concerns do not block approval but require clarification before Phase 2 implementation begins.

## Summary

The Local Guardrails spec and plan define a comprehensive approach to preventing AI Quality Gate violations through local validation. The plan addresses 60% of preventable CRITICAL_FAIL cases with evidence-based requirements. Implementation is properly phased with clear dependencies and realistic success metrics.

## Strengths

### Evidence-Based Requirements

The spec includes quantified analysis of 8 PRs showing 60% Session Protocol CRITICAL_FAIL rate. Requirements directly address observed violation patterns with specific evidence.

### Phased Implementation Strategy

The plan breaks work into 6 distinct phases with clear dependencies. Phase 1 (Foundation) is complete. Phases 2-3 (Session Protocol + PR Description) can proceed independently before integration in Phase 4.

### Reuse of Existing Infrastructure

Plan correctly reuses Validate-SessionEnd.ps1 (DD-2) rather than duplicating logic. Aligns with ADR-005 (PowerShell-Only) and ADR-004 (Pre-commit Hooks).

### Measurable Acceptance Criteria

Each functional requirement includes checkboxes with verifiable outcomes. Example: FR-1 specifies exit codes (0=PASS, 1=FAIL, 2=ERROR) and integration with existing script.

### Escape Hatch Design

Plan includes `-Force` parameter with audit trail (Phase 4) to prevent blocking legitimate edge cases while maintaining accountability.

### Comprehensive Test Strategy

Plan defines Pester tests for each script with test categories (PASS, FAIL, edge cases, integration). Test strategy section provides clear verification approach.

## Concerns

### P1: FR-2 Acceptance Criteria Ambiguity

**Issue**: FR-2.3 states "Script issues WARNING when major changes are not mentioned" but does not define "major changes".

**Location**: SPEC-local-guardrails.md, lines 79-81

**Evidence**: No definition of thresholds for "major". Is this lines changed, files changed, or specific file patterns?

**Impact**: Implementer will need to make arbitrary decisions that may not align with intended behavior.

**Recommendation**: Add quantifiable criteria:
- "Major changes" = modifications to ≥3 files OR ≥50 lines changed OR changes to ADR files

**Skill Reference**: skill-requirements-002-verb-object-clarity requires explicit definitions to prevent ambiguity.

### P1: FR-4 Scope Creep Risk

**Issue**: FR-4 (Test Coverage Detection) is marked SHOULD (not MUST) but is included as Phase 5 without explicit approval gate.

**Location**: PLAN-local-guardrails.md, Phase 5 (lines 160-197)

**Evidence**: Spec Section "Scope Exclusions" (line 155) states "Only file presence checking" but FR-4 acceptance criteria (lines 97-101) include "documented test location patterns" which may require pattern analysis beyond simple file presence.

**Impact**: Phase 5 could expand beyond intended scope without explicit boundary definition.

**Recommendation**:
1. Add explicit scope boundary to FR-4: "Detection limited to filename pattern matching only (no AST analysis, no test execution)"
2. Require explicit approval before starting Phase 5 implementation

**Skill Reference**: skill-planning-004-approval-checkpoint requires user approval for multi-file infrastructure changes.

### P2: Success Metric Baseline Uncertainty

**Issue**: Success metrics table shows "Session Protocol CRITICAL_FAIL rate: 60%" as current baseline, but this is derived from n=8 PRs which is a small sample.

**Location**: SPEC-local-guardrails.md, lines 176-183; PLAN-local-guardrails.md, lines 286-293

**Evidence**: Only 3 of 8 PRs (37.5%) had Session Protocol CRITICAL_FAIL. The 60% figure appears to be calculated from different denominator.

**Impact**: Target of "<5%" may be unrealistic or already achieved depending on actual baseline.

**Recommendation**: Clarify baseline calculation methodology. Consider adding confidence interval: "60% ± 20% (n=8, small sample)". Re-measure after n=20 PRs.

**Skill Reference**: Style guide requires quantified data with evidence; avoid vague metrics without clear measurement basis.

### P2: Missing Rollback Strategy

**Issue**: Plan does not document rollback procedure if validations cause excessive false positives.

**Location**: PLAN-local-guardrails.md, Section "Risk Mitigation" (lines 276-283)

**Evidence**: Risk "False positives block valid PRs" is identified (High impact) with mitigation "provide escape hatch", but no rollback plan if `-Force` usage exceeds acceptable threshold.

**Impact**: If false positive rate is high, team may adopt `-Force` as default behavior, negating value of guardrails.

**Recommendation**: Add rollback criteria to Rollout Plan (Section, lines 256-275):
- If `-Force` bypass rate >30% in first 10 PRs, pause rollout for tuning
- If bypass rate remains >20% after tuning, roll back validation to WARNING-only mode

**Skill Reference**: Reversibility Assessment checklist requires documented rollback capability for new integrations.

### P2: Pre-commit Hook Performance Budget

**Issue**: NFR-1 specifies pre-commit total time SHOULD remain <10 seconds, but does not account for cumulative impact of multiple validations.

**Location**: SPEC-local-guardrails.md, lines 105-109

**Evidence**: Plan adds Test Coverage Detection (FR-4, <2s) to pre-commit. Existing pre-commit hook already includes ADR-005 validation. Cumulative budget unclear.

**Impact**: Incremental additions may degrade developer experience without triggering alert.

**Recommendation**: Add cumulative performance tracking:
- Document current pre-commit baseline execution time
- Require performance measurement before/after each integration
- Add budget: "Total pre-commit time must not exceed baseline + 5s"

## Questions for Planner

### Q1: Validation Sequencing in New-ValidatedPR.ps1

Phase 4 wrapper script design (lines 135-158) shows sequential execution:
1. Run Validate-PrePR.ps1
2. Run Validate-PRDescription.ps1
3. Call gh pr create

**Question**: Should PR description validation occur BEFORE session protocol validation? PR description can be validated faster (git diff only) and might catch issues earlier.

### Q2: Integration with Claude Code Workflow

NFR-3 (line 121) states "Integration with Claude Code SHOULD be seamless" but plan does not describe HOW this integration occurs.

**Question**: Should New-ValidatedPR.ps1 be added to `.claude/skills/github/skill.md` as a recommended command? Should orchestrator agent prompt templates reference this workflow?

### Q3: Test Coverage Ignore File Format

Phase 5 deliverable includes `.test-coverage-ignore` config file (line 20, 170) but format is not specified in plan.

**Question**: What is the expected format? Glob patterns? Explicit file paths? Comment syntax?

## Recommendations

### R1: Add Checkbox Manifest to Plan

Per skill-planning-001-checkbox-manifest, analysis documents with N recommendations require tracking manifest.

**Action**: Add implementation tracking section to PLAN-local-guardrails.md:

```markdown
## Implementation Tracking

- [ ] FR-1: Pre-PR Session Protocol Validation (Phase 2)
- [ ] FR-2: PR Description Validation (Phase 3)
- [ ] FR-3: Validated PR Creation Wrapper (Phase 4)
- [ ] FR-4: Test Coverage Detection (Phase 5)
- [ ] NFR-1: Performance budget verification
- [ ] NFR-2: Reliability edge case handling
- [ ] NFR-3: Claude Code integration
- [ ] NFR-4: Pester test coverage

Total Items: 8
Implemented: 0
Gap: 8
```

### R2: Add Section Cross-References to Plan Summary

Per skill-requirements-001-section-crossref, recommendation summaries should reference detailed specifications.

**Action**: Update PLAN-local-guardrails.md Deliverables table (lines 13-22) to include spec section references:

```markdown
| # | Deliverable | Spec Ref | Location |
|---|-------------|----------|----------|
| 1 | Validate-PrePR.ps1 | FR-1 | scripts/ |
...
```

### R3: Define "Pedagogical Error Message" Pattern

DD-4 (line 149) references "pedagogical error messages" pattern but does not provide template.

**Action**: Add error message template to plan:

```markdown
## Error Message Template

All validation failures must follow this structure:

**WHAT HAPPENED**: [One sentence describing the violation]

**WHY IT MATTERS**: [One sentence explaining the impact]

**HOW TO FIX**: [Numbered steps to resolve]

**Example**:
WHAT HAPPENED: Session log missing commit SHA in Session End checklist
WHY IT MATTERS: AI Quality Gate requires evidence of completion
HOW TO FIX:
1. Run: git log -1 --format="%H"
2. Update Session End checklist Evidence column with SHA
3. Commit session log update
```

### R4: Clarify Phase 5 Optional Status

Plan includes Phase 5 in dependency graph (lines 212-232) but FR-4 is marked SHOULD (optional).

**Action**: Add decision gate before Phase 5:

```markdown
### Phase 4.5: Phase 5 Go/No-Go Decision

After Phase 4 deployment, evaluate Phase 5 necessity:

**Decision Criteria**:
- If QA WARN rate drops to <20% without test coverage detection, skip Phase 5
- If bypass rate from Phase 2-4 is >20%, defer Phase 5 until tuning complete
- Otherwise, proceed with Phase 5

**Decision Owner**: Project maintainer
```

## Approval Conditions

The plan is approved for implementation with the following conditions:

### Before Phase 2 Implementation Begins

1. Resolve P1 concerns:
   - Define "major changes" threshold for FR-2.3
   - Add explicit scope boundary to FR-4
   - Add approval gate before Phase 5

2. Answer Q1 (validation sequencing) and update wrapper design accordingly

3. Answer Q3 (ignore file format) and document in Phase 5 tasks

### Before Phase 4 Integration

1. Answer Q2 (Claude Code integration) and update plan with integration steps

2. Implement R3 (error message template) and apply to all scripts

### Before Rollout (Phase 6)

1. Resolve P2 concerns:
   - Clarify success metric baseline methodology
   - Add rollback criteria to rollout plan
   - Measure and document pre-commit performance budget

## Impact Analysis Review

**Not Applicable**: This plan does not include specialist agent impact analysis.

**Recommendation**: Consider routing to security agent for quick review of validation bypass audit trail design (Phase 4, `-Force` escape hatch). Ensuring bypass events are logged appropriately prevents accountability gaps.

## Handoff Recommendation

**Status**: APPROVED WITH CONCERNS

**Recommended Next Agent**: implementer (via orchestrator)

**Handoff Context**:
- Plan is ready for implementation starting with Phase 2
- Planner must resolve P1 concerns and Q1/Q3 before implementation begins
- P2 concerns can be addressed during or after implementation but must be resolved before claiming completion
- Follow phased approach: complete Phase 2 → Phase 3 → Phase 4 integration → evaluate Phase 5 necessity

**Blocking Items for Phase 2 Start**:
1. Define "major changes" threshold (P1, FR-2)
2. Add FR-4 scope boundary (P1)
3. Answer Q1 (validation sequencing)
4. Answer Q3 (ignore file format)

## References

**Skills Applied**:
- skill-requirements-001-section-crossref
- skill-requirements-002-verb-object-clarity
- skill-planning-001-checkbox-manifest
- skill-planning-004-approval-checkpoint

**Documents Reviewed**:
- `.agents/specs/SPEC-local-guardrails.md`
- `.agents/planning/PLAN-local-guardrails.md`
- `.agents/SESSION-PROTOCOL.md` (referenced in spec)
- `.agents/architecture/ADR-005-powershell-only-scripting.md` (referenced in plan)
