---
status: accepted
date: 2025-12-26
decision-makers: ["architect", "user"]
consulted: ["qa", "devops", "security", "critic", "independent-thinker", "high-level-advisor"]
informed: ["implementer", "analyst"]
---

# ADR-023: Quality Gate Prompt Structural Validation

## Context and Problem Statement

The AI PR Quality Gate prompts (`pr-quality-gate-qa.md`, `pr-quality-gate-security.md`, `pr-quality-gate-devops.md`) control critical CI/CD decision-making. Changes to these prompts can cause:

1. **False CRITICAL_FAIL** - Blocks legitimate PRs (Issue #357)
2. **False PASS** - Allows problematic PRs to merge
3. **Inconsistent behavior** - Different gates apply different standards

Prior to this ADR, prompt changes were validated manually by testing against sample PRs. This approach:

- Was time-consuming and error-prone
- Missed regressions when only some scenarios were tested
- Had no repeatability guarantee

## Decision Drivers

1. **Structural Consistency**: Prompts must maintain required sections and formatting
2. **Fast Feedback**: Developers should know immediately if structural changes break requirements
3. **Documentation as Tests**: Tests serve as executable documentation of prompt requirements
4. **CI Integration**: Tests must run in automated pipelines
5. **Maintainability**: Tests should be easy to update when prompts intentionally change

## Considered Options

### Option 1: Manual Testing (Status Quo)

Test prompt changes by manually running against sample PRs.

**Pros**: No infrastructure needed, flexible
**Cons**: Time-consuming, error-prone, no repeatability, missed scenarios

### Option 2: Pester Structural Tests (Chosen)

Automated tests validating prompt structure, required sections, and consistency.

**Pros**: Fast feedback, repeatable, documents requirements, CI-integrated
**Cons**: Cannot validate runtime AI behavior, maintenance burden when prompts change

### Option 3: Runtime AI Response Tests

Execute prompts against sample PRs with actual AI, validate verdicts.

**Pros**: Tests actual behavior, catches AI interpretation errors
**Cons**: Expensive (API costs), nondeterministic results, slow execution, complex infrastructure

## Decision Outcome

**Chosen option**: "Pester Structural Tests", because it provides immediate, repeatable validation of prompt structure with minimal infrastructure overhead, while acknowledging that runtime behavioral validation is out of scope.

Implement a Pester test suite (`tests/QualityGatePrompts.Tests.ps1`) that validates:

1. **Structural requirements** - All prompts have required sections
2. **Category classification** - File to category mapping is consistent
3. **PR type detection** - Mixed vs single-type detection logic exists
4. **DOCS-only exemptions** - All gates document DOCS exemption from CRITICAL_FAIL
5. **Expected patterns** - False positive prevention patterns are documented
6. **Cross-prompt consistency** - Same terminology across all gates

### Limitations (Critical)

**Structural tests do NOT validate runtime AI interpretation.** A prompt can pass all structural tests while producing incorrect AI verdicts. Issue #357 (AI returning CRITICAL_FAIL for DOCS-only PRs) was an AI interpretation error that structural tests cannot catch.

These tests reduce regression risk for structural changes but do not guarantee correct AI behavior.

### Test Execution Requirements

**MUST run before merging any PR that modifies**:

| File Pattern | Reason |
|--------------|--------|
| `.github/prompts/pr-quality-gate-*.md` | Direct prompt changes |
| `tests/QualityGatePrompts.Tests.ps1` | Test suite changes |

**Execution command**:

```powershell
Invoke-Pester tests/QualityGatePrompts.Tests.ps1 -Output Detailed
```

## Consequences

### Positive

- Prompt changes get immediate structural validation feedback
- Tests document expected prompt structure and required sections
- Cross-prompt consistency is enforced automatically
- New contributors understand prompt requirements via tests

### Negative

- Tests must be updated when prompts intentionally change
- Tests validate structure only, not runtime AI behavior
- High test count (84) may create maintenance burden

### Neutral

- Test suite adds ~590 lines of PowerShell
- Adds ~4 seconds to CI when prompts change

## Confirmation

Compliance verified by:

1. CI workflow runs `QualityGatePrompts.Tests.ps1` on PRs modifying prompt files
2. PR cannot merge if structural tests fail
3. Code review verifies new prompt patterns have corresponding tests
4. Test execution time remains under 10 seconds

## Out of Scope

The following are explicitly NOT addressed by this ADR:

1. **Runtime AI behavior validation** - Tests cannot verify AI interprets prompts correctly
2. **Efficacy testing** - No validation that security prompts detect actual vulnerabilities
3. **Golden corpus testing** - No known-vulnerable samples for AI response validation
4. **Prompt injection resilience** - Adversarial testing of prompts not included

These items are tracked as potential future work.

## Reversibility Assessment

| Criterion | Assessment |
|-----------|------------|
| Rollback capability | Tests can be removed without affecting prompts |
| Vendor lock-in | Pester is open-source, cross-platform |
| Exit strategy | Switch to alternative framework with test rewrite |
| Legacy impact | None; additive change only |
| Data migration | N/A; no persistent state |

**Reversal triggers**: If test maintenance burden exceeds 30 minutes per prompt change, or if tests consistently fail for non-behavioral reasons, reconsider approach.

## Compliance Notes

This decision aligns with:

- **ADR-005**: PowerShell-only scripting (tests use Pester)
- **ADR-006**: Thin workflows (tests are standalone, not embedded in workflows)
- **ADR-010**: Quality gate patterns (extends existing infrastructure)

## Test Categories

| Category | Test Count | Purpose |
|----------|------------|---------|
| Prompt Structure | 19 | Verify required sections exist |
| File Category Classification | 24 | CODE, DOCS, WORKFLOW, etc. mapping |
| PR Type Detection | 7 | Single-type vs MIXED detection |
| DOCS-Only Handling | 7 | CRITICAL_FAIL exemption |
| Expected Patterns | 12 | False positive prevention |
| CRITICAL_FAIL Triggers | 9 | Context-aware thresholds |
| Cross-Prompt Consistency | 6 | Terminology alignment |
| **Total** | **84** | |

## References

- [Issue #357](https://github.com/rjmurillo/ai-agents/issues/357) - Motivating bug report
- [Issue #77](https://github.com/rjmurillo/ai-agents/issues/77) - Known blocker: QA agent cannot run Pester tests
- [PR #465](https://github.com/rjmurillo/ai-agents/pull/465) - Complementary matrix aggregation fix
- [PRD-quality-gate-prompt-refinement](/.agents/planning/PRD-quality-gate-prompt-refinement.md) - Implementation PRD
- [ADR-010](/.agents/architecture/ADR-010-quality-gates-evaluator-optimizer.md) - Quality gate patterns
- [Pester Documentation](https://pester.dev/) - Test framework
- [Debate Log](/.agents/critique/ADR-023-debate-log.md) - Multi-agent review record
