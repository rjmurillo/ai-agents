# Skill-Skepticism-001: Zero Bugs Is A Red Flag

**Statement**: "Zero bugs" in new infrastructure code should trigger verification, not celebration.

**Context**: Claiming implementation success with no failures

**Trigger**: Any claim of "zero bugs", "100% success", "A+ grade" before validation

**Atomicity**: 90%

**Tag**: CRITICAL

## Evidence

- Session 03: 2,189 LOC "zero bugs" code required 24+ fix commits
- Ratio: 1 implementation commit : 24+ fix commits = 96% of work fixing mistakes
- Root cause: Hubris - believed own hype before evidence

## Verification Checklist for "Zero Bugs" Claims

- [ ] Has code been executed in production/CI environment?
- [ ] Have automated security scans completed?
- [ ] Have peer reviews been conducted?
- [ ] Are there any open PR review comments?
- [ ] Are there any code scanning alerts?
- [ ] Has integration testing completed?

## Red Flag Phrases

- "Zero implementation bugs"
- "100% success rate"
- "A+ (Exceptional)"
- "Plan executed exactly as designed"
- "Zero pivots during implementation"

## Related

- [validation-006-self-report-verification](validation-006-self-report-verification.md)
- [validation-007-cross-reference-verification](validation-007-cross-reference-verification.md)
- [validation-007-frontmatter-validation-compliance](validation-007-frontmatter-validation-compliance.md)
- [validation-474-adr-numbering-qa-final](validation-474-adr-numbering-qa-final.md)
- [validation-anti-patterns](validation-anti-patterns.md)
