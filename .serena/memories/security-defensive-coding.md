# Security Defensive Coding

## Skill-Security-002: Input Validation First (88%)

**Statement**: Always validate and sanitize inputs before processing.

**Context**: Any code handling external data

**Strategy**:

- Parameterized queries for database access
- Allowlists over denylists for input validation
- Type checking before processing

**Source**: `.agents/security/security-best-practices.md`

## Skill-Security-003: Secure Error Handling (90%)

**Statement**: Never expose stack traces or internal details in errors.

**Context**: Error handling in any user-facing code

**Pattern**:

- Generic messages to external users
- Detailed logs internal only
- Correlation IDs for debugging

```csharp
// WRONG
catch (Exception ex) { return ex.ToString(); }

// RIGHT
catch (Exception ex) {
    var correlationId = Guid.NewGuid();
    _logger.LogError(ex, "Error {CorrelationId}", correlationId);
    return $"Error occurred. Reference: {correlationId}";
}
```

## Skill-Security-004: Security Event Logging (85%)

**Statement**: Log security events with context but without sensitive data.

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
