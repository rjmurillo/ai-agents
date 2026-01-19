# Validation: Test Before Retrospective

## Skill-Validation-004: Test Before Retrospective

**Statement**: Never write a retrospective until implementation has been:
1. Executed and validated in target environment (CI/CD)
2. All PR review comments addressed or acknowledged
3. All security scanning alerts remediated (high/critical = blocking)
4. No findings blocking merge

**Context**: Completing implementation of infrastructure/CI code; any multi-file change

**Trigger**: Declaring "implementation complete" or writing retrospective

**Evidence**: 
- Session 03 (2025-12-18): Claimed "zero bugs" and "A+ grade" for 2,189 LOC
- Reality: 6+ critical bugs, 24+ fix commits across 4 debugging sessions
- PR #60: 30 review comments (19 Copilot security, 9 Gemini high-priority, 2 GitHub Security)
- PR #60: 4 high-severity code scanning alerts (path injection CWE-22) still open

**Atomicity**: 95%

**Tag**: CRITICAL

**Impact**: 10/10 - Prevents false confidence and premature skill extraction

**Checklist Before Retrospective**:

- [ ] Code executed in target environment (not just written)
- [ ] CI/CD pipeline passed
- [ ] All PR review comments triaged (addressed/acknowledged/deferred with reason)
- [ ] Security scanning completed (code-scanning, dependabot)
- [ ] No high/critical security findings blocking
- [ ] Peer review completed (if required)

**Anti-Pattern**: Victory Lap Before Finish Line

---

## Related

- [validation-001-validation-script-false-positives](validation-001-validation-script-false-positives.md)
- [validation-002-pedagogical-error-messages](validation-002-pedagogical-error-messages.md)
- [validation-003-preexisting-issue-triage](validation-003-preexisting-issue-triage.md)
- [validation-005-pr-feedback-gate](validation-005-pr-feedback-gate.md)
- [validation-006-self-report-verification](validation-006-self-report-verification.md)
