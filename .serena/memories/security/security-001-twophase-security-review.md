# Security: Twophase Security Review

## Skill-Security-001: Two-Phase Security Review

**Statement**: Security review requires TWO phases: pre-implementation (threat model, controls) and post-implementation (verification, actual code review)

**Context**: Any feature with security implications

**Evidence**: Issue #I7 - security script not re-reviewed after implementation; implementer is best positioned to flag security-relevant changes during coding

**Atomicity**: 94%

**Tag**: helpful

**Impact**: 10/10

**Pattern**:

```text
Phase 1 (Pre-Implementation):
  security agent → Threat model, required controls, security requirements
  
Phase 2 (Implementation):  
  implementer → Code + flag security-relevant changes for review
  
Phase 3 (Post-Implementation):
  security agent → Verify controls implemented, actual code review
```

**Anti-Pattern**:

- Single security review at planning time only
- Security not re-engaged after implementation
- No handoff from implementer back to security

---

---

## Related

- [security-002-input-validation-first-88](security-002-input-validation-first-88.md)
- [security-002-input-validation-first](security-002-input-validation-first.md)
- [security-003-secure-error-handling-90](security-003-secure-error-handling-90.md)
- [security-003-secure-error-handling](security-003-secure-error-handling.md)
- [security-004-security-event-logging-85](security-004-security-event-logging-85.md)
