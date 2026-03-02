# Utility: Security Pattern Library 88

## Skill-Utility-003: Security Pattern Library (88%)

**Statement**: Maintain regex patterns for common vulnerabilities in automated scans

**Context**: Automated security scans, PR gates, pre-commit hooks

**Evidence**: Security detection utility with pattern library

**Atomicity**: 88%

**Tag**: helpful

**Impact**: 8/10

**Location**: `.agents/utilities/security-detection/`

**Pattern Categories**:

- Hardcoded credentials (API keys, passwords, tokens)
- SQL injection vectors
- XSS vulnerability patterns
- Insecure deserialization
- Path traversal attempts

**Usage**:

```bash
# Run security pattern scan
pwsh .agents/utilities/security-detection/scan.ps1 -Path ./src
```

**Source**: `.agents/utilities/security-detection/SKILL.md`

---