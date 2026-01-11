# CWE-699 Security Agent Integration

## Purpose

Guidance for integrating CWE-699 Software Development weakness categories into the security agent prompt to address detection gaps identified in PR #752.

## Key CWE Categories for Security Agent

### Path Traversal Family (Priority 1)

Treat as unified detection category:

| CWE | Name | Detection Focus |
|-----|------|-----------------|
| CWE-22 | Path Traversal | Parent category, `..` and absolute paths |
| CWE-23 | Relative Path Traversal | `../` sequences in file paths |
| CWE-36 | Absolute Path Traversal | `/etc/passwd`, `C:\windows` patterns |
| CWE-73 | External Control of File Name | Root cause, user input in file operations |
| CWE-99 | Resource Injection | Broader class containing file attacks |

### Code Execution (Priority 2)

| CWE | Name | PowerShell Patterns |
|-----|------|---------------------|
| CWE-77 | Command Injection | Unquoted variables in external commands |
| CWE-78 | OS Command Injection | Shell metacharacters in parameters |
| CWE-94 | Code Injection | `Invoke-Expression`, `ExpandString()` |

### Additional Categories (Priority 3)

| CWE | Name | Detection Focus |
|-----|------|-----------------|
| CWE-1333 | ReDoS | Regex with nested quantifiers |
| CWE-367 | TOCTOU | Security check before file operation |
| CWE-295 | Certificate Validation | Legacy WebClient usage |

## PowerShell Detection Patterns

### Must Flag

1. `StartsWith()` without prior `GetFullPath()` normalization
2. `Join-Path` with unchecked user input (absolute path risk)
3. `-Path` parameters with unvalidated external input
4. `Invoke-Expression` or `iex` with any input
5. `ExpandString()` with config-derived values
6. Symlink check followed by gap before file operation

### Safe Patterns (Do Not Flag)

1. `Test-SafeFilePath` from GitHubCore.psm1
2. `Test-PathWithinRoot` from Generate-Agents.Common.psm1
3. GraphQL variables for parameter passing
4. `ValidateSet` attributes on parameters

## OWASP Mapping

- A01:2021 Broken Access Control: CWE-22, CWE-23, CWE-36
- A03:2021 Injection: CWE-73, CWE-77, CWE-78, CWE-94

## Severity Calibration

| Scenario | Base | Final |
|----------|------|-------|
| Path traversal (read) in local CLI | HIGH (7.5) | HIGH |
| Path traversal (read) in remote service | HIGH (7.5) | CRITICAL (9.1) |
| Path traversal (write/delete) | CRITICAL (9.1) | CRITICAL |
| Code injection any context | CRITICAL (9.8) | CRITICAL |

## Integration Steps

1. Update `src/claude/security.md` M1 section with these CWEs
2. Add PowerShell checklist patterns from M2
3. Update benchmarks in M5 with codebase findings
4. Create Forgetful memories for cross-project learning

## References

- Analysis: `.agents/analysis/cwe-699-framework-integration.md`
- Remediation Plan: `.agents/planning/security-agent-detection-gaps-remediation.md`
- CWE-699: https://cwe.mitre.org/data/definitions/699.html
