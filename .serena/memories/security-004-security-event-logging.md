# Skill-Security-004: Security Event Logging

**Statement**: Log security events with context but without sensitive data.

**Atomicity**: 85%

**Events to Log**:

- Authentication attempts (success/failure)
- Authorization decisions
- Data modifications
- Configuration changes

**Pattern**:

```csharp
// WRONG - logs password
_logger.LogInformation("Login attempt: {User} {Password}", user, password);

// RIGHT - logs only what's needed
_logger.LogInformation("Login {Result} for {User} from {IP}",
    success ? "success" : "failure", user, clientIp);
```

**Source**: `.agents/security/security-best-practices.md`

## Related

- [security-002-input-validation-first](security-002-input-validation-first.md)
- [security-003-secure-error-handling](security-003-secure-error-handling.md)
- [security-007-defense-in-depth-for-cross-process-security-checks](security-007-defense-in-depth-for-cross-process-security-checks.md)
- [security-008-first-run-gap-analysis](security-008-first-run-gap-analysis.md)
- [security-009-domain-adjusted-signal-quality](security-009-domain-adjusted-signal-quality.md)
