# Security: Secure Error Handling 90

## Skill-Security-003: Secure Error Handling (90%)

**Statement**: Never expose stack traces or internal details in errors

**Context**: Error handling in any user-facing code

**Evidence**: Security best practices document

**Atomicity**: 90%

**Tag**: helpful

**Impact**: 8/10

**Pattern**:

- Generic messages to external users
- Detailed logs internal only
- Correlation IDs for debugging

**Source**: `.agents/security/security-best-practices.md`

---

## Related

- [security-001-twophase-security-review](security-001-twophase-security-review.md)
- [security-002-input-validation-first-88](security-002-input-validation-first-88.md)
- [security-002-input-validation-first](security-002-input-validation-first.md)
- [security-003-secure-error-handling](security-003-secure-error-handling.md)
- [security-004-security-event-logging-85](security-004-security-event-logging-85.md)
