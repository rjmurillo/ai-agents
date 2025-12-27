---
status: accepted
date: 2025-12-26
decision-makers: ["architect", "user"]
consulted: ["qa", "devops"]
informed: ["implementer", "analyst"]
---

# ADR-021: Quality Gate Prompt Testing Requirements

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

1. **Regression Prevention**: Prompt changes must not break existing behavior
2. **Fast Feedback**: Developers should know immediately if changes break tests
3. **Documentation as Tests**: Tests serve as executable documentation of prompt requirements
4. **CI Integration**: Tests must run in automated pipelines
5. **Maintainability**: Tests should be easy to update when prompts intentionally change

## Decision

Implement a Pester test suite (`tests/QualityGatePrompts.Tests.ps1`) that validates:

1. **Structural requirements** - All prompts have required sections
2. **Category classification** - File → category mapping is correct
3. **PR type detection** - Mixed vs single-type detection works
4. **DOCS-only exemptions** - All gates exempt DOCS from CRITICAL_FAIL
5. **Expected patterns** - False positive prevention patterns exist
6. **Cross-prompt consistency** - Same terminology across all gates

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

**CI Integration** (recommended):

Add to `.github/workflows/ci.yml`:

```yaml
- name: Test Quality Gate Prompts
  if: |
    contains(github.event.pull_request.changed_files, '.github/prompts/pr-quality-gate') ||
    contains(github.event.pull_request.changed_files, 'tests/QualityGatePrompts.Tests.ps1')
  run: |
    pwsh -Command "Invoke-Pester tests/QualityGatePrompts.Tests.ps1 -CI -Output Detailed"
```

## Consequences

### Positive

- Prompt changes get immediate regression feedback
- Tests document expected prompt behavior
- False positive fixes are verified before merge
- New contributors understand prompt requirements via tests

### Negative

- Tests must be updated when prompts intentionally change
- Tests validate structure, not runtime behavior (runtime requires AI execution)

### Neutral

- Test suite adds ~590 lines of PowerShell
- Adds ~4 seconds to CI when prompts change

## Compliance Notes

This decision aligns with:

- **ADR-005**: PowerShell-only scripting (tests use Pester)
- **ADR-006**: Thin workflows (tests are standalone, not embedded in workflows)

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
- [PRD-quality-gate-prompt-refinement](/.agents/planning/PRD-quality-gate-prompt-refinement.md) - Implementation PRD
- [Pester Documentation](https://pester.dev/) - Test framework
