# Skill-Security-003: Secure Error Handling

**Statement**: Never expose stack traces or internal details in errors.

**Context**: Error handling in any user-facing code

**Atomicity**: 90%

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

## Related

- [security-002-input-validation-first](security-002-input-validation-first.md)
- [security-004-security-event-logging](security-004-security-event-logging.md)
- [security-007-defense-in-depth-for-cross-process-security-checks](security-007-defense-in-depth-for-cross-process-security-checks.md)
- [security-008-first-run-gap-analysis](security-008-first-run-gap-analysis.md)
- [security-009-domain-adjusted-signal-quality](security-009-domain-adjusted-signal-quality.md)
