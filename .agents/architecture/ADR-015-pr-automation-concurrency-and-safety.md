# ADR-015: PR Automation Concurrency and Safety Controls

## Status

Accepted

## Context

The PR maintenance automation script (`scripts/Invoke-PRMaintenance.ps1`) requires architectural decisions about:

1. **Concurrency Control**: How to prevent multiple script instances from interfering
2. **Rate Limiting Strategy**: How to avoid GitHub API exhaustion  
3. **Input Validation**: What security controls are required for git operations
4. **Deployment Safety**: What controls ensure safe hourly automated execution

Five agents reviewed the initial implementation and identified critical issues requiring architectural decisions.

## Decision

### Decision 1: Workflow-Level Concurrency Control

**Decision**: Use GitHub Actions `concurrency` group instead of file-based locking.

**Rationale**:
- GitHub Actions runners are ephemeral (no persistent filesystem between runs)
- Workflow-level concurrency is the native GitHub Actions pattern (ADR-006: thin workflows)
- File-based locks add complexity without benefit on ephemeral infrastructure

**Implementation**:
```yaml
concurrency:
  group: pr-maintenance
  cancel-in-progress: false  # Queue runs, don't cancel
```

**Rejected Alternative**: File-based mutex lock
- **Why rejected**: Unnecessary on ephemeral GitHub Actions runners; only relevant for persistent VMs

### Decision 2: Multi-Resource Rate Limiting

**Decision**: Check ALL GitHub API resource types with resource-specific thresholds.

**Rationale**:
- GitHub API has multiple rate limit buckets (core, search, graphql, etc.)
- Some resources have very low limits (search: 30, code_scanning_autofix: 10)
- Checking only `.rate.remaining` (core API) ignores critical low-limit resources

**Implementation**:
```powershell
function Test-RateLimitSafe {
    $resources = gh api rate_limit | ConvertFrom-Json
    
    # Resource-specific minimum thresholds (50% of limit)
    $thresholds = @{
        'search' = 15
        'code_scanning_autofix' = 5
        'audit_log_streaming' = 7
        'code_search' = 5
        'core' = 100
    }
    
    foreach ($resource in $thresholds.Keys) {
        $remaining = $resources.resources.$resource.remaining
        if ($remaining -lt $thresholds[$resource]) {
            return $false
        }
    }
    return $true
}
```

**Rejected Alternative**: Single threshold check on core API
- **Why rejected**: Ignores resources with limits as low as 10-30 requests/hour

### Decision 3: Input Validation for Git Operations

**Decision**: Validate branch names and worktree paths before passing to git commands.

**Rationale**:
- Branch names from GitHub API are untrusted input
- Without validation: command injection via branch names like `main; rm -rf /`
- Path traversal risk if PR numbers manipulated to escape worktree directory

**Implementation**:
```powershell
function Test-SafeBranchName {
    param([string]$BranchName)
    
    if ([string]::IsNullOrWhiteSpace($BranchName)) { return $false }
    if ($BranchName.StartsWith('-')) { return $false }
    if ($BranchName.Contains('..')) { return $false }
    if ($BranchName -match '[\x00-\x1f\x7f]') { return $false }
    if ($BranchName -match '[~^:?*\[\]\\]') { return $false }
    
    return $true
}
```

**Rejected Alternative**: Trust GitHub API data
- **Why rejected**: Defense-in-depth principle; API could be compromised or MitM attacked

### Decision 4: DryRun-First Deployment

**Decision**: Default `DryRun=true` for initial production deployment.

**Rationale**:
- Allows monitoring automation behavior without risk
- Gather metrics on API usage, runtime, error rates
- Validate logic against real PRs before enabling writes

**Implementation**: Change workflow default from `false` to `true`

**Rejected Alternative**: Deploy live immediately
- **Why rejected**: Automation bugs could close valid PRs or corrupt data; reversible after confidence established

**Update (2024-12-24)**: Dry run flag removed entirely after successful validation period.
- **Reason**: Bug in dry run flag parsing caused scheduled runs to incorrectly operate in dry run mode (empty string evaluated as true)
- **Solution**: Simplified by removing the flag - workflow now always performs actual operations
- **Impact**: Net reduction of 76 lines of code, simpler maintainability
- **Commit**: ed4e3db "Remove dry run flag from PR maintenance workflow"

### Decision 5: BOT_PAT for Attribution

**Decision**: Use `BOT_PAT` secret instead of `github.token` for workflow authentication.

**Rationale**:
- Ensures actions are attributed to `rjmurillo-bot` service account
- Clearer audit trail (bot actions vs. GitHub Actions runner)
- Follows existing repository pattern for automated operations

**Implementation**: Change all `GH_TOKEN: ${{ github.token }}` to `GH_TOKEN: ${{ secrets.BOT_PAT }}`

**Rejected Alternative**: Use github.token
- **Why rejected**: Poor attribution; actions appear to come from GitHub Actions runner, not identifiable bot

## Consequences

### Positive

- Workflow-level concurrency simpler and native to GitHub Actions
- Multi-resource rate limiting prevents silent failures on low-limit resources
- Input validation prevents command injection and path traversal
- DryRun-first enables safe production validation
- BOT_PAT improves attribution and audit trail

### Negative

- Multi-resource rate limiting adds complexity (must track multiple thresholds)
- DryRun-first delays live automation by 1-2 weeks
- Requires BOT_PAT secret configuration in repository

### Risks

**Risk 1**: Rate limit thresholds too conservative
- **Mitigation**: Start with 50% of each resource limit; tune based on actual usage

**Risk 2**: Input validation too strict (rejects valid branch names)
- **Mitigation**: Test against historical PR branch names; expand regex if needed

## Related ADRs

- [ADR-005](ADR-005-powershell-only-scripting.md): PowerShell-only scripting
- [ADR-006](ADR-006-thin-workflows-testable-modules.md): Thin workflows, testable modules
- [ADR-009](ADR-009-parallel-safe-multi-agent-design.md): Parallel-safe multi-agent design

## References

- Security Analysis: [`.agents/security/SR-002-pr-automation-security-review.md`](../security/SR-002-pr-automation-security-review.md)
- Implementation Plan: [`.agents/planning/pr-automation-implementation-plan.md`](../planning/pr-automation-implementation-plan.md)
- DevOps Review: [`.agents/devops/pr-automation-script-review.md`](../devops/pr-automation-script-review.md)
