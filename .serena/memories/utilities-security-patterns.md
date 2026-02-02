# Security Pattern Library

**Statement**: Maintain regex patterns for common vulnerabilities in automated scans

**Context**: Automated security scans, PR gates, pre-commit hooks

**Atomicity**: 88%

**Impact**: 8/10

**Location**: `.agents/utilities/security-detection/`

## Pattern Categories

- Hardcoded credentials (API keys, passwords, tokens)
- SQL injection vectors
- XSS vulnerability patterns
- Insecure deserialization
- Path traversal attempts

## Usage

```bash
pwsh .agents/utilities/security-detection/scan.ps1 -Path ./src
```

## Integration Points

- Pre-commit hook for local detection
- PR gate for automated review
- CI pipeline for comprehensive scan

## Related

- [utilities-cva-refactoring](utilities-cva-refactoring.md)
- [utilities-markdown-fences](utilities-markdown-fences.md)
- [utilities-pathinfo-conversion](utilities-pathinfo-conversion.md)
- [utilities-precommit-hook](utilities-precommit-hook.md)
- [utilities-regex](utilities-regex.md)
