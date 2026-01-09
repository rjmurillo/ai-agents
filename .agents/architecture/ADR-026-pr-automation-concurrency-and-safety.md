# ADR-026: PR Automation Concurrency and Safety Controls

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
# Per-PR concurrency with cancellation for best-effort coalescing
concurrency:
    group: pr-maintenance-${{ github.event.pull_request.number || inputs.pr_number }}
    cancel-in-progress: true
```

Note: For non-PR runs, ensure the concurrency group resolves to a stable value. Constrain triggers to PRs or require a manual `pr_number` input (or provide a documented default fallback string) to avoid accidental cross-run grouping.

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

## Coalescing Behavior and Race Conditions

### Platform Limitation

GitHub Actions `concurrency` groups with `cancel-in-progress: true` provide **best-effort** run coalescing, not guaranteed atomicity. Race conditions can occur where multiple runs start before cancellation takes effect.

### Observed Behavior

- **Typical coalescing rate**: 90-95% effective
- **Race condition window**: 1-5 seconds between trigger and cancellation
- **Impact**: 5-10% of runs may execute in parallel despite concurrency control

### Mitigation in This Repository

1. **Path filtering** (dorny/paths-filter): Reduces unnecessary runs by 60-80%
2. **PR-specific temp files**: Prevents context collision between concurrent runs
3. **Explicit repo context**: `--repo` flag on all `gh` CLI commands prevents wrong-PR analysis
4. **Timeouts**: Caps maximum cost per run (2-15 minutes depending on workflow)

### Decision Rationale

We accept the "no guarantee" limitation because:

1. **Cost is acceptable**: 5-10% duplicate run rate with ARM runners (37.5% cost savings)
2. **Alternative is worse**: File-based locking doesn't work on ephemeral GitHub Actions runners
3. **Mitigation is effective**: Path filtering + PR-specific files reduce impact to negligible levels
4. **Platform is improving**: GitHub Actions continuously improves concurrency control

### When to Revisit

Revisit this decision if:

- Duplicate run rate exceeds 20% consistently
- Wrong-PR analysis occurs despite mitigation (indicates platform regression)
- GitHub Actions introduces guaranteed atomicity primitives
- Cost of duplicate runs becomes material (>5% of CI budget)

## Optional Debouncing Mechanism

### Decision

Debouncing is available as an opt-in feature via `enable_debouncing` workflow input (default: false), and via repository/workflow variable `vars.ENABLE_DEBOUNCE` for PR-triggered runs.

### Rationale

- Adds 10s latency to every run when enabled
- Reduces race condition probability by extending cancellation window
- Should only be enabled when monitoring data shows persistent race conditions
- Preserves fast feedback loop for majority of runs

### When to Enable

Enable debouncing when:

- Race condition rate consistently exceeds 10%
- Coalescing effectiveness drops below 90%
- Cost of duplicate runs becomes material (>5% of CI budget)
- Specific workflows show persistent overlap patterns

### Implementation

Debouncing is implemented as a reusable composite action (`.github/actions/workflow-debounce/action.yml`) and guarded at the job level:

- Configurable delay (default: 10 seconds)
- Runs before main workflow logic
- Provides cancellation window for GitHub Actions
- Logs metrics for observability
- Conditional job execution allows enabling via either manual inputs or repository variable for PR runs
- Downstream jobs must explicitly await the debounce job under a safe guard

Note: Declare the manual toggle as a typed boolean input to ensure consistent evaluation:

```yaml
on:
    workflow_dispatch:
        inputs:
            enable_debouncing:
                description: "Enable debounce delay"
                type: boolean
                default: false
```

```yaml
# Concurrency (see Decision 1)
concurrency:
    group: pr-maintenance-${{ github.event.pull_request.number || inputs.pr_number }}
    cancel-in-progress: true

jobs:
    debounce:
        if: >-
            (github.event_name == 'workflow_dispatch' && inputs.enable_debouncing == true)
            || (github.event_name == 'pull_request' && vars.ENABLE_DEBOUNCE == 'true')
        steps:
            - uses: ./.github/actions/workflow-debounce
                with:
                    delay-seconds: '10'
                    workflow-name: 'PR Maintenance'
                    concurrency-group: ${{ github.event.pull_request.number || inputs.pr_number }}

    check-paths:
        needs: debounce
        if: >-
            always() &&
            (needs.debounce.result == 'success' || needs.debounce.result == 'skipped')
        runs-on: ubuntu-latest
        steps:
            - uses: dorny/paths-filter@v3
                with:
                    filters: |
                        src:
                            - 'src/**'

# Guard rationale: The `always()` + `needs.debounce.result` check prevents short-circuiting
# when debounce is disabled or skipped, while still honoring failures if the debounce job ran and failed.
```

### Tradeoffs

| Aspect | Without Debouncing | With Debouncing |
|--------|-------------------|------------------|
| Latency | 0s overhead | +10s per run |
| Race condition probability | 5-10% | 2-5% (estimated) |
| Coalescing effectiveness | 90-95% | 95-98% (estimated) |
| Complexity | Simple | Moderate |
| Cost impact | Baseline | +10s × run frequency |

### Monitoring

Use `Measure-WorkflowCoalescing.ps1` to track:

- Race condition rate before/after enabling debouncing
- Coalescing effectiveness improvement
- Average cancellation time
- Cost impact (additional runner minutes)

### Recommendation

**Default**: Keep debouncing disabled for fast feedback loop

**Enable when**: Monitoring shows persistent race conditions (>10% rate) that impact workflow reliability or cost

## Related ADRs

- [ADR-005](ADR-005-powershell-only-scripting.md): PowerShell-only scripting
- [ADR-006](ADR-006-thin-workflows-testable-modules.md): Thin workflows, testable modules
- [ADR-009](ADR-009-parallel-safe-multi-agent-design.md): Parallel-safe multi-agent design

## References

- Security Analysis: [`.agents/security/SR-002-pr-automation-security-review.md`](../security/SR-002-pr-automation-security-review.md)
- Implementation Plan: [`.agents/planning/pr-automation-implementation-plan.md`](../planning/pr-automation-implementation-plan.md)
- DevOps Review: [`.agents/devops/pr-automation-script-review.md`](../devops/pr-automation-script-review.md)
