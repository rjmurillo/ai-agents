# Skill-Security-002: Input Validation First

**Statement**: Always validate and sanitize inputs before processing.

**Context**: Any code handling external data

**Atomicity**: 88%

**Strategy**:

- Parameterized queries for database access
- Allowlists over denylists for input validation
- Type checking before processing

**Source**: `.agents/security/security-best-practices.md`

## Related

- [security-003-secure-error-handling](security-003-secure-error-handling.md)
- [security-004-security-event-logging](security-004-security-event-logging.md)
- [security-007-defense-in-depth-for-cross-process-security-checks](security-007-defense-in-depth-for-cross-process-security-checks.md)
- [security-008-first-run-gap-analysis](security-008-first-run-gap-analysis.md)
- [security-009-domain-adjusted-signal-quality](security-009-domain-adjusted-signal-quality.md)
