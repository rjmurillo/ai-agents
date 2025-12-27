# Related Work Research: ADR-023 Quality Gate Prompt Testing

**ADR**: ADR-023: Quality Gate Prompt Testing Requirements
**Research Date**: 2025-12-27
**Researcher**: analyst agent

## Executive Summary

ADR-021 establishes Pester test requirements for AI PR Quality Gate prompts. Research identified 11 related open issues and 8 active PRs that intersect with quality gate infrastructure, testing, and false positive prevention. Critical dependencies include PR #465 (surfacing matrix failures) and Issue #357 (root cause of ADR).

## Related Issues

### Direct Dependencies

| # | Title | Status | Priority | Relevance |
|---|-------|--------|----------|-----------|
| [#357](https://github.com/rjmurillo/ai-agents/issues/357) | fix(ci): investigate and fix AI PR Quality Gate aggregation failures | Open | P0 | **ROOT CAUSE** - Motivating bug that led to ADR-021 |
| [#77](https://github.com/rjmurillo/ai-agents/issues/77) | fix: QA agent cannot run Pester tests due to permission restrictions | Open | P1 | **BLOCKING** - QA agent cannot execute tests ADR requires |
| [#258](https://github.com/rjmurillo/ai-agents/issues/258) | agent/qa: Add mandatory pre-PR quality gate enforcement | Open | P1 | Extends ADR-021 to enforce tests before PR creation |

### Infrastructure & Testing Gaps

| # | Title | Status | Priority | Relevance |
|---|-------|--------|----------|-----------|
| [#164](https://github.com/rjmurillo/ai-agents/issues/164) | feat(ci): Distinguish infrastructure failures from code quality failures in AI Quality Gate | Open | P1 | Complements ADR test focus - separate infra vs quality failures |
| [#444](https://github.com/rjmurillo/ai-agents/issues/444) | Test Strategy Overhaul: Address Mock Fidelity and Integration Testing Gaps | Open | P1 | Broader test quality initiative that includes ADR-021 scope |
| [#117](https://github.com/rjmurillo/ai-agents/issues/117) | test: Add Pester tests for Post-IssueComment.ps1 idempotent skip behavior | Open | P2 | Example of Pester test expansion (same pattern as ADR) |
| [#291](https://github.com/rjmurillo/ai-agents/issues/291) | Enhancement: Improve Pester test coverage for Detect-CopilotFollowUpPR.ps1 | Open | P2 | Pester test coverage improvement (aligns with ADR goal) |

### False Positive Prevention

| # | Title | Status | Priority | Relevance |
|---|-------|--------|----------|-----------|
| [#328](https://github.com/rjmurillo/ai-agents/issues/328) | feat: Add retry logic for infrastructure failures in AI Quality Gate | Closed | P1 | Addressed infra false positives (ADR addresses prompt false positives) |
| [#329](https://github.com/rjmurillo/ai-agents/issues/329) | feat: Categorize AI Quality Gate failures (infrastructure vs code quality) | Closed | P1 | Categorization pattern mirrors ADR's PR Type Detection |
| [#74](https://github.com/rjmurillo/ai-agents/issues/74) | fix: AI PR Quality Gate returns exit code 1 on idempotent skip | Closed | P0 | Exit code false positive (ADR prevents CRITICAL_FAIL false positives) |

### Enhancement & Workflow

| # | Title | Status | Priority | Relevance |
|---|-------|--------|----------|-----------|
| [#152](https://github.com/rjmurillo/ai-agents/issues/152) | Enhance AI Quality Gate to notify PR authors when action required | Open | P2 | UX improvement on top of ADR-021 foundation |
| [#157](https://github.com/rjmurillo/ai-agents/issues/157) | Enhance QA agent prompt with test quality criteria | Open | - | QA agent test generation quality (orthogonal to ADR) |
| [#172](https://github.com/rjmurillo/ai-agents/issues/172) | feat: Formalize SPARC-like Development Methodology with Quality Gates | Open | P2 | Strategic vision for quality gates (ADR is tactical piece) |

## Related Pull Requests

### Critical Path

| # | Title | Branch | Status | Relevance |
|---|-------|--------|--------|-----------|
| [#465](https://github.com/rjmurillo/ai-agents/pull/465) | fix(ci): Surface AI Quality Gate failures at matrix job level | `copilot/fix-ai-quality-gate-errors` | Open | **CRITICAL** - Fixes matrix-level aggregation (#357) |
| [#353](https://github.com/rjmurillo/ai-agents/pull/353) | fix(ci): emit WARN for Copilot auth failures instead of CRITICAL_FAIL | `fix/copilot-auth-warn-not-block-v2` | Open | False positive fix (WARN vs CRITICAL_FAIL pattern) |

### Related Work

| # | Title | Branch | Status | Relevance |
|---|-------|--------|--------|-----------|
| [#460](https://github.com/rjmurillo/ai-agents/pull/460) | [WIP] Investigate and fix AI PR Quality Gate aggregation failures | `copilot/fix-ai-pr-quality-gate` | Open | WIP investigation of #357 (likely superseded by #465) |
| [#269](https://github.com/rjmurillo/ai-agents/pull/269) | docs(orchestrator): add Phase 4 pre-PR validation workflow and HANDOFF-TERMS.md | `copilot/add-pre-pr-validation-workflow` | Open | Pre-PR validation (complements ADR's testing focus) |
| [#322](https://github.com/rjmurillo/ai-agents/pull/322) | feat: Implement PR merge state verification to prevent wasted review effort | `feat/pr-review-merge-state-verification` | Open | Quality gate enhancement (validates PR state) |
| [#255](https://github.com/rjmurillo/ai-agents/pull/255) | feat(github-skill): enhance skill for Claude effectiveness | `feat/skill-leverage` | Open | GitHub skill improvements (may improve test execution) |
| [#365](https://github.com/rjmurillo/ai-agents/pull/365) | fix(memory): rename skill- prefix files and add naming validation | `fix/memories` | Open | Memory infrastructure (indirect) |
| [#235](https://github.com/rjmurillo/ai-agents/pull/235) | feat(github-skills): add issue comments support to Get-PRReviewComments | `fix/fetch-issue-comments` | Open | GitHub API improvements (indirect) |

## Closed Issues Analysis

### Patterns Resolved

| # | Title | Resolution | Lessons for ADR |
|---|-------|------------|-----------------|
| [#328](https://github.com/rjmurillo/ai-agents/issues/328) | Add retry logic for infrastructure failures | Retry with backoff | Infrastructure failures need different handling than quality failures |
| [#329](https://github.com/rjmurillo/ai-agents/issues/329) | Categorize AI Quality Gate failures | Implemented categorization | ADR's PR Type Detection mirrors this pattern |
| [#338](https://github.com/rjmurillo/ai-agents/issues/338) | Add retry logic with backoff for Copilot CLI failures | Retry mechanism | Transient failures should not cause CRITICAL_FAIL |
| [#74](https://github.com/rjmurillo/ai-agents/issues/74) | AI PR Quality Gate returns exit code 1 on idempotent skip | Fixed exit code handling | Exit codes need careful design (test suite must check this) |
| [#230](https://github.com/rjmurillo/ai-agents/issues/230) | Implement Technical Guardrails for Autonomous Agent Execution | Guardrails implemented | Quality gates are part of broader guardrail system |

## Implications for ADR Review

### 1. Known Gaps That Affect ADR-021

**Issue #77 (P1)**: QA agent cannot run Pester tests due to permission restrictions
- **Impact**: ADR requires QA agent to run tests, but agent lacks permissions
- **Action**: Link #77 as prerequisite or document workaround
- **Recommendation**: ADR should note this limitation until #77 is resolved

**Issue #357 (P0)**: Root cause issue still open
- **Impact**: ADR addresses prompt-level false positives, but matrix aggregation bug remains
- **Action**: ADR should reference PR #465 as complementary fix
- **Recommendation**: Test suite should include matrix-level aggregation validation

### 2. Strategic Alignment

**Issue #172**: SPARC-like Development Methodology
- ADR-021 is a tactical implementation of the strategic vision
- Test suite is an example of shift-left validation
- Should be referenced in broader methodology documentation

**Issue #444**: Test Strategy Overhaul
- ADR-021's Pester suite is part of larger test quality initiative
- Recommend coordination to ensure ADR tests align with overhaul principles
- Mock fidelity concerns may apply to prompt testing

### 3. Integration Points

**PR #269**: Pre-PR validation workflow
- ADR tests should be part of pre-PR validation
- Ensure `Validate-PrePR.ps1` includes prompt testing
- Add to orchestrator Phase 4 checklist

**Issue #164**: Distinguish infrastructure vs code quality failures
- ADR focuses on prompt correctness (quality)
- Should integrate with infra failure categorization
- Test suite should validate categorization logic

### 4. False Positive Prevention Patterns

Closed issues reveal pattern:
1. Categorize failures (infra vs quality)
2. Add retry for transient failures
3. Context-aware thresholds (DOCS vs CODE)
4. Expected patterns documentation

ADR-021 implements items 3 and 4. Test suite should verify these patterns persist through prompt changes.

### 5. Recommendations for ADR Linkage

**Should link in ADR References section**:
- Issue #357 - Root cause (already linked)
- Issue #77 - Known blocker for QA agent test execution
- Issue #164 - Complementary categorization work
- PR #465 - Complementary aggregation fix
- Issue #444 - Broader test strategy context

**Should NOT link** (too indirect):
- #328, #329, #338 (already resolved)
- #255, #365 (infrastructure improvements)

## Data Transparency

### Evidence Found

- **11 open issues** directly related to quality gates, testing, or false positives
- **8 active PRs** with overlapping concerns
- **5 closed issues** showing historical false positive patterns
- **PRD document** (`PRD-quality-gate-prompt-refinement.md`) confirming ADR context
- **Test suite** (`tests/QualityGatePrompts.Tests.ps1`) referenced exists with 84 tests

### Evidence Not Found

- No evidence of prior prompt testing framework (ADR introduces this capability)
- No evidence of runtime prompt behavior testing (ADR acknowledges this limitation)
- No evidence of automated prompt regression detection before ADR

## Conclusion

ADR-021 is well-positioned within the broader quality gate improvement effort. The test suite addresses a known gap (regression testing for prompts) and complements ongoing work in infrastructure failure handling (#164), matrix aggregation (#465), and test strategy (#444).

**Critical dependency**: Issue #77 blocks QA agent test execution. ADR should document this limitation.

**Strategic alignment**: ADR supports shift-left validation strategy (#172, #269) and broader test quality initiative (#444).

**Recommendation**: Approve ADR-021 with note to link Issue #77 and PR #465 in References section.
