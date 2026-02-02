# ADR-035: Exit Code Standardization

**Status**: Accepted
**Date**: 2025-12-30
**Deciders**: User, Architect Agent, ADR Review Protocol
**Context**: Issue #536 - Standardize exit codes across PowerShell scripts

---

## Context and Problem Statement

PowerShell scripts across the repository use inconsistent exit codes. Analysis of 50+ scripts reveals:

1. **Inconsistent semantics**: `exit 1` means "validation failed" in one script, "merged" in another
2. **Undocumented codes**: Scripts use exit codes 0-7 without documentation
3. **Cross-language contract risk**: Bash callers interpret exit codes; inconsistency causes bugs
4. **Test confusion**: Test assertions check exit codes but meanings vary by script

**Key Question**: What exit code standard should all PowerShell scripts follow?

---

## Decision Drivers

1. **Cross-Platform Contract**: PowerShell scripts called from bash/GitHub Actions must have predictable exit semantics
2. **Testability**: Pester tests need clear expectations for exit code assertions
3. **Debugging**: Operators need to interpret exit codes without reading source
4. **Consistency**: ADR-005 standardized language; this standardizes exit semantics
5. **Industry Practice**: Exit code conventions from POSIX, sysexits.h, PowerShell best practices

---

## Considered Options

### Option 1: POSIX-Style Standard (CHOSEN)

Standard exit code ranges with documented semantics:

| Code | Meaning | Examples |
|------|---------|----------|
| 0 | Success | Operation completed, idempotent skip |
| 1 | General error / Validation failure | Logic error, assertion failed |
| 2 | Usage/configuration error | Missing required param, invalid argument, not in git repo |
| 3 | External service error | GitHub API failure, network error |
| 4 | Authentication/authorization error | Token expired, permission denied |
| 5-99 | Reserved for future standard use | |
| 100+ | Script-specific errors | Must be documented in script header |

**Pros**:

- Aligns with POSIX/sysexits conventions (familiar to operators)
- Clear separation: 1=logic, 2=config, 3=external, 4=auth
- Reserved range prevents collision
- Extensible via 100+ range

**Cons**:

- Requires updating existing scripts (migration effort)
- More granular than some scripts need

### Option 2: Binary Success/Failure

| Code | Meaning |
|------|---------|
| 0 | Success |
| 1 | Any failure |

**Pros**:

- Simple
- Already common in some scripts

**Cons**:

- No diagnostic value (caller cannot distinguish failure types)
- Debugging requires log inspection
- Cannot implement conditional retry logic

### Option 3: HTTP-Style Codes

| Code | Meaning |
|------|---------|
| 0 | Success (200-299 equivalent) |
| 4 | Client error (400-499 equivalent) |
| 5 | Server error (500-599 equivalent) |

**Pros**:

- Familiar to web developers

**Cons**:

- Awkward mapping (exit codes are not HTTP codes)
- Loses granularity (many error types map to 4 or 5)
- Not conventional for CLI tools

### Option 4: No Standard (Status Quo)

**Pros**:

- No migration effort

**Cons**:

- Continued inconsistency
- Cross-language bugs persist
- Test reliability issues continue
- Debugging remains difficult

---

## Decision Outcome

**Chosen option: Option 1 - POSIX-Style Standard**

### Exit Code Reference

| Code | Category | Semantic Meaning | When to Use |
|------|----------|------------------|-------------|
| 0 | Success | Operation completed successfully | All success paths, including idempotent no-ops |
| 1 | Logic Error | General failure, validation failed | Business logic failures, assertion violations |
| 2 | Config Error | Usage, configuration, or environment error | Missing params, invalid args, missing dependencies |
| 3 | External Error | External service or API error | GitHub API failures, network errors, timeouts |
| 4 | Auth Error | Authentication or authorization failure | Token expired, permission denied, rate limited |
| 5-99 | Reserved | Future standard use | Do not use until standardized |
| 100+ | Script-Specific | Custom error codes | Document in script header comment |

### When to Use Script-Specific Codes (100+)

**Use standard codes (0-4) when:**

- The error maps cleanly to an existing category
- CI/CD pipelines need to implement conditional logic (retry on 3, fail fast on 2)
- The script is called by multiple consumers who need consistent semantics
- The failure mode is common across many scripts (validation, auth, API errors)

**Use script-specific codes (100+) when:**

- The script has domain-specific states that consumers need to distinguish
- Multiple distinct success or failure modes exist that callers act on differently
- The standard categories (0-4) lose important diagnostic information
- The script serves as a specialized tool where callers need granular control flow

**Examples of script-specific codes:**

```powershell
# Test-PRMerged.ps1 - Callers need to distinguish merge states
# EXIT CODES:
# 0   - Success: PR is open (can proceed with merge)
# 100 - Info: PR already merged (idempotent success)
# 101 - Info: PR was closed without merge (requires intervention)
# 1   - Error: Validation failed
# 3   - Error: GitHub API error

# Get-PRChecks.ps1 - Callers need to know check status
# EXIT CODES:
# 0   - Success: All checks passed
# 100 - Pending: Checks still running (retry later)
# 101 - Failed: One or more checks failed
# 3   - Error: GitHub API error
```

**Decision Framework:**

| Question | If Yes | If No |
|----------|--------|-------|
| Does the caller need to distinguish multiple non-error states? | Use 100+ | Use 0 |
| Does the caller retry based on the exit code? | Use standard (0-4) | Consider 100+ |
| Is this a reusable utility called by many scripts? | Prefer standard (0-4) | 100+ acceptable |
| Would 0 vs 1 lose important caller context? | Use 100+ | Use standard |

### Documentation Requirement

All scripts MUST include exit code documentation in the script header:

```powershell
<#
.SYNOPSIS
    Brief description

.NOTES
    EXIT CODES:
    0  - Success: Operation completed
    1  - Error: Validation failed (specify conditions)
    2  - Error: Missing required parameter
    3  - Error: GitHub API returned error
    4  - Error: Authentication failed

    When called from bash/CI:
    - Exit 0 = success ($? equals 0)
    - Exit non-zero = failure ($? non-zero)
#>
```

### Deviation from Original Proposal (Issue #536)

Issue #536 proposed a simpler 0-5 exit code range. This ADR adopts a POSIX-aligned approach instead:

| Issue #536 Proposal | This ADR | Rationale for Change |
|---------------------|----------|----------------------|
| 1 (invalid params) | 2 (config error) | Align with POSIX convention (exit 2 = usage error) |
| 2 (auth failure) | 4 (auth error) | Reserve 2 for config; align auth with sysexits EX_NOUSER (67→4) |
| 3 (API error) | 3 (external error) | No change (aligned) |
| 4 (not found) | 3 (external error) | Consolidate into external service category |
| 5 (permission denied) | 4 (auth error) | Consolidate into authentication/authorization category |
| N/A | 1 (logic error) | Add general error category for validation failures |
| N/A | 5-99 (reserved) | Future-proof the standard |
| N/A | 100+ (script-specific) | Allow documented custom codes |

**Rationale for POSIX alignment**: Cross-language consistency with bash/Python/Ruby conventions reduces operator cognitive load and enables intelligent retry logic in CI workflows. The reserved range (5-99) future-proofs the standard without risking collision with script-specific codes.

### Rationale

1. **Industry Alignment**: POSIX exit codes and sysexits.h provide proven conventions
2. **Diagnostic Value**: Operators can triage without logs (2=fix config, 3=check GitHub, 4=renew token)
3. **Retry Logic**: CI can implement intelligent retry (retry on 3, fail fast on 2)
4. **Test Clarity**: Pester tests assert specific codes, improving test documentation

### Enforcement

1. **This ADR**: Canonical reference
2. **Code Review**: Verify exit code documentation and compliance
3. **Pester Tests**: Include exit code assertions with semantic checks
4. **PSScriptAnalyzer**: Future custom rule for undocumented exit statements

---

## Migration Plan

Implementation will be tracked via GitHub epic with 3 sub-tasks (see PR comment for issue creation request).

### Phase 1: Document Current State (Low Risk)

**GitHub Issue**: TBD (epic sub-task 1)

1. Add exit code documentation to existing scripts without changing behavior
2. Update scripts that already comply to reference this ADR

**Scope**: All scripts in `.claude/skills/`, `.github/scripts/`, `scripts/`

### Phase 2: Fix Inconsistencies (Medium Risk)

**GitHub Issue**: TBD (epic sub-task 2)

Priority fixes for semantic confusion:

| Script | Current | Issue | Fix |
|--------|---------|-------|-----|
| `Test-PRMerged.ps1` | exit 1 = merged | Success case exits with error code | Change to exit 0 with output property |
| Scripts using exit 1 for API errors | exit 1 | Should be exit 3 | Update to exit 3 |

**Testing**: Pester tests MUST be updated before changing exit codes to verify no regressions.

### Phase 3: Update Callers (Medium Risk)

**GitHub Issue**: TBD (epic sub-task 3)

Update bash/workflow callers to handle new exit codes appropriately.

**Scope**: GitHub Actions workflows in `.github/workflows/` that invoke PowerShell scripts.

---

## Current State Analysis

### Exit Code Usage Before Standardization

| Exit Code | Count | Current Usage |
|-----------|-------|---------------|
| 0 | 30+ | Success (consistent) |
| 1 | 15+ | Mixed: validation, API error, generic failure |
| 2 | 12+ | Config/dependency error (mostly consistent) |
| 3 | 8+ | API error (consistent in newer scripts) |
| 7 | 1 | Timeout (Get-PRChecks.ps1) |

### Notable Inconsistencies

1. **`Test-PRMerged.ps1`**: Uses `exit 1` for "PR is merged" which is a successful state determination
2. **`collect-metrics.ps1`**: Uses `exit 1` for both path-not-found and not-a-git-repo (should be exit 2)
3. **Timeout handling**: Only one script uses exit 7; others use exit 1 or exit 3

---

## Consequences

### Positive

1. **Predictable Cross-Language Behavior**: Bash callers can reliably interpret exit codes
2. **Improved Debugging**: Exit code alone provides diagnostic category
3. **Better Test Coverage**: Pester tests can assert semantic correctness
4. **Consistent Documentation**: All scripts document their exit codes
5. **Retry Intelligence**: CI can implement category-based retry logic

### Negative

1. **Migration Effort**: Existing scripts need updates (30+ files)
   - **Mitigation**: Phase over multiple PRs; prioritize high-impact scripts
2. **Breaking Changes**: Callers expecting specific codes may break
   - **Mitigation**: Phase 3 updates callers; document in PR

### Neutral

1. **Learning Curve**: Developers must learn standard
   - This ADR serves as reference

---

## Implementation Notes

### Helper Function Pattern

Consider adding a shared helper for consistent error exit:

```powershell
function Write-ErrorAndExit {
    param(
        [string]$Message,
        [ValidateRange(1,255)][int]$ExitCode = 1
    )
    Write-Error $Message
    exit $ExitCode
}
```

### Testing Pattern

```powershell
Describe "Exit Codes" {
    It "Should exit 0 on success" {
        $result = & $script -ValidParams
        $LASTEXITCODE | Should -Be 0
    }

    It "Should exit 2 on missing required parameter" {
        $result = & $script 2>&1
        $LASTEXITCODE | Should -Be 2
    }

    It "Should exit 3 on API error" {
        Mock gh { throw "API error" }
        $result = & $script -ValidParams 2>&1
        $LASTEXITCODE | Should -Be 3
    }
}
```

---

## Claude Code Hook Exit Codes

Claude Code hooks have **predefined exit code semantics** defined by Claude Code itself. Hook scripts (`.claude/hooks/*.ps1`) are **exempt** from this ADR's standard because Claude interprets these codes specially.

### Hook Exit Code Reference

| Exit Code | Claude Hook Behavior | This ADR Equivalent |
|-----------|---------------------|---------------------|
| 0 | Allow action / JSON decision processed | Success (aligned) |
| 1 | Hook error (fail-open: action allowed) | Logic Error (aligned) |
| 2 | **Block action immediately** | Config Error (DIFFERENT) |

### JSON Decision Mode (Recommended)

To align hook scripts with this ADR while maintaining Claude semantics, use **JSON decision mode**:

```powershell
# Block action using JSON decision (ADR-035 aligned)
$Output = @{
    decision = "deny"
    reason = "Validation failed: missing session log"
}
$Output | ConvertTo-Json -Compress
exit 0  # Success exit code, but action blocked via JSON
```

This approach:

- Uses exit 0 (aligned with this ADR's "success" semantic)
- Blocks the action via JSON `decision: "deny"`
- Provides structured error messages to Claude

### When Exit 2 Is Required

Only use exit 2 in hooks when:

1. **Immediate block required** without structured message
2. **Fallback** when JSON output fails

```powershell
# Emergency block (hook-specific, not ADR-035 aligned)
Write-Error "CRITICAL: Cannot proceed"
exit 2  # Claude blocks action
```

### Hook Script Documentation

Hook scripts should document this exemption:

```powershell
<#
.SYNOPSIS
    Claude Code PreToolUse hook for routing gates.

.NOTES
    EXIT CODES (Claude Hook Semantics - exempt from ADR-035):
    0  - Allow action OR JSON decision (deny/allow)
    1  - Hook error (fail-open)
    2  - Block action immediately (hook-specific)

    See: ADR-033 Routing-Level Enforcement Gates
    See: https://docs.anthropic.com/en/docs/claude-code/hooks
#>
```

### Cross-Reference

- [ADR-033: Routing-Level Enforcement Gates](./ADR-033-routing-level-enforcement-gates.md) - Uses Claude hooks for enforcement
- [Claude Code Hooks Documentation](https://docs.anthropic.com/en/docs/claude-code/hooks) - Official reference

---

## Related Decisions

- [ADR-005: PowerShell-Only Scripting](./ADR-005-powershell-only-scripting.md) - Language standardization
- [ADR-006: Thin Workflows, Testable Modules](./ADR-006-thin-workflows-testable-modules.md) - Module patterns
- **Memory**: `bash-integration-exit-codes` - Cross-language contract documentation

---

## References

- [POSIX Exit Codes](https://pubs.opengroup.org/onlinepubs/9699919799/utilities/V3_chap02.html#tag_18_08_02)
- [sysexits.h](https://man.freebsd.org/cgi/man.cgi?query=sysexits) - BSD exit code conventions
- [PowerShell Exit Codes Best Practices](https://learn.microsoft.com/en-us/powershell/module/microsoft.powershell.core/about/about_automatic_variables#lastexitcode)
- [Issue #536](https://github.com/rjmurillo/ai-agents/issues/536) - Original request

---

## Validation

Before accepting this ADR:

- [ ] Review exit code assignments align with project needs
- [ ] Confirm migration plan is feasible
- [ ] Verify no critical workflows depend on current inconsistent codes

After implementation:

- [ ] All scripts document exit codes in header
- [ ] High-priority inconsistencies resolved
- [ ] Pester tests include exit code assertions
- [ ] This ADR referenced in relevant code reviews

---

**Supersedes**: None (new decision)
**Amended by**: None
