# Security Best Practices Enforcement Guide

## Purpose

This guide defines security best practices that should be enforced during code review and development. It covers input validation, error handling, logging, cryptography, and testing requirements.

---

## 1. Input Validation

### Validation Strategy

| Layer | Responsibility | Action |
|-------|----------------|--------|
| Client | UX feedback | Validate format, provide hints |
| API Gateway | Rate limiting | Block excessive requests |
| Application | Business rules | Validate all inputs server-side |
| Database | Constraints | Enforce data integrity |

### Validation Patterns

#### Do: Allowlist Validation

```csharp
// GOOD: Explicit allowlist
var allowedRoles = new[] { "user", "admin", "moderator" };
if (!allowedRoles.Contains(input.Role))
    throw new ValidationException("Invalid role");

// GOOD: Regex with bounded pattern
var emailPattern = @"^[a-zA-Z0-9._%+-]{1,64}@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$";
if (!Regex.IsMatch(input.Email, emailPattern))
    throw new ValidationException("Invalid email");
```

#### Don't: Denylist Validation

```csharp
// BAD: Denylist (can be bypassed)
var blockedChars = new[] { '<', '>', '&', '"', '\'' };
if (input.Any(c => blockedChars.Contains(c)))
    throw new ValidationException("Invalid characters");
// Attacker can use: %3C (URL-encoded <), &#60; (HTML entity), etc.
```

### Input Validation Checklist

```markdown
- [ ] All inputs validated server-side
- [ ] Validation before any processing
- [ ] Allowlist approach used
- [ ] Length limits enforced
- [ ] Type validation (number vs string)
- [ ] Range validation (min/max)
- [ ] Format validation (regex with bounds)
- [ ] Encoding validated (UTF-8)
```

---

## 2. Error Handling

### Error Handling Strategy

| Error Type | Log Level | User Response | Include Details |
|------------|-----------|---------------|-----------------|
| Validation | Debug | Specific message | Yes (field names) |
| Authentication | Warn | Generic message | No |
| Authorization | Warn | Generic message | No |
| Business logic | Info | Specific message | Limited |
| System/infrastructure | Error | Generic message | No |
| Unexpected | Error | Generic message | No |

### Secure Error Patterns

#### Do: Safe Error Responses

```csharp
// GOOD: Generic message, detailed logging
try
{
    await AuthenticateUser(credentials);
}
catch (Exception ex)
{
    _logger.LogWarning(ex, "Authentication failed for user {UserId}", credentials.UserId);
    return Unauthorized("Authentication failed");  // Generic
}
```

#### Don't: Verbose Error Responses

```csharp
// BAD: Exposes system details
catch (SqlException ex)
{
    return BadRequest($"Database error: {ex.Message} - Stack: {ex.StackTrace}");
}

// BAD: Reveals user existence
if (user == null)
    return NotFound("User john@example.com not found");  // Information leak
```

### Error Handling Checklist

```markdown
- [ ] No stack traces in production responses
- [ ] No internal paths in responses
- [ ] No database error details in responses
- [ ] No version information in responses
- [ ] Authentication errors are generic
- [ ] All errors logged with correlation ID
- [ ] Sensitive data not logged
```

---

## 3. Logging

### Logging Strategy

| What to Log | What NOT to Log |
|-------------|-----------------|
| Authentication attempts | Passwords/credentials |
| Authorization decisions | Full credit card numbers |
| Security-relevant events | Social Security Numbers |
| Error events (sanitized) | API keys/tokens |
| Admin actions | Session tokens |
| Data access patterns | Encryption keys |

### Secure Logging Patterns

#### Do: Structured, Safe Logging

```csharp
// GOOD: Structured logging without sensitive data
_logger.LogInformation(
    "User {UserId} accessed resource {ResourceId} at {Timestamp}",
    userId, resourceId, DateTime.UtcNow);

// GOOD: Masked sensitive data
_logger.LogDebug("Processing payment for card ending in {CardLast4}", card.Last4);
```

#### Don't: Dangerous Logging

```csharp
// BAD: Logging password
_logger.LogDebug($"Login attempt: {username}/{password}");

// BAD: Logging full request
_logger.LogDebug($"Request body: {JsonSerializer.Serialize(request)}");

// BAD: Logging token
_logger.LogInfo($"Generated token: {jwtToken}");
```

### Logging Checklist

```markdown
- [ ] Structured logging used
- [ ] No sensitive data in logs
- [ ] Correlation IDs for tracing
- [ ] Log levels appropriate
- [ ] Security events tagged
- [ ] Logs protected from tampering
- [ ] Log retention policy defined
```

---

## 4. Cryptography

### Cryptography Guidelines

| Use Case | Recommended | Avoid |
|----------|-------------|-------|
| Password hashing | bcrypt, Argon2 | MD5, SHA1, plain SHA256 |
| Encryption at rest | AES-256-GCM | DES, 3DES, RC4 |
| TLS | TLS 1.3, TLS 1.2 | SSL, TLS 1.0, TLS 1.1 |
| Hashing (non-password) | SHA-256, SHA-3 | MD5, SHA1 |
| Digital signatures | Ed25519, ECDSA | RSA-1024 |
| Key derivation | PBKDF2, Argon2 | Simple hashing |

### Secure Cryptography Patterns

#### Do: Use Standard Libraries

```csharp
// GOOD: Using built-in secure password hashing
using BCrypt.Net;
var hash = BCrypt.HashPassword(password, BCrypt.GenerateSalt(12));
var valid = BCrypt.Verify(password, storedHash);

// GOOD: Using AES-GCM for encryption
using var aesGcm = new AesGcm(key);
aesGcm.Encrypt(nonce, plaintext, ciphertext, tag);
```

#### Don't: Roll Your Own Crypto

```csharp
// BAD: Custom encryption
var encrypted = XorWithKey(data, secretKey);

// BAD: Weak hashing for passwords
var hash = MD5.Create().ComputeHash(Encoding.UTF8.GetBytes(password));

// BAD: Hardcoded IV
var iv = new byte[] { 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16 };
```

### Cryptography Checklist

```markdown
- [ ] No custom cryptographic algorithms
- [ ] Strong password hashing (bcrypt/Argon2)
- [ ] AES-256 for symmetric encryption
- [ ] TLS 1.2+ for transport
- [ ] Random IVs/nonces (never reused)
- [ ] Keys in secure storage
- [ ] Key rotation process defined
- [ ] No hardcoded keys in code
```

---

## 5. Testing Requirements

### Security Testing Coverage

| Code Area | Coverage Target | Test Types |
|-----------|-----------------|------------|
| Authentication | 95% | Unit + Integration |
| Authorization | 95% | Unit + Integration |
| Input validation | 90% | Unit + Fuzzing |
| Cryptography | 95% | Unit |
| Error handling | 85% | Unit + Integration |
| Security middleware | 90% | Integration |

### Required Security Tests

#### Authentication Tests

```csharp
[Fact]
public void Login_ValidCredentials_ReturnsToken() { ... }

[Fact]
public void Login_InvalidPassword_ReturnsUnauthorized() { ... }

[Fact]
public void Login_NonexistentUser_ReturnsUnauthorized() { ... }

[Fact]
public void Login_LockedAccount_ReturnsLocked() { ... }

[Fact]
public void Login_BruteForce_RateLimits() { ... }
```

#### Authorization Tests

```csharp
[Fact]
public void GetResource_OwnerAccess_ReturnsOk() { ... }

[Fact]
public void GetResource_OtherUserAccess_ReturnsForbidden() { ... }

[Fact]
public void AdminEndpoint_NonAdmin_ReturnsForbidden() { ... }

[Fact]
public void AdminEndpoint_Admin_ReturnsOk() { ... }
```

#### Input Validation Tests

```csharp
[Theory]
[InlineData("<script>alert('xss')</script>")]
[InlineData("'; DROP TABLE users; --")]
[InlineData("../../../etc/passwd")]
public void Endpoint_MaliciousInput_Sanitized(string input) { ... }
```

### Security Testing Checklist

```markdown
- [ ] All auth paths have positive/negative tests
- [ ] Authorization tested for each role
- [ ] Input validation has boundary tests
- [ ] Error responses tested for information leak
- [ ] Crypto functions have correctness tests
- [ ] Rate limiting tested
- [ ] Session handling tested
```

---

## 6. Quick Reference

### Security Code Review Questions

1. **Input**: Is all user input validated before use?
2. **Output**: Is output properly encoded for context?
3. **Auth**: Are all endpoints properly authenticated?
4. **Authz**: Are resources protected by authorization?
5. **Crypto**: Are secure algorithms and practices used?
6. **Errors**: Are error messages safe and logged?
7. **Secrets**: Are secrets properly managed?
8. **Tests**: Are security paths covered?

### Red Flags to Watch

| Pattern | Risk | Action |
|---------|------|--------|
| `eval()` or similar | Code injection | Remove or sandbox |
| `innerHTML =` | XSS | Use textContent or sanitize |
| String concatenation in SQL | SQL injection | Use parameters |
| `catch (Exception)` with rethrow | Stack trace leak | Handle or wrap |
| `password = "..."` | Hardcoded credential | Use secret manager |
| `MD5` or `SHA1` for passwords | Weak hashing | Use bcrypt/Argon2 |
| Missing `[Authorize]` | Missing auth | Add authorization |

---

## Related Documents

- [Static Analysis Checklist](./static-analysis-checklist.md)
- [Secret Detection Patterns](./secret-detection-patterns.md)
- [Code Quality Security Guide](./code-quality-security.md)
- [Architecture Security Template](./architecture-security-template.md)

---

*Document Version: 1.0*
*Created: 2025-12-13*
*GitHub Issue: #10*
