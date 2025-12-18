applyTo: "**/Auth/**,*.env*,**/*.secrets.*"

# Security Best Practices

Apply OWASP security guidelines for authentication, authorization, and sensitive data handling.

## Key Requirements

- **Authentication**: Use industry-standard protocols (OAuth2, OIDC)
- **Authorization**: Implement role-based or claims-based access control
- **Secrets**: Never hardcode secrets, use secure configuration
- **Input validation**: Validate and sanitize all external input
- **Output encoding**: Encode output to prevent injection attacks
- **Cryptography**: Use platform crypto libraries, never roll your own

## Patterns

- **PKCE**: For OAuth2 authorization code flow
- **JWT validation**: Verify signature, issuer, audience, expiration
- **Password hashing**: Use bcrypt or Argon2, never plain SHA
- **Rate limiting**: Protect against brute force attacks
- **CSRF protection**: Implement anti-forgery tokens

## Anti-Patterns to Avoid

- ❌ Hardcoded credentials or API keys
- ❌ Weak password policies
- ❌ Missing input validation
- ❌ SQL injection vulnerabilities
- ❌ Timing attacks on authentication

## Threat Modeling

- Consider STRIDE for new features
- Document security controls
- Review authentication flows for vulnerabilities

*Note: Full steering content to be implemented in Phase 4. See `.agents/steering/security-practices.md` for placeholder.*
