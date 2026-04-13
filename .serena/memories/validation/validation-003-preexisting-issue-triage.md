# Validation: Preexisting Issue Triage

## Skill-Validation-003: Pre-Existing Issue Triage

**Statement**: When introducing new validation, establish baseline and triage pre-existing violations separately from new work

**Context**: Adding new validators to existing codebases

**Evidence**: Validation script found 14 pre-existing issues requiring separate triage to avoid scope creep

**Atomicity**: 92%

**Tag**: helpful

**Impact**: 9/10

**Implementation**:

1. Run validator and capture baseline count
2. Create exception list or snapshot for existing violations
3. New code must pass validation (zero tolerance)
4. Schedule separate remediation for pre-existing issues
5. Gradual rollout: warn → error over time

---

## Related

- [validation-001-validation-script-false-positives](validation-001-validation-script-false-positives.md)
- [validation-002-pedagogical-error-messages](validation-002-pedagogical-error-messages.md)
- [validation-004-test-before-retrospective](validation-004-test-before-retrospective.md)
- [validation-005-pr-feedback-gate](validation-005-pr-feedback-gate.md)
- [validation-006-self-report-verification](validation-006-self-report-verification.md)
