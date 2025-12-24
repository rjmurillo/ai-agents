# Security Secret Detection

## Skill-Security-005: Regex-Based Secret Detection (92%)

**Statement**: Use regex patterns to detect hardcoded secrets in code.

**Context**: Pre-commit hooks, PR gates, security scans

**Pattern Categories**:

| Secret Type | Regex Pattern |
|-------------|---------------|
| AWS Access Key | `AKIA[0-9A-Z]{16}` |
| AWS Secret Key | `[A-Za-z0-9/+=]{40}` (context required) |
| GitHub PAT | `ghp_[A-Za-z0-9]{36}` |
| GitHub OAuth | `gho_[A-Za-z0-9]{36}` |
| GitHub App | `ghs_[A-Za-z0-9]{36}` |
| Connection String | `(password\|pwd)=[^;]+` |
| API Key | `(api_key\|apikey)=[A-Za-z0-9]+` |
| Private Key | `-----BEGIN (RSA\|OPENSSH\|EC) PRIVATE KEY-----` |
| JWT | `eyJ[A-Za-z0-9-_]+\.eyJ[A-Za-z0-9-_]+\.[A-Za-z0-9-_.+/=]*` |

**Pre-commit Hook Pattern**:

```bash
# .githooks/pre-commit
SECRETS_PATTERN='(AKIA[0-9A-Z]{16}|ghp_[A-Za-z0-9]{36}|-----BEGIN.*PRIVATE KEY-----)'

if git diff --cached | grep -E "$SECRETS_PATTERN"; then
    echo "ERROR: Potential secret detected in staged changes"
    exit 1
fi
```

**False Positive Handling**:

- Use `.secretignore` for known safe patterns
- Require context (variable name + value pattern)
- Entropy-based detection for high-entropy strings

**Source**: `.agents/security/secret-detection-patterns.md`
