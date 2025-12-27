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
