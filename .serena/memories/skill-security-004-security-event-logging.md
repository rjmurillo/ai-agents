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
