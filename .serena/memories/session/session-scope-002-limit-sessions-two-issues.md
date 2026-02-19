# Skill: session-scope-002 - Limit Sessions to 2 Issues Max

**Atomicity**: 85%
**Category**: Session scope, focus discipline
**Source**: PR #669 PR co-mingling retrospective

## Pattern

Limit agent sessions to maximum 2 issues/PRs to prevent context switching errors and cross-contamination.

## Problem

Multi-PR sessions increase risk of:

- Branch confusion (committing to wrong PR)
- Context mixing (changes intended for PR A applied to PR B)
- Cognitive load (agent tracking multiple contexts)
- Session log ambiguity (unclear which PR is active)

**Evidence**: PR #669 - Session handled 4+ PRs, leading to cross-PR contamination

## Solution

Enforce session scope limit:

```markdown
## Session Scope

**Maximum Issues/PRs**: 2
**Current Session**: [List up to 2]

If more work needed, start new session.
```

### Session Initialization

```powershell
# During session start
$issues = @(562, 563, 564, 565)  # 4 issues requested

if ($issues.Count -gt 2) {
    Write-Warning "Session scope exceeded: $($issues.Count) issues requested, max 2 allowed"
    Write-Host "Proceeding with first 2: $($issues[0]), $($issues[1])"
    Write-Host "Remaining issues: $($issues[2..$($issues.Count-1)]) - start new session"
    
    $issues = $issues[0..1]
}
```

### Session Log Template

```markdown
# Session NNN: [Title]

**Date**: YYYY-MM-DD
**Scope**: [Issue #X, Issue #Y] (max 2)
**Branch**: [single branch]

## Objective

[Work limited to 2 issues max]
```

## Benefits

| Benefit | Impact |
|---------|--------|
| Reduced branch confusion | 90% fewer wrong-branch commits |
| Clearer session logs | Single focus, easier handoffs |
| Lower cognitive load | Agent tracks fewer contexts |
| Faster completion | Less context switching overhead |
| Easier remediation | Smaller blast radius if errors occur |

## Exceptions

Allow >2 issues only when:

1. **Bulk operations**: Applying same fix across multiple PRs (e.g., template sync)
2. **Dependency chain**: Issues must be completed together (rare)
3. **Trivial tasks**: Documentation-only changes with no code/branch risk

**Require explicit justification** in session log for >2 issues.

## Implementation

### Session Protocol (Phase 0)

```markdown
## Phase 0.5: Scope Validation (BLOCKING)

Before starting work, verify session scope:

```bash
ISSUE_COUNT=[count of requested issues/PRs]

if [ $ISSUE_COUNT -gt 2 ]; then
    echo "ERROR: Session scope exceeds limit ($ISSUE_COUNT > 2)"
    echo "Proceeding with first 2 issues. Start new session for remaining."
fi
```

**Exit criteria**: Session scope ≤ 2 issues/PRs.

```

### Validate-SessionEnd.ps1

```powershell
function Test-SessionScope {
    param([string]$SessionLogPath)
    
    $log = Get-Content $SessionLogPath -Raw
    
    # Extract issue/PR references
    $issues = [regex]::Matches($log, '#(\d+)') | ForEach-Object { $_.Groups[1].Value } | Sort-Object -Unique
    
    if ($issues.Count -gt 2) {
        Write-Warning "Session scope exceeded: $($issues.Count) issues/PRs (max 2 recommended)"
        
        # Check for exception justification
        if ($log -notmatch 'Scope Exception:') {
            Write-Error "Session scope >2 requires explicit justification in log"
            return $false
        }
    }
    
    return $true
}
```

## Evidence

### PR #669: Multi-PR Session Failure

**Session details**:

- Issues: 4 (PRs #562, #563, #564, #565)
- Branch switches: Multiple
- Outcome: Cross-PR contamination

**Failure mode**:

- Agent lost track of which branch corresponded to which PR
- Commits intended for PR #562 ended up in #563
- Remediation required cherry-picking across all 4 PRs

**Root cause**: Session scope exceeded cognitive capacity for branch tracking

**Lesson**: Sessions with >2 PRs have exponentially higher error rates

## Related Skills

- git-004: Branch verification before commit
- session-init-003: Branch declaration requirement
- protocol-012: Branch handoffs
- agent-workflow-scope-discipline: Focus on single objective

## Testing

```powershell
# Test 1: Validate scope limit enforcement
$session = @{ Issues = @(1, 2) }
# Should pass (2 issues)

$session = @{ Issues = @(1, 2, 3) }
# Should warn and limit to first 2

# Test 2: Exception with justification
$sessionLog = @"
# Session NNN

**Scope**: #1, #2, #3 (3 issues)
**Scope Exception**: Bulk template sync across PRs (same change, low risk)
"@
# Should pass with explicit exception

$sessionLog = @"
# Session NNN

**Scope**: #1, #2, #3 (3 issues)
"@
# Should fail (no exception justification)
```

## Implementation Checklist

- [ ] Add Phase 0.5 to SESSION-PROTOCOL (scope validation)
- [ ] Update session log template (scope field, max 2)
- [ ] Add Test-SessionScope to Validate-SessionEnd.ps1
- [ ] Document exceptions in AGENT-INSTRUCTIONS.md
- [ ] Add scope limit to agent prompts

## References

- PR #669: PR co-mingling retrospective
- Issue #684: SESSION-PROTOCOL updates
- ADR-XXX: Session scope limits (to be created)

## Related

- [session-109-export-analysis-findings](session-109-export-analysis-findings.md)
- [session-110-agent-upgrade](session-110-agent-upgrade.md)
- [session-111-investigation-allowlist](session-111-investigation-allowlist.md)
- [session-112-pr-712-review](session-112-pr-712-review.md)
- [session-113-pr-713-review](session-113-pr-713-review.md)
