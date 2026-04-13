# Validation: Validation Script False Positives

## Skill-Validation-001: Validation Script False Positives

**Statement**: When creating validation scripts, distinguish between examples/anti-patterns and production code to prevent false positives

**Context**: Any validation script or automated checker

**Evidence**: 3/14 path violations were intentional anti-pattern examples in explainer.md

**Atomicity**: 88%

**Tag**: helpful

**Impact**: 8/10

**Mitigation Strategies**:

1. Skip code fence blocks during validation
2. Add `<!-- skip-validation -->` comment mechanism
3. Maintain allowlist for known pedagogical examples
4. Document false positives in validation output

---

## Related

- [validation-002-pedagogical-error-messages](validation-002-pedagogical-error-messages.md)
- [validation-003-preexisting-issue-triage](validation-003-preexisting-issue-triage.md)
- [validation-004-test-before-retrospective](validation-004-test-before-retrospective.md)
- [validation-005-pr-feedback-gate](validation-005-pr-feedback-gate.md)
- [validation-006-self-report-verification](validation-006-self-report-verification.md)
