---
name: Security Practices
applyTo: "**/Auth/**,*.env*,**/*.secrets.*,.github/workflows/**,.githooks/**"
priority: 10
version: 0.1.0
status: placeholder
---

# Security Practices Steering

**Status**: Placeholder for Phase 4 implementation

## Scope

**Applies to**: 
- `**/Auth/**` - Authentication/authorization code
- `*.env*` - Environment configuration
- `**/*.secrets.*` - Secret management
- `.github/workflows/**` - GitHub Actions workflows (secret exposure, code injection)
- `.githooks/**` - Git hooks (pre-commit secret scanning)

## Purpose

This steering file will provide security guidance for security-sensitive code.

## Planned Content (Phase 4)

### Guidelines
- OWASP Top 10 prevention
- Authentication best practices
- Authorization patterns
- Secrets management
- Input validation
- Output encoding

### Patterns
- PKCE for OAuth2
- JWT validation
- Password hashing (bcrypt)
- Rate limiting
- CSRF protection

### Anti-Patterns
- Hardcoded secrets
- Weak password policies
- Missing input validation
- Timing attacks
- SQL injection vulnerabilities

### Examples
- Secure authentication flows
- Token management
- Secret rotation

---

*This is a placeholder file. Content will be added in Phase 4: Steering Scoping*
