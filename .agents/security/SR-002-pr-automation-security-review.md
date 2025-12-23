# Security Review: PR Automation Script

**Script**: `scripts/Invoke-PRMaintenance.ps1`  
**Reviewed**: 2025-12-22  
**Status**: Phase 1 Security Fixes Required

## Executive Summary

Security review identified 3 HIGH severity findings requiring remediation before production deployment:

| Finding | Severity | CWE | Status |
|---------|----------|-----|--------|
| Command injection via branch name | HIGH | CWE-78 | Fix Required |
| Path traversal in worktree creation | HIGH | CWE-22 | Fix Required |
| CommentId integer overflow | MEDIUM | CWE-190 | Fix Required |

## Findings

### HIGH-001: Command Injection via Branch Name

**CWE**: [CWE-78: OS Command Injection](https://cwe.mitre.org/data/definitions/78.html)

**Description**: Branch names from GitHub API are passed directly to git commands without validation.

**Attack Vector**:
```powershell
# Attacker creates PR from branch: main; rm -rf /
# Script executes: git checkout "main; rm -rf /"
# Result: Command injection
```

**Impact**: Arbitrary command execution with workflow runner permissions

**Remediation**:
```powershell
function Test-SafeBranchName {
    param([string]$BranchName)
    
    # Reject: empty, starts with -, contains .., contains control chars
    if ([string]::IsNullOrWhiteSpace($BranchName)) { return $false }
    if ($BranchName.StartsWith('-')) { return $false }
    if ($BranchName.Contains('..')) { return $false }
    if ($BranchName -match '[\x00-\x1f\x7f]') { return $false }
    if ($BranchName -match '[~^:?*\[\]\\]') { return $false }
    
    return $true
}

# Usage
if (-not (Test-SafeBranchName -BranchName $branch)) {
    throw "Invalid branch name: $branch"
}
```

**Priority**: P0 (BLOCKING for production deployment)

### HIGH-002: Path Traversal in Worktree Creation

**CWE**: [CWE-22: Path Traversal](https://cwe.mitre.org/data/definitions/22.html)

**Description**: Worktree paths constructed from PR numbers without validation.

**Attack Vector**:
```powershell
# Attacker manipulates PR number to: ../../.ssh/authorized_keys
# Script creates worktree at: /runner/_work/../../.ssh/authorized_keys
# Result: File overwrites outside intended directory
```

**Impact**: File overwrites, information disclosure

**Remediation**:
```powershell
function Get-SafeWorktreePath {
    param(
        [string]$BasePath,
        [int]$PRNumber
    )
    
    $base = Resolve-Path $BasePath -ErrorAction Stop
    $worktreePath = Join-Path $base.Path "ai-agents-pr-$PRNumber"
    
    # Ensure path is within base (no ..)
    $resolved = [System.IO.Path]::GetFullPath($worktreePath)
    if (-not $resolved.StartsWith($base.Path)) {
        throw "Worktree path escapes base directory: $worktreePath"
    }
    
    return $resolved
}
```

**Priority**: P0 (BLOCKING for production deployment)

### MEDIUM-001: Integer Overflow in CommentId

**CWE**: [CWE-190: Integer Overflow](https://cwe.mitre.org/data/definitions/190.html)

**Description**: CommentId parameter typed as `[int]` but GitHub comment IDs exceed `Int32.MaxValue` (2,147,483,647).

**Impact**: Cannot process comments with IDs > 2.1 billion (most recent comments)

**Remediation**:
```powershell
# Change parameter type from [int] to [long]
function Add-CommentReaction {
    param(
        [string]$Owner,
        [string]$Repo,
        [long]$CommentId,  # Changed from [int]
        [string]$Reaction = 'eyes'
    )
    # ...
}
```

**Priority**: P0 (CORRECTNESS - script will fail on modern PRs)

## GitHub Acceptable Use Policy Compliance

Per [GitHub Acceptable Use Policies §4](https://docs.github.com/en/site-policy/acceptable-use-policies/github-acceptable-use-policies#4-spam-and-inauthentic-activity-on-github), we must avoid:

- **Automated excessive bulk activity**: Hourly runs with rate limiting
- **Inauthentic interactions**: Bot clearly identified via BOT_PAT attribution
- **Rank abuse**: No starring/following, only PR maintenance
- **Undue burden on servers**: Rate limiting prevents API exhaustion

**Compliance Measures**:

1. **Rate Limiting**: Multi-resource checks prevent API exhaustion
2. **Clear Attribution**: BOT_PAT ensures bot identity is transparent
3. **Throttling**: Hourly schedule (not more frequent)
4. **Legitimate Purpose**: PR maintenance is core to repository operations

## Defense-in-Depth Checklist

- [ ] **Input Validation**: Branch names, PR numbers, comment IDs validated
- [ ] **Path Validation**: Worktree paths confined to base directory  
- [ ] **Type Safety**: Int64 for GitHub IDs (not Int32)
- [ ] **Rate Limiting**: Multi-resource threshold checks
- [ ] **Authentication**: BOT_PAT for clear attribution
- [ ] **Concurrency Control**: GitHub Actions workflow-level (ephemeral-safe)
- [ ] **Error Handling**: No silent failures (all errors logged)
- [ ] **DryRun Mode**: Safe testing before live deployment

## Test Requirements

**Security Tests** (Pester):
```powershell
Describe "Input Validation Security" {
    Context "Branch Name Validation" {
        It "Rejects command injection attempts" {
            $malicious = "main; rm -rf /"
            Test-SafeBranchName $malicious | Should -Be $false
        }
        
        It "Rejects path traversal attempts" {
            $malicious = "../../etc/passwd"
            Test-SafeBranchName $malicious | Should -Be $false
        }
    }
    
    Context "Worktree Path Validation" {
        It "Prevents directory escape" {
            {
                Get-SafeWorktreePath -BasePath "/tmp" -PRNumber "../../root"
            } | Should -Throw "*escapes base directory*"
        }
    }
    
    Context "CommentId Type Safety" {
        It "Handles IDs > Int32.MaxValue" {
            $largeId = 3000000000  # > 2.1 billion
            {
                Add-CommentReaction -CommentId $largeId -Reaction "eyes"
            } | Should -Not -Throw
        }
    }
}
```

## Remediation Priority

| Priority | Finding | Effort | Risk if Not Fixed |
|----------|---------|--------|-------------------|
| P0 | HIGH-001 (Command Injection) | 2 hours | CRITICAL - Arbitrary code execution |
| P0 | HIGH-002 (Path Traversal) | 2 hours | HIGH - File overwrites, data corruption |
| P0 | MEDIUM-001 (Integer Overflow) | 1 hour | HIGH - Script fails on modern PRs |

**Total Effort**: 5 hours (P0 only)

## Approval Gates

**Phase 1 (P0 Fixes)**: BLOCKING for production deployment
- [ ] All P0 findings remediated
- [ ] Security tests pass (68+ tests across 4 functions)
- [ ] Code review by security agent
- [ ] Integration test with real PRs (DryRun mode)

**Phase 2 (Operational Hardening)**: Post-deployment enhancements
- Structured logging for security events
- Retry logic with exponential backoff
- Failure alerting (create GitHub issue)

## References

- **ADR**: [ADR-015: PR Automation Concurrency and Safety Controls](../architecture/ADR-015-pr-automation-concurrency-and-safety.md)
- **Implementation Plan**: [`.agents/planning/pr-automation-implementation-plan.md`](../planning/pr-automation-implementation-plan.md)
- **DevOps Review**: [`.agents/devops/pr-automation-script-review.md`](../devops/pr-automation-script-review.md)
- **Test Results**: Session 66 - 68/68 tests passing
- **Rollback Procedure**: [`.agents/operations/pr-maintenance-rollback.md`](../operations/pr-maintenance-rollback.md)
