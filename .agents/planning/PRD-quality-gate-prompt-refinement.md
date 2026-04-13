# PRD: AI PR Quality Gate Prompt Refinement

**Issue**: [#357](https://github.com/rjmurillo/ai-agents/issues/357)
**Status**: Implementation Complete
**Author**: Claude Code
**Created**: 2025-12-26

## Problem Statement

The AI PR Quality Gate was issuing false CRITICAL_FAIL verdicts for documentation-only PRs. Root cause analysis revealed the prompts lacked context-aware evaluation - they applied the same CRITICAL_FAIL triggers regardless of PR type, causing:

1. Documentation PRs flagged for "missing tests" when no code was changed
2. False security warnings for example/placeholder credentials in docs
3. CI noise that trained maintainers to ignore quality gate results

## Solution Summary

Applied prompt engineering patterns from the single-turn reference to add:

1. **PR Type Detection** - Categorize PRs before evaluation (DOCS, CODE, WORKFLOW, CONFIG, MIXED)
2. **Expected Patterns** - Document acceptable patterns that should NOT trigger warnings
3. **Context-Aware CRITICAL_FAIL** - Different thresholds by PR type (DOCS exempt from most triggers)
4. **Affirmative Directives** - Replace negative "don't do X" with "do Y instead"
5. **Error Normalization** - Document expected edge cases as normal behavior

## Changes Made

### Quality Gate Prompts

| Prompt | Changes |
|--------|---------|
| `pr-quality-gate-qa.md` | Added PR Type Detection, Expected Patterns (generated files, test files, type definitions), Context-Aware Verdict Thresholds |
| `pr-quality-gate-security.md` | Added PR Type Detection, Expected Patterns (example API keys, test fixtures), Context-Aware CRITICAL_FAIL |
| `pr-quality-gate-devops.md` | Added PR Scope Detection, Expected Patterns (ubuntu-latest, tag-pinned actions), Context-Aware CRITICAL_FAIL by category |

### Orchestrator Prompts

| Prompt | Changes |
|--------|---------|
| `.claude/agents/orchestrator.md` | Added Task Type Triage table, Reliability Principles (Delegation > Memory), Affirmative Directives, Error Normalization |
| `templates/agents/orchestrator.shared.md` | Same changes (template sync) |

### Verification Infrastructure

| File | Purpose |
|------|---------|
| `tests/QualityGatePrompts.Tests.ps1` | 84-test Pester suite for regression testing prompt changes |

## Prompt Engineering Patterns Applied

### Single-Turn Patterns

| Pattern | Applied To | Effect |
|---------|------------|--------|
| Conditional Sections | All prompts | PR Type Detection tables |
| Category-Based Generalization | File categorization | CODE, DOCS, WORKFLOW, etc. |
| Affirmative Directives | Orchestrator | Replaced FORBIDDEN with "Delegate to specialists" |
| Scope Limitation | CRITICAL_FAIL triggers | "For DOCS-only: PASS unless..." |
| Error Normalization | Expected Patterns | Document acceptable patterns |
| Contrastive Examples | Orchestrator | CORRECT vs INCORRECT examples |

### Reliability Principles (Orchestrator)

From user feedback, captured in orchestrator:

1. **Delegation > Memory**: Passing artifacts to sub-agents is 10x more reliable than memory
2. **Freshness First**: If not using tools NOW, working with stale data
3. **Plan Before Execute**: Outline logic before API/code execution

## Validation Results

Tested against real PRs across all categories:

| PR | Type | Result | Notes |
|----|------|--------|-------|
| #462 | DOCS-only | PASS | Correctly exempted from CRITICAL_FAIL |
| #437 | CODE | PASS | No regressions |
| #438 | WORKFLOW | PASS | No regressions |
| #458 | MIXED | PASS | No regressions |

## Regression Test Suite

Created `tests/QualityGatePrompts.Tests.ps1` with 84 tests covering:

- **File Category Classification** (24 tests) - CODE, DOCS, WORKFLOW, PROMPT, ACTION, CONFIG
- **PR Type Detection** (7 tests) - Single-type and MIXED detection
- **DOCS-Only Handling** (7 tests) - Exemption verification across all gates
- **Expected Patterns** (12 tests) - False positive prevention
- **CRITICAL_FAIL Triggers** (9 tests) - Context-aware thresholds
- **Cross-Prompt Consistency** (6 tests) - Consistent terminology and format

### Running Tests

```powershell
# Run full suite
Invoke-Pester tests/QualityGatePrompts.Tests.ps1

# Run with detailed output
Invoke-Pester tests/QualityGatePrompts.Tests.ps1 -Output Detailed
```

## Success Metrics

| Metric | Before | After |
|--------|--------|-------|
| DOCS-only false CRITICAL_FAIL | Common | Eliminated |
| Expected patterns false positives | Frequent | Eliminated |
| Test coverage | None | 84 tests |
| Regression detection | Manual | Automated |

## References

- [Issue #357](https://github.com/rjmurillo/ai-agents/issues/357) - Original bug report
- [RCA](/.agents/analysis/003-quality-gate-comment-caching-rca.md) - Root cause analysis
- [ADR-021](/.agents/architecture/ADR-023-quality-gate-prompt-testing.md) - Test suite decision record
- [Prompt Engineering Reference](/.claude/skills/prompt-engineer/references/prompt-engineering-single-turn.md) - Pattern source
