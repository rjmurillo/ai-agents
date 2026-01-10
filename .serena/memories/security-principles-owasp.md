# Security Principles and OWASP

**Category**: Security
**Source**: `.agents/analysis/advanced-engineering-knowledge.md`

## Core Principles

| Principle | Summary |
|-----------|---------|
| OWASP Top 10 | Standard for most common web vulnerabilities |
| Least Privilege | Code/users have only needed access |
| Never Trust Input | Always validate and sanitize |
| Never Log Secrets | Exposing sensitive data is breach risk |
| Secure by Default | Default settings should be safe |
| AuthN vs AuthZ | AuthN proves identity; AuthZ grants permissions |

## OWASP Top 10 (2021)

1. Broken Access Control
2. Cryptographic Failures
3. Injection
4. Insecure Design
5. Security Misconfiguration
6. Vulnerable Components
7. Authentication Failures
8. Data Integrity Failures
9. Logging/Monitoring Failures
10. Server-Side Request Forgery

## Secure Development Practices

- Input validation: Whitelist, not blacklist
- Output encoding: Context-appropriate escaping
- Parameterized queries: Never concatenate SQL
- Secret management: Use vaults, not env vars in code
- Dependency scanning: Automated vulnerability detection
- Security testing: SAST, DAST, penetration testing

## Related

- `owasp-agentic-security-integration` - AI agent security
- `security-002-input-validation-first` - Validation patterns
- `cwe-699-security-agent-integration` - Vulnerability detection
