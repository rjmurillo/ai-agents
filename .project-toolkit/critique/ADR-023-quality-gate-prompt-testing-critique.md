# Plan Critique: ADR-023 Quality Gate Prompt Testing Requirements

**Date**: 2025-12-27
**Critic**: critic agent
**ADR**: ADR-021
**Related PRD**: issue-357-aggregation-fix-plan.md
**Verdict**: **NEEDS REVISION**

---

## Summary

ADR-021 proposes a Pester test suite (84 tests, 590 lines) to validate AI Quality Gate prompts and prevent regressions like Issue #357. The ADR correctly identifies structural testing requirements and demonstrates implementation with comprehensive test coverage. However, critical gaps exist in CI integration, runtime validation strategy, and maintenance burden assessment.

---

## Strengths

1. **Evidence-based motivation**: Issue #357 provides concrete failure mode
2. **Quantified scope**: 84 tests across 6 categories with specific coverage targets
3. **Implementation complete**: Tests exist at `tests/QualityGatePrompts.Tests.ps1` (590 lines)
4. **Compliance alignment**: References ADR-005 (PowerShell-only) and ADR-006 (thin workflows)
5. **Real-world validation**: Tests include regression scenarios from actual PRs (#462, #437, #438, #458, #401)
6. **Fast execution**: Claims ~4 seconds CI overhead (requires verification)

---

## Issues Found

### Critical (Must Fix)

#### P0-1: CI Integration Not Implemented

**Location**: ADR lines 59-70 (CI Integration section)

**Issue**: ADR claims "recommended" CI integration but provides no evidence of implementation.

**Evidence**:
- Workflow analysis shows `pester-tests.yml` does NOT include `QualityGatePrompts.Tests.ps1`
- Current testable paths (line 52-58 of `pester-tests.yml`): `scripts/**`, `build/**`, `.github/scripts/**`, `.claude/skills/**`, `tests/**`
- `.github/prompts/` is NOT in the testable paths trigger list
- Test invocation script (`Invoke-PesterTests.ps1` line 68) does NOT include `tests/` directory in default test paths

**Impact**: Prompt changes can merge without regression testing, defeating the entire purpose of ADR-021.

**Recommendation**:
1. Add `.github/prompts/pr-quality-gate-*.md` to `pester-tests.yml` testable paths (line 52-58)
2. Add `tests/` to default test paths in `Invoke-PesterTests.ps1` (line 68)
3. Verify test execution in CI with test PR modifying a prompt file

**Priority Justification**: Without CI integration, tests provide zero regression prevention.

---

#### P0-2: Runtime Behavior Gap Not Addressed

**Location**: ADR line 84 (Negative consequences)

**Issue**: ADR acknowledges "tests validate structure, not runtime behavior" but provides no strategy for runtime validation.

**Evidence**:
- Tests validate prompt structure (sections exist, patterns present)
- Tests do NOT validate AI model responses to prompts
- Issue #357 root cause: AI agents returned `CRITICAL_FAIL` for DOCS-only PRs
- Test suite cannot detect if prompt changes cause AI to ignore DOCS-only exemption rules

**Example Gap**:
```powershell
# Test validates pattern exists (line 294-296):
It "Should state DOCS require no tests" {
    $script:QAContent | Should -Match "DOCS.*None required"
}
```

This test PASSES if text exists, but cannot verify if AI interprets it correctly at runtime.

**Missing Validation Strategy**:
- No mention of prompt validation against real PR scenarios
- No AI response smoke tests
- No monitoring of AI verdict accuracy over time

**Recommendation**:
1. Add "Runtime Validation" section to ADR describing:
   - Manual validation protocol for prompt changes (test against sample PRs)
   - AI response monitoring (track DOCS-only PR verdicts in production)
   - Escalation criteria (3+ false positives triggers prompt audit)
2. Reference this limitation explicitly in "Decision" section
3. Consider Phase 2 work item: automated AI response regression tests

**Priority Justification**: Current approach provides false sense of security - passing tests do NOT guarantee prompts work correctly.

---

#### P0-3: Test Maintenance Burden Unquantified

**Location**: ADR line 82 (Negative consequences)

**Issue**: "Tests must be updated when prompts intentionally change" - no estimate of maintenance cost or guidelines.

**Evidence**:
- 84 tests across 6 categories
- Tests are tightly coupled to prompt structure (exact section names, text patterns)
- No versioning strategy for prompts
- No guidance on when to update tests vs. when to reject prompt changes

**Example Brittle Test** (line 294-296):
```powershell
It "Should state DOCS require no tests" {
    $script:QAContent | Should -Match "DOCS.*None required"
}
```

If prompt rewording changes "None required" to "Not required", test fails even though behavior is identical.

**Missing Maintenance Strategy**:
- How to distinguish intentional prompt changes from regressions?
- Who validates test updates are correct vs. test bugs?
- What percentage of prompt changes require test updates?

**Recommendation**:
1. Add "Maintenance Protocol" section:
   - Test updates require architect approval (prevent test weakening)
   - Prompt changes that fail tests must document rationale
   - Annual test suite audit to reduce brittleness
2. Quantify expected maintenance: "Estimated 15-30 min test updates per prompt change"
3. Add test design guideline: "Test behavior, not exact wording"

**Priority Justification**: High maintenance burden without clear process will lead to test rot or prompt change resistance.

---

### Important (Should Fix)

#### P1-1: Missing Rollback Capability Assessment

**Location**: No reversibility section

**Issue**: ADR adds 590 lines of test code with CI dependency but provides no rollback strategy.

**Rollback Scenarios**:
- Tests have high false positive rate (block valid prompt improvements)
- Maintenance burden exceeds value (tests become outdated)
- Test execution time exceeds 4s estimate (slows CI)

**Recommendation**: Add "Rollback Plan" section:
- Detection criteria: 3+ test failures requiring test fixes vs. prompt fixes
- Removal procedure: Remove from `pester-tests.yml`, keep tests in repo as reference
- Fallback: Manual prompt validation protocol

---

#### P1-2: Cross-Prompt Consistency Tests May Be Too Strict

**Location**: Lines 107-109 (Test categories) - "Cross-Prompt Consistency: 6 tests"

**Issue**: Enforcing identical terminology across all gates may prevent domain-specific language.

**Evidence** (from test suite lines 548-590):
- Tests require exact match: `| DOCS |` in all prompts
- Tests require exact verdict format in all prompts
- Security vs. DevOps may need different terminology for same concept

**Example**: Security prompt may need "CWE-XX" references while QA prompt needs "test coverage %" - forcing identical terms loses domain specificity.

**Recommendation**:
1. Review consistency tests for over-constraint
2. Allow domain-specific terminology where appropriate
3. Focus consistency tests on verdict format and DOCS exemption (critical), not all terminology

---

#### P1-3: Test Coverage Gaps in MIXED PR Handling

**Location**: Lines 268-283 (PR Type Detection - Mixed PRs)

**Issue**: Tests verify MIXED detection but do NOT verify per-file rule application.

**Evidence**:
- Test verifies PR classified as MIXED (line 269-271, 274-276, 279-281)
- Test does NOT verify CODE rules applied to `.ps1` files in MIXED PR
- Test does NOT verify DOCS exemption applied to `.md` files in MIXED PR

**Real-World Scenario** (PR #458):
- Files: `.ps1` (CODE), `.Tests.ps1` (CODE), `.md` (DOCS)
- Expected: Test coverage required for `.ps1`, not required for `.md`
- Current tests: Verify PR is MIXED, do NOT verify per-file behavior

**Recommendation**: Add test category "MIXED PR Per-File Rules" with tests like:
```powershell
It "Should apply CODE rules to .ps1 in MIXED PR" {
    # Verify prompt specifies per-file rule application for MIXED
}
```

---

### Minor (Consider)

#### P2-1: Test Count Mismatch in Documentation

**Location**: Line 88 (Neutral consequences) vs. Line 109 (Test categories table)

**Issue**: Claims "~590 lines of PowerShell" but does not verify test count accuracy.

**Evidence**:
- Table claims 84 total tests (line 109)
- Manual verification required to confirm

**Recommendation**: Add verification step to ADR: "Test count verified via `Invoke-Pester -DryRun`"

---

#### P2-2: No False Positive Rate Target

**Location**: Lines 75-79 (Positive consequences)

**Issue**: Claims "tests document expected prompt behavior" but sets no acceptable false positive rate for tests themselves.

**Recommendation**: Add success metric: "Test false positive rate <5% (test failures requiring test fixes, not prompt fixes)"

---

#### P2-3: Missing Test Execution Time Baseline

**Location**: Line 89 (Neutral consequences) - "Adds ~4 seconds to CI"

**Issue**: No evidence provided for 4-second estimate.

**Recommendation**: Add verification evidence: "Measured via local Pester execution: [actual time]"

---

## Questions for Architect

1. **CI Integration Intent**: Is CI integration mandatory or optional? ADR says "recommended" but lack of implementation suggests optional. Clarify decision.

2. **Runtime Validation Strategy**: How will the project detect when passing structural tests still result in incorrect AI behavior?

3. **Maintenance Ownership**: Who is responsible for updating tests when prompts intentionally change? How to prevent test weakening over time?

4. **Phase 2 Scope**: Should runtime validation (AI response testing) be added to this ADR or deferred to future work?

5. **Test Brittleness Trade-off**: Current tests are tightly coupled to exact prompt text. Is this acceptable or should tests be redesigned for flexibility?

---

## Recommendations

### Immediate Actions (Before Approval)

1. **Implement CI integration** (P0-1):
   - Add `.github/prompts/` to `pester-tests.yml` trigger paths
   - Add `tests/` to default test paths in `Invoke-PesterTests.ps1`
   - Create test PR to verify execution

2. **Add Runtime Validation section** (P0-2):
   - Document manual validation protocol
   - Define AI verdict monitoring strategy
   - Set escalation criteria for false positives

3. **Add Maintenance Protocol section** (P0-3):
   - Define approval process for test updates
   - Quantify expected maintenance effort
   - Add test design guidelines

4. **Add Rollback Plan** (P1-1):
   - Define removal criteria
   - Document fallback validation approach

### Long-Term Improvements (Post-Approval)

1. **Runtime validation automation**: Develop AI response regression tests using sample PRs
2. **Test brittleness reduction**: Refactor tests to check behavior patterns vs. exact text
3. **MIXED PR test coverage**: Add per-file rule application tests

---

## Approval Conditions

### Blocking Issues (Must Resolve)

| Issue | Resolution Required | Evidence Needed |
|-------|---------------------|------------------|
| P0-1: CI Integration | Implement in `pester-tests.yml` and `Invoke-PesterTests.ps1` | CI workflow run showing test execution |
| P0-2: Runtime Validation Gap | Add section to ADR documenting strategy | ADR updated with validation protocol |
| P0-3: Maintenance Burden | Add section quantifying effort and process | ADR updated with maintenance protocol |

### Advisory Issues (Recommend Resolving)

| Issue | Resolution Required | Evidence Needed |
|-------|---------------------|------------------|
| P1-1: Rollback Plan | Add rollback section to ADR | ADR updated with removal criteria |
| P1-2: Cross-Prompt Consistency | Review tests for over-constraint | Test suite updated or rationale documented |
| P1-3: MIXED PR Coverage | Add per-file rule tests or defer to Phase 2 | Test updates or Phase 2 work item created |

---

## Verdict Details

**Status**: NEEDS REVISION

**Confidence**: HIGH

**Rationale**:
- ADR demonstrates strong technical implementation (590-line test suite exists and covers 84 test cases)
- Critical gap: CI integration recommended but not implemented, allowing regressions to slip through
- Major gap: Tests validate structure but cannot detect runtime AI behavior failures
- Maintenance strategy missing, creating risk of test rot or prompt change resistance
- 3 P0 issues must be resolved before approval
- Implementation quality is high, but decision documentation is incomplete

**Estimated Revision Effort**: 4-6 hours
- 2 hours: Implement CI integration and verify
- 2 hours: Document runtime validation and maintenance protocols
- 1 hour: Add rollback plan
- 1 hour: Review and address P1 issues

---

## Next Steps

1. **Architect**: Address P0-1 (CI integration) by updating workflow files
2. **Architect**: Address P0-2 and P0-3 by adding ADR sections
3. **Critic**: Re-review updated ADR for approval
4. **Implementer**: Execute CI integration changes once approved

**Recommendation**: Route to architect for ADR revision addressing P0 issues.
