# Skill-Init-003: Memory-First Monitoring Gate

**Statement**: Load relevant memories before status classification logic in monitoring tasks

**Context**: At start of monitoring session, before PR status classification. Required memories: ci-workflow-required-checks, skills-implementation-index, skills-ci-infrastructure-index. Applies to autonomous loops and manual monitoring tasks.

**Evidence**: 2025-12-24 PR monitoring session: Cycle 7 revealed 3-cycle waste (30% of session) due to BLOCKED status misclassification. PR #334 + 5 others incorrectly categorized as "awaiting review" when actual blocker was required check not running. If ci-workflow-required-checks memory loaded before classification logic, pattern would have been recognized immediately.

**Atomicity**: 90% | **Impact**: 10/10

## Pattern

BLOCKING gate at session start for monitoring tasks:

1. Identify task type: monitoring or status classification
2. Load domain memories BEFORE executing logic:
   - CI/workflow monitoring: [ci-workflow-required-checks](ci-workflow-required-checks.md), [skills-ci-infrastructure-index](skills-ci-infrastructure-index.md)
   - PR status classification: [skills-pr-review-index](skills-pr-review-index.md), [skills-pr-validation-gates](skills-pr-validation-gates.md)
   - General monitoring: [skill-monitoring-001-blocked-pr-root-cause](monitoring-001-blocked-pr-root-cause.md)
3. Review loaded context for patterns matching current scenario
4. Proceed with classification/monitoring using memory-informed logic

## Anti-Pattern

Reactive memory loading (load AFTER problem encountered):

```text
# WRONG: Reactive approach
1. Execute monitoring logic with assumptions
2. Encounter unexpected status (BLOCKED)
3. Make assumption (BLOCKED = awaiting review)
4. User feedback reveals error
5. THEN load memory to understand pattern
```

Result: 3+ cycles wasted, 30% session efficiency loss.

**Evidence**: Lines 226-242 of retrospective show assumption made without verification, requiring user intervention at Cycle 7.

## Related

- [session-109-export-analysis-findings](session-109-export-analysis-findings.md)
- [session-110-agent-upgrade](session-110-agent-upgrade.md)
- [session-111-investigation-allowlist](session-111-investigation-allowlist.md)
- [session-112-pr-712-review](session-112-pr-712-review.md)
- [session-113-pr-713-review](session-113-pr-713-review.md)
