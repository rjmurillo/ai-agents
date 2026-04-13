# Security: Regexbased Secret Detection 92

## Skill-Security-005: Regex-Based Secret Detection (92%)

**Statement**: Use regex patterns to detect hardcoded secrets in code

**Context**: Pre-commit hooks, PR gates, security scans

**Evidence**: Secret detection patterns document with regex library

**Atomicity**: 92%

**Tag**: helpful

**Impact**: 9/10

**Pattern Categories**:

- AWS keys: `AKIA[0-9A-Z]{16}`
- GitHub tokens: `gh[ps]_[A-Za-z0-9]{36}`
- Connection strings: `(password|pwd)=[^;]+`
- API keys: `(api_key|apikey)=[A-Za-z0-9]+`

**Source**: `.agents/security/secret-detection-patterns.md`

---

## Related

- [security-001-twophase-security-review](security-001-twophase-security-review.md)
- [security-002-input-validation-first-88](security-002-input-validation-first-88.md)
- [security-002-input-validation-first](security-002-input-validation-first.md)
- [security-003-secure-error-handling-90](security-003-secure-error-handling-90.md)
- [security-003-secure-error-handling](security-003-secure-error-handling.md)
