# Security Best Practices Enforcement Guide

<!-- doc-accuracy: external-sdk dotnet -- C# examples use the .NET base class library, ASP.NET Core Identity, BCrypt.Net, and Microsoft.Data.SqlClient, not this repository -->

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
using System;
using System.ComponentModel.DataAnnotations;
using System.Linq;
using System.Text.RegularExpressions;

static void ValidateRegistration(RegistrationInput input)
{
    // Check allowed values here. Authorize privileged role assignments separately.
    var allowedRoles = new[] { "user", "admin", "moderator" };
    if (!allowedRoles.Contains(input.Role, StringComparer.Ordinal))
        throw new ValidationException("Invalid role");

    // This pattern describes the application's accepted subset of addresses.
    const string emailPattern = @"\A[a-zA-Z0-9._%+-]{1,64}@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}\z";
    if (input.Email.Length > 254 ||
        !Regex.IsMatch(input.Email, emailPattern, RegexOptions.NonBacktracking))
        throw new ValidationException("Invalid email");
}

record RegistrationInput(string Role, string Email);
```

#### Don't: Denylist Validation

```csharp
using System.ComponentModel.DataAnnotations;
using System.Linq;

static void ValidateByDenylist(string input)
{
    // BAD: A list of literal characters misses encoded forms such as %3C and &#60;.
    var blockedChars = new[] { '<', '>', '&', '"', '\'' };
    if (input.Any(c => blockedChars.Contains(c)))
        throw new ValidationException("Invalid characters");
}
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
using System;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.AspNetCore.Http;
using Microsoft.Extensions.Logging;

static async Task<IResult> AuthenticateAsync(
    string userId,
    Func<CancellationToken, Task<bool>> verifyCredentials,
    ILogger logger,
    CancellationToken cancellationToken)
{
    if (await verifyCredentials(cancellationToken))
        return Results.NoContent();

    logger.LogWarning("Authentication failed for user {UserId}", userId);
    return Results.Unauthorized();
}
```

#### Don't: Verbose Error Responses

```csharp
using System;
using Microsoft.AspNetCore.Http;
using Microsoft.Data.SqlClient;

static IResult FindUser(Func<User?> queryUser)
{
    try
    {
        var user = queryUser();
        // BAD: Reveals whether the supplied account exists.
        return user is null ? Results.NotFound("User john@example.com not found") : Results.Ok(user);
    }
    catch (SqlException ex)
    {
        // BAD: Exposes system details.
        return Results.BadRequest($"Database error: {ex.Message} - Stack: {ex.StackTrace}");
    }
}

record User(string Id);
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
using System;
using Microsoft.Extensions.Logging;

static void LogResourceAccess(ILogger logger, string userId, string resourceId) =>
    logger.LogInformation(
        "User {UserId} accessed resource {ResourceId} at {Timestamp}",
        userId, resourceId, DateTimeOffset.UtcNow);

// The payment provider gives this code only the masked suffix.
static void LogPayment(ILogger logger, MaskedCard card) =>
    logger.LogDebug("Processing payment for card ending in {CardLast4}", card.Last4);

record MaskedCard(string Last4);
```

#### Don't: Dangerous Logging

```csharp
using System.Text.Json;
using Microsoft.Extensions.Logging;

static void LogSecrets(ILogger logger, string username, string password, object request, string jwtToken)
{
    // BAD: Logging password
    logger.LogDebug($"Login attempt: {username}/{password}");

    // BAD: Logging full request
    logger.LogDebug($"Request body: {JsonSerializer.Serialize(request)}");

    // BAD: Logging token
    logger.LogInformation($"Generated token: {jwtToken}");
}
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

The password example requires the `BCrypt.Net-Next` NuGet package.
Store the nonce and authentication tag alongside the ciphertext.

```csharp
using System;
using System.Security.Cryptography;
using PasswordHasher = BCrypt.Net.BCrypt;

static string HashPassword(string password) => PasswordHasher.HashPassword(password, workFactor: 12);

static bool VerifyPassword(string password, string storedHash) => PasswordHasher.Verify(password, storedHash);

static (byte[] Nonce, byte[] Ciphertext, byte[] Tag) Encrypt(ReadOnlySpan<byte> key, ReadOnlySpan<byte> plaintext)
{
    if (key.Length != 32)
        throw new ArgumentException("AES-256 requires a 32-byte key.", nameof(key));

    var nonce = RandomNumberGenerator.GetBytes(AesGcm.NonceByteSizes.MaxSize);
    var ciphertext = new byte[plaintext.Length];
    var tag = new byte[AesGcm.TagByteSizes.MaxSize];
    using var aesGcm = new AesGcm(key, tag.Length);
    aesGcm.Encrypt(nonce, plaintext, ciphertext, tag);
    return (nonce, ciphertext, tag);
}
```

#### Don't: Roll Your Own Crypto

```csharp
using System;
using System.Security.Cryptography;
using System.Text;

// BAD: Reusing the same XOR key exposes relationships between plaintexts.
static byte[] XorWithKey(ReadOnlySpan<byte> data, byte key)
{
    var encrypted = new byte[data.Length];
    for (int i = 0; i < data.Length; i++)
        encrypted[i] = (byte)(data[i] ^ key);
    return encrypted;
}

// BAD: Weak hashing for passwords.
static byte[] WeakPasswordHash(string password) => MD5.HashData(Encoding.UTF8.GetBytes(password));

// BAD: Every encryption would reuse the same IV.
static byte[] FixedIv() => new byte[] { 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16 };
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

The [Security Testing Reference](./security-testing.md) contains the coverage targets,
required security test examples, and checklist.

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
