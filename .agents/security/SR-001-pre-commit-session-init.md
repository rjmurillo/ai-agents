# Security Report: Pre-commit Hook & Session-Init Scripts

**Date**: 2025-01-23
**Scope**: `.githooks/pre-commit`, `scripts/`, `.claude/skills/session-init/`
**Branch**: Current vs origin/main

## Summary

| Finding Type | Count |
|--------------|-------|
| Critical | 0 |
| High | 1 |
| Medium | 3 |
| Low | 2 |

## Findings

### HIGH-001: Unvalidated Git Output in Path Operations

**Location**: `.githooks/pre-commit:119-128`

**CWE**: CWE-78 (OS Command Injection)

**Description**: The pre-commit hook uses `git rev-parse --show-toplevel` output directly in `cd` command without sufficient validation. While path existence is checked, malicious git config could inject path traversal or special characters.

**Current Code**:
```bash
REPO_ROOT=$(git rev-parse --show-toplevel) || {
    echo_error "Failed to determine repository root"
    exit 1
}
if [ ! -d "$REPO_ROOT" ]; then
    echo_error "Invalid repository root: $REPO_ROOT"
    exit 1
fi
cd "$REPO_ROOT"
```

**Impact**: An attacker with control over git config could potentially inject malicious paths. Risk is mitigated by the directory existence check but remains elevated in compromised environments.

**Likelihood**: Low (requires git config compromise)

**Risk Score**: 6/10

**Remediation**:
```bash
REPO_ROOT=$(git rev-parse --show-toplevel) || {
    echo_error "Failed to determine repository root"
    exit 1
}
# Sanitize: reject paths with suspicious characters
case "$REPO_ROOT" in
    *[';'*'$''`']*) 
        echo_error "Invalid characters in repository root: $REPO_ROOT"
        exit 1 ;;
esac
if [ ! -d "$REPO_ROOT" ]; then
    echo_error "Invalid repository root: $REPO_ROOT"
    exit 1
fi
cd "$REPO_ROOT" || exit 1
```

### MEDIUM-001: Unquoted Variable Expansion in Shell Commands

**Location**: `.githooks/pre-commit:192,205,302`

**CWE**: CWE-78 (OS Command Injection)

**Description**: The `$MARKDOWNLINT_CMD` variable is expanded without quotes in command execution contexts. While the variable is controlled (set to known values), this violates defense-in-depth principles.

**Current Code**:
```bash
# shellcheck disable=SC2086
$MARKDOWNLINT_CMD --fix --no-globs -- "${MD_FILES[@]}" 2>"$LINT_ERRORS" || true
```

**Impact**: If `get_markdownlint_cmd()` function is compromised or modified, unquoted expansion could allow command injection through spaces or special characters in the command path.

**Likelihood**: Low (requires function compromise)

**Risk Score**: 4/10

**Remediation**:
```bash
# Add quotes and remove shellcheck disable
"$MARKDOWNLINT_CMD" --fix --no-globs -- "${MD_FILES[@]}" 2>"$LINT_ERRORS" || true
```

### MEDIUM-002: Temporary File Cleanup Race Condition

**Location**: `.githooks/pre-commit:190-198,202-219`

**CWE**: CWE-377 (Insecure Temporary File)

**Description**: Temporary files created with `mktemp` are deleted with `rm -f` without checking for symlink substitution between creation and deletion. An attacker could replace the temp file with a symlink to cause deletion of arbitrary files.

**Current Code**:
```bash
LINT_ERRORS=$(mktemp)
$MARKDOWNLINT_CMD --fix --no-globs -- "${MD_FILES[@]}" 2>"$LINT_ERRORS" || true
# ... processing ...
rm -f "$LINT_ERRORS"
```

**Impact**: Potential deletion of arbitrary files if attacker can win race condition. Limited attack window (milliseconds).

**Likelihood**: Very Low (requires precise timing attack)

**Risk Score**: 3/10

**Remediation**:
```bash
LINT_ERRORS=$(mktemp)
trap 'rm -f "$LINT_ERRORS"' EXIT  # Automatic cleanup
# ... processing ...
# Remove explicit rm -f, rely on trap
```

Apply trap pattern consistently at script start:
```bash
cleanup() {
    rm -f "$LINT_ERRORS" "$LINT_OUTPUT" "$ANALYZER_OUTPUT" 2>/dev/null || true
}
trap cleanup EXIT INT TERM
```

### MEDIUM-003: Path Injection in PowerShell Script Parameters

**Location**: `.claude/skills/session-init/scripts/New-SessionLog.ps1:258-260`

**CWE**: CWE-73 (External Control of File Name or Path)

**Description**: The `New-SessionLog.ps1` script generates filenames from user-controlled objective text using `Get-DescriptiveKeywords`. While keywords are extracted, insufficient sanitization could allow path traversal characters (`../`, `..\\`) in filenames.

**Impact**: Potential file creation outside intended directory if keyword extraction doesn't filter path separators.

**Likelihood**: Low (depends on TemplateHelpers.psm1 implementation)

**Risk Score**: 4/10

**Remediation**:
Add explicit path separator sanitization in `Write-SessionLogFile`:
```powershell
# After Get-DescriptiveKeywords call
$keywords = $keywords -replace '[/\\:*?"<>|]', '-'  # Strip filesystem-invalid chars
$keywordSuffix = if ($keywords) { "-$keywords" } else { "" }
```

### LOW-001: Insufficient Error Context in Git Operations

**Location**: `.claude/skills/session-init/scripts/Extract-SessionTemplate.ps1:41-46`

**CWE**: CWE-209 (Information Exposure Through Error Message)

**Description**: Git error output is directly included in exception messages without sanitization. This could leak repository paths or system information if git produces verbose errors.

**Impact**: Low information disclosure (repository paths already known in normal operation).

**Risk Score**: 2/10

**Remediation**: Consider sanitizing git error output to remove absolute paths before including in user-facing errors.

### LOW-002: Stderr Redirection Limits Audit Trail

**Location**: `.githooks/pre-commit:192`

**CWE**: CWE-778 (Insufficient Logging)

**Description**: Linter stderr is redirected to temp file and only first 5 lines are shown. Full error context may be lost for debugging security-relevant linting failures.

**Impact**: Reduced visibility into potential security-relevant linting issues during incident investigation.

**Risk Score**: 2/10

**Remediation**: Log full linter output to `.git/hooks/pre-commit.log` for audit trail:
```bash
tee "$LINT_ERRORS" | tee -a .git/hooks/pre-commit.log >/dev/null
```

## Positive Security Observations

The following security controls are correctly implemented:

1. **Array-based file handling**: Properly uses bash arrays with quoted expansion `"${MD_FILES[@]}"` to prevent word splitting attacks (lines 176-179, 192, 205)

2. **Symlink rejection**: Consistently rejects symlinks before processing files (lines 227, 290, 365, 408, 449, 462) - mitigates TOCTOU attacks

3. **Path separator `--` usage**: Correctly uses `--` separator in git commands (lines 236, 466) to prevent option injection from filenames starting with `-`

4. **Command injection prevention**: Uses `$env:PSANALYZER_FILE` environment variable to pass filenames to PowerShell (line 302) instead of string interpolation

5. **Structured error handling**: PowerShell scripts use typed exceptions with detailed messages (Extract-SessionTemplate.ps1, New-SessionLog.ps1)

6. **Non-interactive detection**: New-SessionLog.ps1 properly detects and rejects non-interactive contexts (lines 88-102) preventing hang attacks in CI/CD

7. **Input validation**: PowerShell scripts validate session numbers are positive integers and objectives are non-empty (lines 107-125 in New-SessionLog.ps1)

8. **File existence verification**: Session log creation verifies file was written and has expected content size (lines 262-283 in New-SessionLog.ps1)

## Portability Assessment: `.githooks/pre-commit`

| Platform | Status | Notes |
|----------|--------|-------|
| Linux | ✅ PASS | Full compatibility, all tools available |
| macOS | ✅ PASS | Bash 3.x compatible (no mapfile/readarray), zsh fallback works |
| Windows Git Bash | ⚠️ CONDITIONAL | Requires pwsh in PATH, npm for markdownlint |
| Windows WSL | ✅ PASS | Full Linux compatibility |

**Portability Risk**: Windows Git Bash users may encounter `pwsh` not found warnings. This is acceptable per ADR-005 grandfathered exception.

## Bootstrap Script Security: `scripts/bootstrap-vm.sh`

| Check | Status | Finding |
|-------|--------|---------|
| Pipe-to-shell downloads | ⚠️ WARNING | Lines 14, 31, 42: curl piped to bash/sh without verification |
| TLS verification | ✅ PASS | Uses `-fsSL` (fail on error, silent, follow redirects, verify SSL) |
| Script idempotency | ✅ PASS | Checks for existing installations before installing |
| Set flags | ✅ PASS | Uses `set -euo pipefail` (fail on error, unset vars, pipefail) |
| Token handling | ✅ PASS | Respects both GITHUB_TOKEN and GH_TOKEN without logging |
| Privilege escalation | ✅ PASS | Uses sudo only where needed (apt-get, package installs) |

**Recommendation**: Consider adding checksum verification for downloaded packages:
```bash
# Before: curl ... | sh
# After:
curl -fsSL https://example.com/install.sh -o /tmp/install.sh
echo "expected_sha256  /tmp/install.sh" | sha256sum -c -
sh /tmp/install.sh
rm /tmp/install.sh
```

## Recommendations

### Priority P0 (High Risk)
1. **Fix HIGH-001**: Add path sanitization for `REPO_ROOT` in pre-commit hook (lines 119-128)

### Priority P1 (Medium Risk)
2. **Fix MEDIUM-001**: Quote `$MARKDOWNLINT_CMD` expansion (lines 192, 205, 302)
3. **Fix MEDIUM-002**: Add trap-based cleanup for temp files
4. **Fix MEDIUM-003**: Sanitize filesystem-invalid characters in session log filenames

### Priority P2 (Defense in Depth)
5. **Fix LOW-001**: Sanitize git error messages before displaying to users
6. **Fix LOW-002**: Add audit logging for pre-commit hook operations
7. **Enhance bootstrap-vm.sh**: Add checksum verification for piped downloads

## Compliance Notes

**OWASP Top 10 Mapping**:
- A03:2021 Injection → HIGH-001, MEDIUM-001, MEDIUM-003
- A01:2021 Broken Access Control → MEDIUM-002 (TOCTOU)
- A09:2021 Security Logging and Monitoring → LOW-002

**CWE Coverage**:
- CWE-78: OS Command Injection (HIGH-001, MEDIUM-001)
- CWE-377: Insecure Temporary File (MEDIUM-002)
- CWE-73: External Control of File Name (MEDIUM-003)
- CWE-209: Information Exposure (LOW-001)
- CWE-778: Insufficient Logging (LOW-002)

---

**Security Agent**: Verified 2025-01-23
**Total Issues**: 6 (0 Critical, 1 High, 3 Medium, 2 Low)
**Blocking Issues**: None (High risk requires git config compromise)
**Recommendation**: CONDITIONAL APPROVAL - Fix HIGH-001 before production deployment
