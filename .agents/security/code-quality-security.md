# Code Quality Security Guide

## Purpose

This guide identifies code quality issues that have security implications. Poor code quality increases attack surface, makes vulnerabilities harder to detect, and complicates security reviews.

## Complexity Thresholds

### File-Level Metrics

| Metric | Threshold | Security Impact |
|--------|-----------|-----------------|
| Lines of Code (LOC) | > 500 | Hard to review, vulnerabilities hide |
| Cyclomatic Complexity | > 20 | Difficult to test all paths |
| Dependencies | > 15 imports | Large attack surface |
| Functions per file | > 20 | Poor cohesion, mixed concerns |

### Function-Level Metrics

| Metric | Threshold | Security Impact |
|--------|-----------|-----------------|
| Lines of Code | > 50 | Hard to reason about |
| Parameters | > 5 | Input validation burden |
| Nesting Depth | > 4 | Complex control flow |
| Cyclomatic Complexity | > 10 | Untestable edge cases |

## Security-Critical Code Patterns

### 1. Large Files Handling Security

**Risk**: Files > 500 LOC in security-critical paths

**Detection**:

```text
# Security-critical directories to watch
**/Auth/**
**/Security/**
**/Controllers/**
**/Middleware/**
**/*Handler*
**/*Provider*
```

**Remediation**:

- Split into focused, single-responsibility modules
- Extract validation logic into dedicated validators
- Separate authentication from authorization
- Move crypto operations to utility classes

### 2. Complex Functions

**Risk**: Complex functions are harder to reason about and test.

**Detection Patterns**:

```text
# High nesting depth (> 4 levels)
if (a) {
    if (b) {
        if (c) {
            if (d) {  // Too deep
                ...
            }
        }
    }
}

# Long parameter lists (> 5)
void ProcessPayment(
    string userId, string cardNumber, string cvv,
    decimal amount, string currency, string description,
    bool saveCard, string billingAddress, ...
)
```

**Remediation**:

- Use early returns to reduce nesting
- Create parameter objects for related data
- Extract nested logic into named methods
- Use guard clauses

### 3. Tight Coupling

**Risk**: Coupled code spreads vulnerabilities and makes isolation difficult.

**Detection Patterns**:

```text
# Static dependencies on sensitive services
SecurityManager.GetCurrentUser()
AuthenticationService.Instance.Validate()

# Hardcoded dependencies
new UserRepository()
new CryptoProvider()
```

**Remediation**:

- Use dependency injection
- Program to interfaces
- Apply principle of least privilege
- Isolate security-critical code

## Environment Coupling

### Dangerous Patterns

| Pattern | Risk | Better Approach |
|---------|------|-----------------|
| Hardcoded URLs | Environment leak | Use configuration |
| Inline connection strings | Credential exposure | Use secrets manager |
| File path hardcoding | Path traversal risk | Use configuration |
| OS-specific code | Platform vulnerabilities | Use abstractions |

### Detection

```text
# Hardcoded environment values
http://localhost:
https://api.production.
C:\Users\
/home/user/
/var/www/

# Environment checks that skip security
if (Environment.IsDevelopment())
    // Skip auth
```

### Remediation

```csharp
// BAD: Hardcoded
var apiUrl = "https://api.production.example.com";

// GOOD: Configured
var apiUrl = configuration["ApiEndpoint"];

// BAD: Environment-based security bypass
if (env.IsDevelopment())
    app.UseAuthenticationBypass();

// GOOD: No security bypass, different config instead
app.UseAuthentication();  // Always enabled
```

## Testing Burden

### Security Code Must Be Testable

| Requirement | Why | How |
|-------------|-----|-----|
| Pure functions for crypto | Deterministic testing | Extract crypto logic |
| Injectable dependencies | Mockable security services | Dependency injection |
| Clear boundaries | Isolated security tests | Separate concerns |
| No hidden state | Predictable behavior | Explicit parameters |

### Testing Coverage Requirements

| Code Area | Minimum Coverage | Reason |
|-----------|------------------|--------|
| Authentication | 90% | Critical path |
| Authorization | 90% | Access control |
| Input validation | 85% | Attack prevention |
| Crypto operations | 95% | No tolerance for bugs |
| Error handling | 80% | Information disclosure |

## Module Boundary Violations

### Cross-Cutting Concerns to Watch

| Concern | Violation Pattern | Risk |
|---------|-------------------|------|
| Logging | Security code logging secrets | Data leak |
| Caching | Caching auth tokens incorrectly | Token theft |
| Configuration | Security config mixed with app | Exposure |
| Exception handling | Catching/rethrowing incorrectly | Stack exposure |

### Detection

```text
# Security code reaching into other modules
class AuthController {
    void Login() {
        // BAD: Reaching into logging internals
        LogManager.GetLogger().LogSensitive(password);

        // BAD: Direct cache access
        MemoryCache.Set("token:" + userId, token);
    }
}
```

### Proper Boundaries

```csharp
// GOOD: Security-aware abstractions
class AuthController {
    private readonly ISecurityLogger _logger;
    private readonly ISecureTokenCache _tokenCache;

    void Login() {
        _logger.LogAuthAttempt(userId);  // PII-safe
        _tokenCache.Store(userId, token);  // Encrypted
    }
}
```

## Security Review Checklist

### File-Level Review

```markdown
- [ ] LOC < 500 (or justified exception)
- [ ] Clear single responsibility
- [ ] No mixed concerns (auth + business logic)
- [ ] Appropriate test coverage
- [ ] Dependencies minimized
```

### Function-Level Review

```markdown
- [ ] LOC < 50 (or justified)
- [ ] Cyclomatic complexity < 10
- [ ] Nesting depth < 4
- [ ] Parameters < 5
- [ ] No security bypass in conditionals
```

### Coupling Review

```markdown
- [ ] Uses dependency injection
- [ ] No static singletons for security services
- [ ] No hardcoded environment values
- [ ] No OS-specific security code
- [ ] Boundaries respected
```

## Refactoring for Security

### When to Refactor

1. Before adding security-sensitive features
2. After security incident (prevent recurrence)
3. When complexity exceeds thresholds
4. During code review with security findings

### Safe Refactoring Steps

1. **Add tests first**: Ensure behavior is captured
2. **Extract method**: Move complex logic out
3. **Inject dependencies**: Remove static access
4. **Add boundaries**: Separate concerns
5. **Verify security**: Re-test after changes

## Related Documents

- [Static Analysis Checklist](./static-analysis-checklist.md)
- [Security Best Practices](./security-best-practices.md)
- [Architecture Security Template](./architecture-security-template.md)

---

*Document Version: 1.0*
*Created: 2025-12-13*
*GitHub Issue: #10*
