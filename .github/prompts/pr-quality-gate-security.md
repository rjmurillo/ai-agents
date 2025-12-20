# Security Review Task

You are reviewing a pull request for security vulnerabilities and risks.

## Analysis Focus Areas

### 1. Vulnerability Scanning (OWASP Top 10)

- **Injection** (CWE-78, CWE-79, CWE-89): Check for shell injection, XSS, SQL injection
- **Broken Authentication**: Weak session handling, credential exposure
- **Sensitive Data Exposure**: Hardcoded secrets, API keys, tokens
- **Security Misconfiguration**: Insecure defaults, missing security headers
- **Insecure Deserialization**: Unsafe object parsing

### 2. Secret Detection

Look for patterns indicating exposed secrets:

- API keys: `[A-Za-z0-9_-]{20,}`
- AWS credentials: `AKIA[A-Z0-9]{16}`
- GitHub tokens: `gh[pousr]_[A-Za-z0-9_]{36}`
- Generic passwords: `password\s*=\s*['"][^'"]+['"]`
- Environment leaks: `.env` file exposure

### 3. Dependency Security

- New dependencies added without security review
- Known vulnerable packages
- Outdated security-critical libraries

### 4. Infrastructure Security

For changes to:

- `.github/workflows/*`: Check for injection via untrusted inputs
- `*.sh`, `*.ps1`: Validate input sanitization
- Configuration files: Check for overly permissive settings

## Output Requirements

Provide your analysis in this format:

### Findings

| Severity | Category | Finding | Location | CWE |
|----------|----------|---------|----------|-----|
| Critical/High/Medium/Low | [category] | [description] | [file:line] | [CWE-XXX] |

### Recommendations

1. [Specific remediation for each finding]

### Verdict

Choose ONE verdict:

- `VERDICT: PASS` - No security issues found
- `VERDICT: WARN` - Minor issues that don't block merge
- `VERDICT: CRITICAL_FAIL` - Security vulnerabilities that MUST be fixed

```text
VERDICT: [PASS|WARN|CRITICAL_FAIL]
MESSAGE: [Brief explanation]
```

## Critical Failure Triggers

Automatically use `CRITICAL_FAIL` if you find:

- Hardcoded credentials or API keys
- Shell injection vulnerabilities (CWE-78)
- SQL injection vulnerabilities (CWE-89)
- Path traversal vulnerabilities (CWE-22)
- Insecure deserialization
- Authentication bypass
