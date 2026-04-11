---
source: wiki/concepts/Design Principles/OWASP Top 10.md
created: 2026-04-11
review-by: 2026-07-11
---

# OWASP Top 10 (2021)

Industry-standard vulnerability categories for web application security. Use as a checklist during Phase 2 (Threat Identification) to ensure coverage.

## The 10 Categories

| # | Category | Description |
|---|----------|-------------|
| A01 | Broken Access Control | Users access functions/data beyond permissions |
| A02 | Cryptographic Failures | Poor encryption exposing sensitive data |
| A03 | Injection | Malicious data injected into commands/queries |
| A04 | Insecure Design | Missing security controls in design phase |
| A05 | Security Misconfiguration | Insecure defaults, unnecessary features enabled |
| A06 | Vulnerable Components | Using libraries with known vulnerabilities |
| A07 | Authentication Failures | Broken credential/session management |
| A08 | Integrity Failures | Insecure CI/CD, unsigned updates, unsafe deserialization |
| A09 | Logging Failures | Insufficient logging to detect breaches |
| A10 | SSRF | Server fetches URLs without validation |

## Quick Reference by Risk Area

| Area | Vulnerabilities | Primary Defense |
|------|----------------|-----------------|
| Authentication | A07 | MFA, strong sessions, rate limiting |
| Authorization | A01 | RBAC, deny by default, verify every request |
| Data Protection | A02 | Encryption at rest/transit, strong hashing |
| Input Handling | A03 | Parameterized queries, input validation |
| Dependencies | A06 | Regular updates, vulnerability scanning |
| Configuration | A05 | Secure defaults, remove unused features |
| Monitoring | A09 | Comprehensive logging, alerting |

## Critical Categories with Code Examples

### A01: Broken Access Control

```csharp
// Always verify ownership
public async Task<Order> GetOrder(int orderId, int userId)
{
    var order = await _db.Orders.FindAsync(orderId);
    if (order.UserId != userId)
        throw new UnauthorizedAccessException();
    return order;
}
```

Mitigations: Implement RBAC consistently. Deny by default. Verify permissions on every request.

### A02: Cryptographic Failures

Mitigations: Use AES-256 for encryption at rest. Enforce TLS 1.2+ for transport. Use bcrypt/Argon2 for password hashing. Implement key rotation. Never hardcode encryption keys.

### A03: Injection

```csharp
// Vulnerable
var sql = $"SELECT * FROM Users WHERE Id = {userId}";

// Safe: parameterized query
var user = await _db.Users
    .FromSqlRaw("SELECT * FROM Users WHERE Id = {0}", userId)
    .FirstOrDefaultAsync();

// Better: use ORM
var user = await _db.Users.FindAsync(userId);
```

Mitigations: Use parameterized queries/prepared statements. Validate and sanitize all inputs. Use allowlist validation.

## STRIDE to OWASP Mapping

Use this mapping during Phase 2 to cross-reference STRIDE findings with OWASP categories:

| STRIDE | OWASP Categories |
|--------|-----------------|
| Spoofing | A07 (Authentication Failures) |
| Tampering | A03 (Injection), A08 (Integrity Failures) |
| Repudiation | A09 (Logging Failures) |
| Info Disclosure | A01 (Broken Access Control), A02 (Cryptographic Failures) |
| Denial of Service | A05 (Security Misconfiguration) |
| Elevation of Privilege | A01 (Broken Access Control), A04 (Insecure Design) |

## Relationship to Security Testing

| Activity | OWASP Role |
|----------|------------|
| Threat Modeling | Use Top 10 as vulnerability checklist |
| SAST | Static analysis tools scan for Top 10 |
| DAST | Dynamic testing verifies resilience |
| Penetration Testing | Testers use Top 10 as attack guide |
| Compliance | GDPR, PCI-DSS reference OWASP |

## Related

- [Defense in Depth](security-defense-in-depth.md): Layered mitigations for each category
- [Zero Trust](security-zero-trust.md): Complements OWASP with trust verification
- [Least Privilege](security-least-privilege.md): A01 mitigation foundation
