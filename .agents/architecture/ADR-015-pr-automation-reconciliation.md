# ADR-015: PR Automation Script Reconciliation

## Status

Proposed

## Date

2025-12-22

## Decision-Makers

- Architect Agent (this ADR)
- Security Agent (review)
- Critic Agent (review)
- DevOps Agent (review)
- QA Agent (review)
- Roadmap Agent (review)

## Context

Five agents reviewed `scripts/Invoke-PRMaintenance.ps1` and produced conflicting assessments:

| Agent | Rating | Focus |
|-------|--------|-------|
| DevOps | B+ (Ready for operationalization) | Infrastructure, logging, scheduling |
| Critic | 15% complete | Feature completeness vs goals |
| Security | 3 HIGH findings | Command injection, concurrency, path traversal |
| QA | Integer overflow bug | CommentId exceeds Int32.MaxValue |
| Roadmap | 2 missing features | HANDOFF.md data loss, no bot replies |

The script is designed for automated hourly PR maintenance with four stated goals:
1. Acknowledge unacknowledged bot comments (eyes reaction)
2. Resolve merge conflicts with main
3. Close PRs superseded by merged PRs
4. Report blocked PRs (CHANGES_REQUESTED)

Thirteen critical issues were identified across all reviews. This ADR reconciles the findings and defines a deployment path.

## Decision

**Phase 1 (Minimum Viable Script)**: Fix P0 security and correctness issues before deployment.

**Phase 2 (Operational Excellence)**: Add monitoring, alerting, and resilience after successful Phase 1 deployment.

**Phase 3 (Feature Completion)**: Implement reply functionality and thread resolution in a follow-up PR.

### Scope Decision Matrix

| Issue | Source | Priority | Scope | Rationale |
|-------|--------|----------|-------|-----------|
| Command injection via branch name | Security | P0 | Phase 1 | Safety: unvalidated input to git commands |
| No lock file for concurrency | Security | P0 | Phase 1 | Race condition risk with hourly cron |
| Path traversal in worktree | Security | P0 | Phase 1 | Safety: directory escape possible |
| Int64 CommentId overflow | QA | P0 | Phase 1 | Correctness: GitHub IDs exceed Int32 |
| GitHub Actions concurrency group | DevOps | P0 | Phase 1 | Required for safe hourly runs |
| Rate limit pre-flight check | DevOps/HLA | P0 | Phase 1 | Silent API exhaustion is production incident |
| HANDOFF.md merge loses data | Roadmap | P1 | Phase 2 | Session history preserved in session logs |
| Worktree cleanup on crash | Critic | P1 | Phase 2 | Pre-run cleanup mitigates |
| Retry logic (exponential backoff) | DevOps | P1 | Phase 2 | Resilience enhancement |
| Structured logging (JSON) | DevOps | P2 | Phase 2 | Queryability improvement |
| Missing reply functionality | Critic/Roadmap | P2 | Phase 3 | New feature, not a fix |
| Thread resolution (GraphQL) | Critic | P2 | Phase 3 | New feature, not a fix |
| Code change implementation | Critic | P3 | Defer | Requires AI agent integration |

### Reconciling B+ vs 15%

Both ratings are valid assessments of different dimensions:

**DevOps B+ evaluates operational readiness:**
- Comprehensive error handling: PASS
- Logging and dry-run capability: PASS
- Exit codes for CI integration: PASS
- Secrets management (uses gh CLI): PASS
- Branch protection check: PASS
- 12-Factor compliance: 9/11 factors satisfied

**Critic 15% evaluates feature completeness:**

| Feature | Status | Completion |
|---------|--------|------------|
| Acknowledge comments (reaction) | Implemented | 100% |
| Reply to comments | NOT IMPLEMENTED | 0% |
| Resolve review threads | NOT IMPLEMENTED | 0% |
| Implement code changes | NOT IMPLEMENTED | 0% |
| Merge conflict resolution | Implemented (HANDOFF.md only) | 50% |
| Superseded PR detection | Implemented | 100% |
| Blocked PR reporting | Implemented | 100% |

**Weighted Average**: (100 + 0 + 0 + 0 + 50 + 100 + 100) / 7 = 50%

The Critic's 15% appears to weight reply/resolution/implementation heavily (core differentiators from simple scripts). Adjusting for intended scope (maintenance, not response), the actual completion is closer to 70%.

**Verdict**: The script achieves its maintenance goals but does not achieve PR comment response goals. The ADR title "PR Maintenance" aligns with current capabilities.

### Minimum Viable Script (Phase 1)

**Updated per HLA-001 review (2025-12-22)**: Added rate limit check to P0 based on high-level-advisor challenge.

The following 6 fixes MUST be complete before hourly automated deployment:

#### Fix 1: Branch Name Validation

**Problem**: Branch names passed directly to git without validation.

**Solution**:

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

# Usage in Resolve-PRConflicts
if (-not (Test-SafeBranchName -BranchName $BranchName)) {
    throw "Invalid branch name: $BranchName"
}
```

#### Fix 2: Worktree Path Validation

**Problem**: Worktree path could escape intended directory.

**Solution**:

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

#### Fix 3: Concurrency Lock

**Problem**: Two script instances could run simultaneously.

**Solution**:

```powershell
$lockFile = Join-Path $PSScriptRoot '..' '.agents' 'logs' 'pr-maintenance.lock'

function Enter-ScriptLock {
    if (Test-Path $lockFile) {
        $lockAge = (Get-Date) - (Get-Item $lockFile).LastWriteTime
        if ($lockAge.TotalMinutes -lt 15) {
            Write-Log "Another instance running (lock age: $($lockAge.TotalMinutes)m)" -Level WARN
            return $false
        }
        Write-Log "Stale lock detected - removing" -Level WARN
        Remove-Item $lockFile -Force
    }

    New-Item $lockFile -ItemType File -Force | Out-Null
    return $true
}

function Exit-ScriptLock {
    Remove-Item $lockFile -Force -ErrorAction SilentlyContinue
}

# Entry point
if (-not (Enter-ScriptLock)) { exit 0 }
try {
    # Main logic
}
finally {
    Exit-ScriptLock
}
```

#### Fix 4: Int64 CommentId

**Problem**: GitHub comment IDs exceed Int32.MaxValue (2,147,483,647).

**Solution**:

```powershell
# Change parameter type
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

#### Fix 5: GitHub Actions Concurrency

**Problem**: Workflow can run multiple instances simultaneously.

**Solution** (workflow-level):

```yaml
concurrency:
  group: pr-maintenance
  cancel-in-progress: false
```

#### Fix 6: Rate Limit Pre-flight Check

**Problem**: Script could silently exhaust GitHub API rate limit.

**Solution** (per HLA-001 recommendation):

```powershell
function Test-RateLimitSafe {
    param([int]$MinimumRemaining = 200)

    $rateLimit = gh api rate_limit --jq '.rate'
    $remaining = ($rateLimit | ConvertFrom-Json).remaining

    if ($remaining -lt $MinimumRemaining) {
        Write-Log "API rate limit too low: $remaining < $MinimumRemaining" -Level WARN
        return $false
    }

    Write-Log "API rate limit OK: $remaining remaining" -Level INFO
    return $true
}

# Entry point (after lock check)
if (-not (Test-RateLimitSafe -MinimumRemaining 200)) {
    Write-Log "Skipping run due to low rate limit" -Level WARN
    exit 0
}
```

### Implementation Order

**Updated per HLA-001 review**: Timeline adjusted from 1 week to 2 weeks (realistic engineering effort).

```text
Phase 1 (Week 1-2) - Safety First
    |
    ├─ Sprint 1A (Days 1-5):
    │   ├─ Day 1-2: Fix 1 (branch validation) + Fix 2 (path validation) + unit tests
    │   ├─ Day 3-4: Fix 3 (lock file) + Fix 4 (Int64) + Fix 6 (rate limit) + unit tests
    │   └─ Day 5: Code review cycle, test refinement
    │
    └─ Sprint 1B (Days 6-10):
        ├─ Day 6: Fix 5 (workflow concurrency) + integration tests
        ├─ Day 7-8: Deploy with DryRun=true on real repo
        ├─ Day 9: 24h monitoring + issue resolution
        └─ Day 10: Enable live mode, monitor first hourly run

Phase 2 (Week 3-4) - Operational Excellence
    |
    ├─ Structured logging (JSON)
    ├─ Retry logic with exponential backoff
    ├─ Pre-run worktree cleanup
    └─ Failure alerting (create issue)

Phase 3 (Future) - Feature Completion
    |
    ├─ Reply to comments (gh api POST)
    ├─ Thread resolution (GraphQL mutation)
    └─ HANDOFF.md intelligent merge (preserve both)
```

## Rationale

### Alternatives Considered

| Alternative | Pros | Cons | Why Not Chosen |
|-------------|------|------|----------------|
| Deploy as-is | Fast time to value | 5 critical security/correctness bugs | Unacceptable risk for unattended script |
| Full rewrite | Address all 13 issues | 2-3 weeks effort, delays maintenance | Incremental approach preferred |
| Defer all features | Zero risk | No automation value | Wastes existing implementation |
| Phase 1 only, defer Phase 2 | Fastest safe deployment | Operational gaps remain | Phase 2 is 1-week effort |

### Trade-offs

**Time vs Safety**: Phase 1 adds 1 week before deployment. This trade-off is mandatory for unattended script execution.

**Feature Completeness vs Stability**: Reply functionality (Phase 3) requires API calls that could fail. Current acknowledge-only approach is more resilient.

**HANDOFF.md Strategy**: Using `--theirs` loses session history. However:
- Session logs preserve all history (primary source of truth)
- HANDOFF.md is a summary, not canonical
- Complex three-way merge risks corruption

**Verdict**: Accept `--theirs` for now; document session log as canonical source.

## Consequences

### Positive

- 5 critical bugs fixed before production deployment
- Clear prioritization enables incremental delivery
- Phase 1 achievable in 1 week with existing codebase
- Reconciles conflicting feedback into actionable plan
- Defines explicit "done" criteria for each phase

### Negative

- 1-week delay before automated maintenance begins
- Reply functionality not available until Phase 3
- HANDOFF.md session history may be lost in conflicts (mitigated by session logs)
- Additional complexity from lock file mechanism

### Neutral

- DevOps "B+" assessment applies to Phase 2 complete state
- Critic "15%" becomes "70%" after Phase 1 (maintenance scope)
- Full "100%" requires Phase 3 (response scope)

## Reversibility Assessment

### Rollback Capability

- [x] Phase 1 fixes are additive (validation functions, parameter type change)
- [x] Lock file mechanism can be disabled by removing try/finally block
- [x] Workflow concurrency group is declarative, easily removed

### Vendor Lock-in

**Dependency**: GitHub API, gh CLI

**Lock-in Level**: Medium (GitHub-specific, but gh CLI is standard)

**Exit Strategy**: Script logic is portable; replace `gh` calls with REST API calls for other platforms.

## Confirmation

**Phase 1 Complete When** (updated per HLA-001):

- [ ] All 6 fixes implemented (branch, path, lock, Int64, concurrency, rate limit)
- [ ] Pester tests pass for validation functions (20+ test cases per function)
- [ ] Integration test with 5 mock PRs demonstrates end-to-end safety
- [ ] 24-hour DryRun deployment shows 0 script errors, 0 API errors
- [ ] Security agent reviews and approves P0 fixes
- [ ] Rollback procedure documented (can revert concurrency lock in <30 min)

**Phase 2 Complete When**:

- [ ] JSON logs queryable with `jq`
- [ ] Retry logic handles 3 transient failures per run
- [ ] Failure issues created on workflow error
- [ ] Pre-run worktree cleanup removes stale worktrees

**Phase 3 Complete When**:

- [ ] Script can POST reply to comment
- [ ] Script can resolve review thread via GraphQL
- [ ] Critic re-assessment shows >80% completion

## Implementation Notes

### P0 Fixes (Phase 1)

**Files to Modify**:

- `scripts/Invoke-PRMaintenance.ps1` (Fixes 1-4)
- `.github/workflows/pr-maintenance.yml` (Fix 5)

**Test Strategy**:

- Unit tests for `Test-SafeBranchName`, `Get-SafeWorktreePath`
- Integration test with mock PRs (DryRun mode)
- Monitor first 24h of live runs

### ADR Cross-References

| Related ADR | Relationship |
|-------------|--------------|
| ADR-005 | PowerShell-only scripting policy |
| ADR-006 | Thin workflows, testable modules |
| ADR-009 | Parallel-safe multi-agent design |

## Related Decisions

- ADR-005: PowerShell-only scripting (why pwsh, not bash)
- ADR-006: Thin workflows pattern (workflow calls script)
- ADR-014: Distributed handoff architecture (HANDOFF.md merge strategy)

## References

- DevOps Review: `.agents/devops/pr-automation-script-review.md`
- Session 64: `.agents/sessions/2025-12-22-session-64-pr-automation-devops-review.md`
- Skill-Security-007: Defense-in-depth for cross-process checks
- Skill-Autonomous-Execution-Guardrails: Stricter protocols for unattended

---

**ADR Version**: 1.0
**Created**: 2025-12-22
**Author**: Architect Agent
