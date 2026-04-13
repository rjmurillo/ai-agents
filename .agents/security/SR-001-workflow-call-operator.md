# Security Report: PowerShell Call Operator Addition to pr-maintenance.yml

**Date**: 2025-12-24
**Scope**: `.github/workflows/pr-maintenance.yml` lines 104, 123
**Change**: Added PowerShell call operator `&` to script invocations
**Risk Level**: LOW

## Summary

| Finding Type | Count |
|--------------|-------|
| Critical | 0 |
| High | 0 |
| Medium | 0 |
| Low | 1 |

**Overall Assessment**: [PASS] - Change is security-neutral and fixes a legitimate functional issue.

## Executive Summary

The addition of PowerShell call operator `&` to two script invocations in the pr-maintenance workflow is a required syntactic fix with no adverse security impact. The change enables proper script execution without introducing command injection vulnerabilities or modifying security controls.

**Risk Score**: 2/10 (Low - syntactic fix only)

## Changes Analyzed

### Line 104 (Create alert issue for blocked PRs)

**Before**:
```powershell
./.claude/skills/github/scripts/issue/New-Issue.ps1 -Title "[PR Maintenance] Blocked PRs Require Human Action" -Body $body -Labels "automation,needs-triage"
```

**After**:
```powershell
& ./.claude/skills/github/scripts/issue/New-Issue.ps1 -Title "[PR Maintenance] Blocked PRs Require Human Action" -Body $body -Labels "automation,needs-triage"
```

### Line 123 (Notify on failure)

**Before**:
```powershell
./.claude/skills/github/scripts/issue/New-Issue.ps1 -Title "[ALERT] PR Maintenance Workflow Failed" -Body $body -Labels "automation,priority:P1"
```

**After**:
```powershell
& ./.claude/skills/github/scripts/issue/New-Issue.ps1 -Title "[ALERT] PR Maintenance Workflow Failed" -Body $body -Labels "automation,priority:P1"
```

## Security Analysis

### 1. Command Injection Risk Assessment

**Finding**: No command injection risk introduced

**Analysis**:

- **Call Operator Behavior**: The `&` operator in PowerShell is the call operator, not a command chaining operator. It executes the script at the specified path without shell interpretation of additional commands.
- **Path Static**: Script path `./.claude/skills/github/scripts/issue/New-Issue.ps1` is hardcoded, not user-controlled.
- **Parameter Validation**: The called script (`New-Issue.ps1`) validates all inputs through `GitHubHelpers.psm1`:
  - `Test-GitHubNameValid` validates Owner/Repo names (lines 19-59 of GitHubHelpers.psm1)
  - `Test-SafeFilePath` prevents path traversal (lines 61-104 of GitHubHelpers.psm1)
  - `Assert-ValidBodyFile` validates file paths (lines 106-137 of GitHubHelpers.psm1)
- **Input Sources**: Variables `$body`, `$runUrl` are constructed from GitHub context variables (`${{ github.* }}`) and validated functions from `PRMaintenanceModule.psm1`.

**Evidence**:

1. New-Issue.ps1 line 47-52: Imports GitHubHelpers.psm1 and calls `Resolve-RepoParams` which validates Owner/Repo names
2. GitHubHelpers.psm1 lines 208-213: Explicit validation prevents CWE-78 command injection
3. New-Issue.ps1 line 78: Uses `gh` CLI with array splatting `& gh @ghArgs`, not string concatenation

**CWE Reference**: No CWE-78 (OS Command Injection) vulnerability introduced.

### 2. Path Traversal Risk Assessment

**Finding**: No path traversal risk

**Analysis**:

- **Script Path**: Hardcoded relative path `./.claude/skills/github/scripts/issue/New-Issue.ps1` resolves from workflow working directory (checked out repository root).
- **No Dynamic Path Construction**: Path is not assembled from user input or environment variables.
- **Workflow Context**: GitHub Actions checkout action (line 40) ensures working directory is the repository root with controlled content.

**CWE Reference**: No CWE-22 (Path Traversal) vulnerability.

### 3. Token Usage Audit

**Finding**: BOT_PAT usage is appropriate

**Analysis**:

- **Scope**: BOT_PAT used in lines 54, 66, 79, 97, 117 for GitHub API operations via `gh` CLI.
- **Permissions Required**: Token needs `contents:write`, `pull-requests:write`, `issues:write` (declared lines 17-20).
- **Appropriate Use Cases**:
  - Creating issues for blocked PRs (line 104)
  - Creating alert issues on workflow failure (line 123)
  - Running PR maintenance operations (line 66)
  - Checking API rate limits (line 54)
- **No Token Leakage**: Token passed via environment variable `GH_TOKEN`, not logged or echoed.
- **Secret Handling**: GitHub Actions automatically redacts secrets in logs.

**Best Practice Compliance**: Follows GitHub Actions secret handling best practices.

### 4. Input Validation in Called Script

**Finding**: Strong input validation in place

**Analysis** (New-Issue.ps1):

- **Line 49**: Calls `Assert-GhAuthenticated` - fails fast if gh CLI not authenticated
- **Line 50-52**: Calls `Resolve-RepoParams` which validates Owner/Repo against regex patterns preventing injection
- **Line 54-56**: Validates Title parameter is not empty
- **Line 59-64**: Validates BodyFile path exists and is safe (if used)
- **Line 67-75**: Constructs `gh` command using array (not string concatenation)
- **Line 78**: Executes `gh` with argument array, preventing argument injection

**Security Controls Verified**:

| Control | Location | Status |
|---------|----------|--------|
| Authentication check | New-Issue.ps1:49 | ✅ Implemented |
| Owner/Repo validation | GitHubHelpers.psm1:208-213 | ✅ Implemented |
| Path traversal prevention | GitHubHelpers.psm1:90-103 | ✅ Implemented |
| Input sanitization | New-Issue.ps1:54-64 | ✅ Implemented |
| Command array construction | New-Issue.ps1:67-75 | ✅ Implemented |

### 5. Comparison: Before vs After

**Functional Difference**:

- **Before**: PowerShell interprets `./.claude/...` as a file path string (not executable). Execution fails unless script is in PATH or current directory.
- **After**: PowerShell call operator `&` explicitly executes the script at the given path. This is the correct syntax for invoking scripts by path.

**Security Difference**: None. The call operator does not change security posture:

- No new attack surface introduced
- No privilege escalation
- No additional data exposure
- No weakening of existing controls

### 6. Workflow Execution Context

**Finding**: Workflow runs in isolated GitHub Actions environment

**Analysis**:

- **Runner**: ubuntu-24.04-arm (line 35)
- **Permissions**: Explicitly scoped to contents, pull-requests, issues (lines 17-20)
- **Timeout**: 45 minutes (line 36) prevents resource exhaustion
- **Concurrency**: Single instance with no cancellation (lines 22-24)
- **Artifact Retention**: Logs retained 30 days (line 112) for audit trail

**Isolation Boundaries**:

- GitHub Actions runner is ephemeral and isolated per workflow run
- Secrets are injected only into steps that declare them
- Working directory is cleaned between runs

## Threat Model (STRIDE)

| Threat | Category | Impact | Likelihood | Mitigation |
|--------|----------|--------|------------|------------|
| Malicious PR author manipulates $body variable | Tampering | Low | Low | Input validated by New-Issue.ps1; gh CLI escapes arguments |
| Attacker modifies script path in workflow | Tampering | High | Very Low | Requires write access to .github/workflows/; CODEOWNERS protection |
| BOT_PAT token leakage | Information Disclosure | High | Very Low | GitHub Actions redacts secrets; token in environment variable only |
| Script executes unintended commands | Elevation of Privilege | Medium | Very Low | Static path; input validation; array-based gh invocation |

**Threat Summary**: No new threats introduced by call operator addition. Existing mitigations remain effective.

## Findings

### LOW-001: Workflow Executes Scripts from Repository Content

**Location**: `.github/workflows/pr-maintenance.yml:104, 123`
**Severity**: Low
**CWE**: N/A (by design)
**Impact**: Workflow executes scripts that are part of the repository. If an attacker gains write access to the repository, they could modify scripts.

**Remediation**: This is inherent to GitHub Actions workflows that use repository scripts. Mitigations in place:

1. Branch protection on main/master branches
2. CODEOWNERS file for .github/ directory (if configured)
3. Required PR reviews for workflow changes
4. Workflow permissions scoped to minimum required

**Risk Acceptance**: This is standard practice for GitHub Actions. Risk is acceptable given repository access controls.

**Status**: Accepted (by design)

## Dependencies Analysis

**Direct Dependencies** (pr-maintenance.yml):

| Dependency | Version | Purpose | Vulnerabilities |
|------------|---------|---------|-----------------|
| actions/checkout | v4 (SHA: b4ffde6...) | Repository checkout | None known |
| actions/upload-artifact | v4 (SHA: 26f96df...) | Artifact upload | None known |
| gh CLI | Latest (ubuntu package) | GitHub API operations | None known (authenticated use) |

**Script Dependencies**:

| Script | Module Dependencies | Validation |
|--------|-------------------|------------|
| New-Issue.ps1 | GitHubHelpers.psm1 | Input validation (lines 19-137) |
| New-Issue.ps1 | gh CLI | Command execution (line 78) |

**Transitive Risk**: Low. All dependencies are maintained by GitHub (actions) or validated before use (scripts).

## Attack Surface Assessment

**New Surface Introduced**: None

**Existing Surface**: Unchanged

| Surface | Exposure | Controls |
|---------|----------|----------|
| GitHub API (via gh CLI) | High (scheduled + manual) | BOT_PAT scoped permissions; rate limiting |
| PowerShell script execution | Medium (trusted scripts) | Input validation; static paths |
| Workflow logs | Low (authenticated access) | Secret redaction; 90-day retention |

**Attack Vector Assessment**:

1. **Script Modification**: Requires repository write access (mitigated by branch protection)
2. **Token Compromise**: Requires GitHub secret access (mitigated by GitHub's secret management)
3. **Input Injection**: Mitigated by input validation in called scripts

## Compliance Implications

**Standards Assessed**:

- **OWASP Top 10 (2021)**: No violations introduced
- **CWE Top 25**: No new weaknesses
- **GitHub Actions Security Best Practices**: Compliant

**Specific Compliance**:

| Requirement | Status | Evidence |
|-------------|--------|----------|
| A01:2021 Broken Access Control | ✅ Pass | Workflow permissions scoped (lines 17-20) |
| A02:2021 Cryptographic Failures | ✅ Pass | BOT_PAT in environment variable, not logged |
| A03:2021 Injection | ✅ Pass | Input validation in GitHubHelpers.psm1 |
| A05:2021 Security Misconfiguration | ✅ Pass | Minimal permissions; timeout configured |
| A07:2021 Identification and Authentication | ✅ Pass | gh CLI authentication check enforced |

## Recommendations

### No Action Required (Change is Safe)

The addition of the PowerShell call operator is:

1. **Syntactically Correct**: Required for script execution by path
2. **Functionally Necessary**: Fixes workflow failure
3. **Security-Neutral**: No new vulnerabilities introduced
4. **Best Practice Aligned**: Uses explicit script invocation

### Optional Enhancements (Not Related to This Change)

These are general improvements for the workflow, not issues with the current change:

1. **Pin Script Versions**: Consider versioning scripts and pinning to specific commits (similar to actions/checkout SHA pinning)
2. **Add Script Integrity Check**: Add SHA256 checksums for scripts before execution
3. **Limit BOT_PAT Scope**: Ensure BOT_PAT has minimum required permissions (currently appears appropriate)
4. **Add Security Scanning**: Consider adding CodeQL or similar to scan workflow files

**Priority**: P2 (Nice-to-have, not urgent)

## Verification Tests

| Test Type | Status | Coverage |
|-----------|--------|----------|
| Static Analysis | ✅ Pass | Manual code review completed |
| Input Validation Review | ✅ Pass | Validated GitHubHelpers.psm1 controls |
| Threat Modeling | ✅ Pass | STRIDE analysis complete |
| Dependency Audit | ✅ Pass | No vulnerable dependencies |
| Compliance Check | ✅ Pass | OWASP Top 10 assessed |

**Manual Verification Performed**:

1. Reviewed New-Issue.ps1 for input handling
2. Reviewed GitHubHelpers.psm1 validation functions
3. Analyzed gh CLI usage pattern
4. Verified BOT_PAT usage scope
5. Checked GitHub Actions security best practices compliance

## Blast Radius Assessment

| If Control Fails | Systems Affected | Data at Risk | Containment Strategy |
|------------------|-----------------|--------------|---------------------|
| Script executes malicious code | Single workflow run (isolated runner) | Repository contents (read), BOT_PAT token scope | Runner isolation; scoped token permissions; audit logs |
| BOT_PAT compromised | Repository contents, issues, PRs within token scope | Repository data | Token rotation; audit logs; IP allowlisting (if configured) |
| Input validation bypass | Issue creation with malformed data | Issue metadata only | GitHub API validation; rate limiting |

**Worst Case Impact**: Compromised BOT_PAT could allow unauthorized issue/PR creation and modification within the repository. Impact limited by token scope (no org-wide permissions apparent).

**Isolation Boundaries**:

- GitHub Actions runner (ephemeral, isolated)
- BOT_PAT scope (repository-level, not org-level)
- Branch protection (prevents direct push to protected branches)

## Conclusion

**Recommendation**: ✅ **APPROVED** - Change meets security requirements

### Summary

The addition of PowerShell call operator `&` to lines 104 and 123 of `.github/workflows/pr-maintenance.yml` is a necessary syntactic correction with no adverse security implications.

**Key Findings**:

1. **No New Vulnerabilities**: Change does not introduce command injection, path traversal, or other security weaknesses
2. **Strong Existing Controls**: Called script implements robust input validation and safe command execution patterns
3. **Appropriate Token Usage**: BOT_PAT usage follows GitHub Actions security best practices
4. **Minimal Attack Surface**: No expansion of attack surface; existing protections remain effective

**Risk Assessment**: 2/10 (Low)

- **Impact**: Low (syntactic fix only)
- **Likelihood**: N/A (not a vulnerability)
- **Exploitability**: None (no exploit vector)

### Required Actions

None. Change is approved for merge.

### Optional Follow-Up (Future Work)

Consider implementing general workflow hardening measures documented in Recommendations section (Priority: P2).

## Signature

**Security Agent**: Reviewed 2025-12-24
**Status**: [COMPLETE]
**Approval**: [PASS] - No security concerns identified
