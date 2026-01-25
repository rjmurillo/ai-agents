# Skill-Validation-004: Test Before Retrospective

**Statement**: Never write a retrospective until implementation has been:

1. Executed and validated in target environment (CI/CD)
2. All PR review comments addressed or acknowledged
3. All security scanning alerts remediated (high/critical = blocking)
4. No findings blocking merge

**Context**: Completing implementation of infrastructure/CI code; any multi-file change

**Trigger**: Declaring "implementation complete" or writing retrospective

**Atomicity**: 95%

**Tag**: CRITICAL

## Evidence

- Session 03: Claimed "zero bugs" and "A+ grade" for 2,189 LOC
- Reality: 6+ critical bugs, 24+ fix commits across 4 debugging sessions
- PR #60: 30 review comments, 4 high-severity code scanning alerts still open

## Checklist Before Retrospective

- [ ] Code executed in target environment (not just written)
- [ ] CI/CD pipeline passed
- [ ] All PR review comments triaged (addressed/acknowledged/deferred with reason)
- [ ] Security scanning completed (code-scanning, dependabot)
- [ ] No high/critical security findings blocking
- [ ] Peer review completed (if required)

## Related

- [validation-006-self-report-verification](validation-006-self-report-verification.md)
- [validation-007-cross-reference-verification](validation-007-cross-reference-verification.md)
- [validation-007-frontmatter-validation-compliance](validation-007-frontmatter-validation-compliance.md)
- [validation-474-adr-numbering-qa-final](validation-474-adr-numbering-qa-final.md)
- [validation-anti-patterns](validation-anti-patterns.md)
