# Security Secret Detection

## Skill-Security-005: Regex-Based Secret Detection (92%)

**Statement**: Use regex patterns to detect hardcoded secrets in code.

**Context**: Pre-commit hooks, PR gates, security scans

**Pattern Categories**:

Patterns are POSIX ERE, the dialect `grep -E` reads in the hook below. Copy
them verbatim. The `|` characters are alternation and must stay unescaped: in
ERE a `\|` matches a literal pipe character, so an escaped pattern silently
matches nothing and the scan reports clean while secrets pass.

```text
AWS Access Key     AKIA[0-9A-Z]{16}
AWS Secret Key     [A-Za-z0-9/+=]{40}
GitHub PAT         ghp_[A-Za-z0-9]{36}
GitHub OAuth       gho_[A-Za-z0-9]{36}
GitHub App         ghs_[A-Za-z0-9]{36}
Connection String  (password|pwd)=[^;]+
API Key            (api_key|apikey)=[A-Za-z0-9]+
Private Key        -----BEGIN (RSA|OPENSSH|EC) PRIVATE KEY-----
JWT                eyJ[A-Za-z0-9_-]+\.eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_.+/=-]*
```

The `\.` pairs in the JWT pattern are correct: they match the literal dots
separating the header, payload, and signature segments. Each `-` sits last in
its bracket expression, where it is a literal; placed mid-class it starts a
character range and `grep -E` rejects the pattern with `Invalid range end`.

The Private Key pattern begins with `-`, so pass it after `--` or with `-e`.
Otherwise `grep` reads it as a bundle of options.

AWS Secret Key has no distinctive prefix and matches any 40-character base64
run, so it needs surrounding context (an assignment to a credential-shaped
variable name) before it is worth alerting on.

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

That source file is a broader catalog written in a different dialect: its
patterns carry `(?i)` and `\s`, which are Python and PCRE constructs, not
POSIX ERE. Do not copy patterns between the two files without translating
them. Measured with GNU grep 3.11: every source-file pattern containing
`[a-zA-Z0-9-_]` aborts under `grep -E` with `Invalid range end`, because the
mid-class hyphen opens a character range there. Python's `re` parses the same
hyphen as a literal, so those patterns are correct for the source file's own
engine and wrong for this one.

## Related

- [security-002-input-validation-first](security-002-input-validation-first.md)
- [security-003-secure-error-handling](security-003-secure-error-handling.md)
- [security-004-security-event-logging](security-004-security-event-logging.md)
- [security-007-defense-in-depth-for-cross-process-security-checks](security-007-defense-in-depth-for-cross-process-security-checks.md)
- [security-008-first-run-gap-analysis](security-008-first-run-gap-analysis.md)
