# Security Analysis: Issue #1025 - Path Traversal StartsWith Vulnerability

**Issue**: [#1025](https://github.com/rjmurillo/ai-agents/issues/1025)
**Severity**: HIGH (CWE-22: Path Traversal)
**Status**: VERIFIED
**Date**: 2026-03-07

## Executive Summary

The bug report claim is **VALID**. The path traversal validation logic in the security agent template uses `StartsWith()` without appending a directory separator, creating exposure to prefix-based directory attacks.

## Vulnerability Details

### Affected Code Pattern

```powershell
# templates/agents/security.shared.md:644
if (-not $OutputFile.StartsWith($MemoriesDirFull, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "Path traversal attempt detected..."
}
```

### Attack Vector

An attacker can bypass the validation by creating or accessing a sibling directory that shares the same prefix:

| Base Directory | Malicious Input | Resolved Path | Validation |
|----------------|-----------------|---------------|------------|
| `/tmp/memories` | `../memories-evil/secret.txt` | `/tmp/memories-evil/secret.txt` | PASSES (BUG) |
| `/tmp/allowed` | `../allowed-evil/steal.txt` | `/tmp/allowed-evil/steal.txt` | PASSES (BUG) |

### Root Cause

```
"/tmp/memories-evil/file.txt".StartsWith("/tmp/memories") → True
```

The string `"/tmp/memories-evil"` does start with `"/tmp/memories"` as a string match, but it is NOT a subdirectory of `/tmp/memories`.

## Repro Evidence

```
ATTACK: Prefix-based directory escape
  Input: ../memories-evil/malicious.txt
  Resolved: /tmp/memories-evil/malicious.txt
  Base: /tmp/memories
  Result: Allowed=True (VULNERABLE)

ATTACK: Adjacent directory with same prefix
  Input: ../allowed-evil/steal.txt
  Resolved: /tmp/allowed-evil/steal.txt
  Base: /tmp/allowed
  Result: Allowed=True (VULNERABLE)
```

Repro scripts:
- Python: `.agents/analysis/issue-1025-repro.py`
- PowerShell: `.agents/analysis/issue-1025-repro.ps1`

## Affected Files

| File | Type | Priority |
|------|------|----------|
| `templates/agents/security.shared.md` | Source template | PRIMARY |
| `src/claude/security.md` | Generated | Secondary |
| `src/copilot-cli/security.agent.md` | Generated | Secondary |
| `src/vs-code-agents/security.agent.md` | Generated | Secondary |
| `.github/agents/security.agent.md` | Generated | Secondary |
| `.claude/agents/security.md` | Generated | Secondary |

## Impact Assessment

- **Confidentiality**: HIGH - Attacker can read files outside the intended directory
- **Integrity**: HIGH - Attacker can potentially write files outside the intended directory
- **Availability**: LOW - No direct denial of service impact

### CVSS v3.1 Estimate

- **Vector**: CVSS:3.1/AV:L/AC:L/PR:L/UI:N/S:U/C:H/I:H/A:N
- **Score**: 7.1 (HIGH)

## Remediation

### Fix (Single Line Change)

```powershell
# BEFORE (vulnerable)
if (-not $OutputFile.StartsWith($MemoriesDirFull, [System.StringComparison]::OrdinalIgnoreCase)) {

# AFTER (fixed)
if (-not $OutputFile.StartsWith($MemoriesDirFull + [System.IO.Path]::DirectorySeparatorChar, [System.StringComparison]::OrdinalIgnoreCase)) {
```

### Why This Works

```
"/tmp/memories-evil/file.txt".StartsWith("/tmp/memories/") → False (CORRECT)
"/tmp/memories/subdir/file.txt".StartsWith("/tmp/memories/") → True (CORRECT)
```

By appending the directory separator, we ensure that only true subdirectory paths match.

## Recommendation

1. **Fix the template**: Apply the one-line fix to `templates/agents/security.shared.md:644`
2. **Regenerate agents**: Run `build/generate_agents.py` to propagate the fix
3. **Add regression test**: Include the repro script in the test suite
4. **Update documentation**: Note this pattern in the security best practices

## Cross-References

- CWE-22: Improper Limitation of a Pathname to a Restricted Directory
- OWASP Path Traversal: https://owasp.org/www-community/attacks/Path_Traversal
- Related memory: `security-path-anchoring-pattern`
