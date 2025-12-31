---
name: Security Practices
applyTo: "**/Auth/**,*.env*,**/*.secrets.*,.github/workflows/**,.githooks/**"
priority: 10
version: 1.0.0
status: active
---

# Security Practices Steering

This steering file provides security guidance for security-sensitive code in the ai-agents repository.

## Scope

**Applies to**:

- `**/Auth/**` - Authentication/authorization code
- `*.env*` - Environment configuration
- `**/*.secrets.*` - Secret management
- `.github/workflows/**` - GitHub Actions workflows
- `.githooks/**` - Git hooks

## Guidelines

### GitHub Actions Security

#### Token Permission Minimization

Always use minimal required permissions in workflows:

```yaml
permissions:
  contents: read
  pull-requests: write  # Only if needed for PR comments
```

Avoid `permissions: write-all` unless absolutely necessary.

#### Avoiding Code Injection

Never use untrusted input directly in `run:` blocks:

```yaml
# WRONG - Vulnerable to injection
run: echo "${{ github.event.comment.body }}"

# RIGHT - Use environment variable
env:
  COMMENT_BODY: ${{ github.event.comment.body }}
run: echo "$COMMENT_BODY"
```

#### Avoiding `pull_request_target` Risks

Do NOT checkout untrusted code in `pull_request_target` workflows:

```yaml
# DANGEROUS - Runs untrusted code with write permissions
on: pull_request_target
steps:
  - uses: actions/checkout@v4
    with:
      ref: ${{ github.event.pull_request.head.sha }}  # UNSAFE
```

Use `pull_request` event for untrusted code, `pull_request_target` only for trusted operations.

### Secret Scanning

#### Pre-commit Detection Patterns

Use regex patterns to detect hardcoded secrets:

| Secret Type | Pattern |
|-------------|---------|
| AWS Access Key | `AKIA[0-9A-Z]{16}` |
| GitHub PAT | `ghp_[A-Za-z0-9]{36}` |
| GitHub OAuth | `gho_[A-Za-z0-9]{36}` |
| GitHub App | `ghs_[A-Za-z0-9]{36}` |
| Private Key | `-----BEGIN (RSA\|OPENSSH\|EC) PRIVATE KEY-----` |
| Connection String | `(password\|pwd)=[^;]+` |
| JWT | `eyJ[A-Za-z0-9-_]+\.eyJ[A-Za-z0-9-_]+\.[A-Za-z0-9-_.+/=]*` |

#### Pre-commit Hook Pattern

```bash
# .githooks/pre-commit
SECRETS_PATTERN='(AKIA[0-9A-Z]{16}|ghp_[A-Za-z0-9]{36}|-----BEGIN.*PRIVATE KEY-----)'

if git diff --cached | grep -E "$SECRETS_PATTERN"; then
    echo "ERROR: Potential secret detected in staged changes"
    exit 1
fi
```

### AI Output Validation

When parsing AI-generated output (labels, milestones, strings), use hardened regex:

```powershell
# Hardened pattern - blocks metacharacters and trailing special chars
$validPattern = '^(?=.{1,50}$)[A-Za-z0-9](?:[A-Za-z0-9 _\.-]*[A-Za-z0-9])?$'

# Use in parsing
$labels = $aiOutput | Where-Object { $_ -match $validPattern }
```

**Blocked characters**: `;`, `|`, `` ` ``, `$`, `(`, `)`, `&`, `<`, `>`, newlines

**Never use**:

- `xargs` for AI output
- Unquoted variables with AI content
- Shell interpolation of AI strings

### Error Handling

Never expose internal details in error messages:

```powershell
# WRONG - Exposes internal details
catch {
    Write-Error "Error: $_"  # May contain stack trace, paths
}

# RIGHT - Generic message with correlation
catch {
    $correlationId = [guid]::NewGuid().ToString().Substring(0, 8)
    Write-Warning "Error occurred. Reference: $correlationId"
    Write-Debug "[$correlationId] $_"  # Detailed log for debugging
}
```

### Security Event Logging

Log security events with context but without sensitive data:

```powershell
# WRONG - Logs sensitive data
Write-Host "Authentication attempt: User=$user Token=$token"

# RIGHT - Logs only what's needed
Write-Host "Authentication $result for $user from $clientIP"
```

**Events to log**:

- Authentication attempts (success/failure)
- Authorization decisions
- Configuration changes
- Secret access patterns

## Patterns

### Input Validation First

Validate all inputs at system boundaries:

```powershell
param(
    [Parameter(Mandatory)]
    [ValidatePattern('^[a-zA-Z0-9_-]+$')]
    [string]$Username,

    [Parameter(Mandatory)]
    [ValidateRange(1, 99999)]
    [int]$IssueNumber
)
```

### Secure Credential Handling

Never store credentials in plain text:

```powershell
# Use environment variables for secrets
$token = $env:GITHUB_TOKEN
if (-not $token) {
    throw "GITHUB_TOKEN environment variable not set"
}
```

### Defense in Depth

Apply multiple security layers:

1. Input validation at boundaries
2. Output encoding before display
3. Least privilege for all operations
4. Audit logging for sensitive actions

## Anti-Patterns

### Hardcoded Secrets

```powershell
# NEVER DO THIS
$apiKey = "sk-abc123..."  # Hardcoded secret
gh auth login --with-token "ghp_..."  # Inline token
```

### Missing Input Validation

```powershell
# WRONG - No validation
$pr = gh pr view $input --json title

# RIGHT - Validate first
if ($input -notmatch '^\d+$') {
    throw "Invalid PR number format"
}
$pr = gh pr view $input --json title
```

### Trusting AI Output

```powershell
# WRONG - Direct execution of AI output
$aiOutput = Get-AIRecommendation
Invoke-Expression $aiOutput  # DANGEROUS

# RIGHT - Validate against allowlist
$allowedCommands = @('git status', 'npm test', 'pwsh Invoke-Pester')
if ($aiOutput -in $allowedCommands) {
    & $aiOutput
}
```

### Insufficient Error Handling

```powershell
# WRONG - Catch-all that swallows errors
try { Do-Something } catch { }

# RIGHT - Log and handle appropriately
try {
    Do-Something
} catch {
    Write-Warning "Operation failed: $($_.Exception.Message)"
    exit 1
}
```

## References

- Memory: `security-secret-detection`
- Memory: `powershell-security-ai-output`
- Memory: `security-003-secure-error-handling`
- Memory: `security-004-security-event-logging`
- [OWASP Top 10](https://owasp.org/www-project-top-ten/)
- [GitHub Actions Security Hardening](https://docs.github.com/en/actions/security-guides/security-hardening-for-github-actions)
