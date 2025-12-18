---
applyTo: "**/Auth/**,*.env*,**/*.secrets.*,.github/workflows/**,.githooks/**"
---

# Security Best Practices

For comprehensive security guidance, see [.agents/steering/security-practices.md](../../.agents/steering/security-practices.md) and the security agent at [src/claude/security.md](../../src/claude/security.md).

## Quick Reference

### OWASP Top 10 Focus Areas

- **Injection**: Validate and sanitize all input
- **Broken Authentication**: Use industry-standard protocols (OAuth2, OIDC)  
- **Sensitive Data Exposure**: Never hardcode secrets
- **XXE/XSS**: Encode output, validate XML
- **Broken Access Control**: Implement RBAC/claims-based authz
- **Security Misconfiguration**: Secure defaults, minimal exposure
- **Insecure Deserialization**: Validate serialized data
- **Using Components with Known Vulnerabilities**: Audit dependencies
- **Insufficient Logging**: Log security events
- **Server-Side Request Forgery (SSRF)**: Validate URLs

### Critical Patterns

**Authentication:**

- Use OAuth2 with PKCE for authorization code flow
- Validate JWT signatures, issuer, audience, expiration
- Never use plain SHA for passwords (use bcrypt or Argon2)
- Implement rate limiting against brute force

**Secrets Management:**

- Never hardcode credentials, API keys, tokens
- Use secure configuration (environment variables, key vaults)
- Rotate secrets regularly
- Audit .env files, never commit them

**Input Validation:**

- Validate all external input (APIs, forms, files)
- Use allowlists, not denylists
- Sanitize before processing
- Prevent SQL injection, command injection, path traversal

**Output Encoding:**

- Encode output to prevent XSS
- Use context-appropriate encoding (HTML, JavaScript, URL)

### File Path Triggers

Security review REQUIRED for changes to:

- `**/Auth/**` - Authentication/authorization code
- `.githooks/*` - Pre-commit hooks (can leak secrets)
- `*.env*` - Environment configuration
- `**/*.secrets.*` - Secret storage patterns

### Threat Modeling

Apply STRIDE for new features:

- **S**poofing: Authentication controls
- **T**ampering: Integrity controls
- **R**epudiation: Logging and auditing
- **I**nformation Disclosure: Encryption, access control
- **D**enial of Service: Rate limiting, resource limits
- **E**levation of Privilege**: Authorization, least privilege

*This file serves as a Copilot-specific entry point. The authoritative steering content is maintained in `.agents/steering/security-practices.md` and the security agent expertise in `src/claude/security.md`.*
