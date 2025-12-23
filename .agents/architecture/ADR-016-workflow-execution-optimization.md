# ADR-016: Workflow Execution Optimization Strategy

## Status

Accepted

## Date

2025-12-22

## Context

GitHub Actions costs are driven by workflow execution minutes. Analysis revealed two optimization opportunities:

1. **Unnecessary executions**: Workflows running on irrelevant file changes (e.g., AI triage running on every push regardless of content)
2. **Duplicate runs**: Multiple concurrent workflow runs for the same PR (e.g., rapid-fire commits triggering overlapping runs)

Current state:
- **6 workflows lack path filters**: Running on all push/PR events
- **4 workflows lack concurrency control**: Allowing duplicate runs
- **Estimated waste**: 20-30% of workflow minutes spent on irrelevant changes or duplicate runs

## Decision

Implement two complementary optimizations:

1. **Path filters**: Restrict workflow triggers to relevant file changes
2. **Concurrency groups**: Cancel in-progress runs when new commits arrive

## Rationale

### Path Filter Strategy

**Principle**: Workflows only run when files they analyze are changed.

| Workflow | Files Analyzed | Path Filter |
|----------|---------------|-------------|
| agent-metrics | Metrics scripts | `.agents/utilities/metrics/**` |
| copilot-setup-steps | Git hooks | `.githooks/**` |
| drift-detection | Agent files, templates | `src/claude/**`, `templates/agents/**` |
| pester-tests | PowerShell scripts | `scripts/**`, `build/**`, `.claude/skills/**` |

**Already filtered** (no change):
- ai-session-protocol, ai-spec-validation, validate-generated-agents, validate-planning-artifacts

**Issue-triggered** (no path filters needed):
- ai-issue-triage, copilot-context-synthesis, label-issues

**PR-triggered with internal path filtering** (no top-level filters):
- ai-pr-quality-gate (uses dorny/paths-filter internally)
- label-pr (applies to all PRs by design)

### Concurrency Group Strategy

**Principle**: One active run per branch/PR. New commits cancel previous runs.

| Workflow | Concurrency Group | Cancel In Progress |
|----------|------------------|-------------------|
| agent-metrics | `agent-metrics-${{ github.ref }}` | ✅ Yes |
| ai-issue-triage | `issue-triage-${{ issue }}` | ❌ No (per-issue) |
| ai-pr-quality-gate | `ai-quality-${{ pr }}` | ✅ Yes |
| ai-session-protocol | `session-protocol-${{ pr }}` | ✅ Yes |
| copilot-context-synthesis | `copilot-synthesis-${{ issue }}` | ❌ No (per-issue) |
| copilot-setup-steps | `copilot-setup-${{ github.ref }}` | ✅ Yes |
| drift-detection | `drift-detection-${{ github.ref }}` | ✅ Yes |
| pester-tests | `pester-tests-${{ github.ref }}` | ✅ Yes |
| validate-generated-agents | `validate-agents-${{ github.ref }}` | ✅ Yes |
| validate-paths | `validate-paths-${{ github.ref }}` | ✅ Yes |
| validate-planning-artifacts | `validate-planning-${{ github.ref }}` | ✅ Yes |

**Issue-based workflows**: `cancel-in-progress: false` to avoid race conditions
**Branch/PR workflows**: `cancel-in-progress: true` to eliminate redundant runs

### Alternatives Considered

| Alternative | Pros | Cons | Why Not Chosen |
|-------------|------|------|----------------|
| No path filters | Simplicity, no false negatives | Wastes 20-30% of runs | Cost constraint makes this unviable |
| Global path ignore | Easy to configure | Too coarse-grained | Need workflow-specific filters |
| No concurrency control | Parallel feedback | Duplicate runs waste resources | Cancel-in-progress is safe for most workflows |
| queue (no cancel) | Preserve all runs | Slow feedback for rapid commits | Cancel is better for PR workflows |

### Cost Impact

**Estimated savings**:
- Path filters: 20% reduction in unnecessary runs
- Concurrency groups: 10% reduction from duplicate runs
- **Combined**: ~30% reduction in workflow minutes

**Annual savings**: $300-500 (based on $1,000-1,500 remaining budget after ARM migration)

### Trade-offs

**Path Filters**:
- **Pro**: Significant cost savings, faster feedback (skip irrelevant runs)
- **Con**: Risk of false negatives (workflow not running when it should)
- **Mitigation**: Conservative filters (include related paths), manual trigger available

**Concurrency Groups**:
- **Pro**: Eliminates redundant work, faster PR feedback
- **Con**: May cancel long-running tests mid-execution
- **Mitigation**: Per-issue workflows use `cancel-in-progress: false`

## Consequences

### Positive

- **30% reduction in workflow execution costs**
- **Faster PR feedback**: No wasted time on irrelevant runs
- **Reduced queue wait time**: Fewer concurrent runs competing for runners
- **Better developer experience**: More relevant workflow results

### Negative

- **Potential false negatives**: Path filters may miss indirect dependencies
- **Cancelled long-running tests**: Concurrency groups may waste partial work
- **Increased complexity**: Path patterns require maintenance

### Neutral

- **Manual trigger preserved**: workflow_dispatch allows overriding path filters
- **Issue workflows unchanged**: Concurrency behavior already optimal
- **No impact on workflow logic**: Only trigger conditions changed

## Implementation Notes

### Path Filters Added

1. **agent-metrics.yml**:
   ```yaml
   on:
     push:
       paths:
         - '.agents/utilities/metrics/**'
         - '.github/workflows/agent-metrics.yml'
   ```

2. **copilot-setup-steps.yml**:
   ```yaml
   on:
     push:
       paths:
         - '.githooks/**'
         - '.github/workflows/copilot-setup-steps.yml'
   ```

3. **drift-detection.yml**:
   ```yaml
   on:
     push:
       paths:
         - 'src/claude/**'
         - 'templates/agents/**'
         - 'build/scripts/Detect-AgentDrift.ps1'
         - '.github/workflows/drift-detection.yml'
   ```

4. **pester-tests.yml**:
   ```yaml
   on:
     push:
       paths:
         - 'scripts/**'
         - 'build/**'
         - '.github/scripts/**'
         - '.claude/skills/**'
         - 'tests/**'
         - '.github/workflows/pester-tests.yml'
   ```

### Concurrency Groups Added

All workflows now have concurrency groups:
```yaml
concurrency:
  group: <workflow>-${{ github.ref || github.event.issue.number }}
  cancel-in-progress: true  # false for issue-based workflows
```

### Monitoring

1. **Track false negatives**: Monitor for cases where workflows should run but don't
2. **Measure cost savings**: Compare workflow minutes before/after implementation
3. **Developer feedback**: Survey team on PR feedback latency

### Rollback Plan

If path filters cause issues:
1. Remove `paths` filter from specific workflow
2. Document why filter was removed
3. Consider alternative filtering strategy (e.g., internal skip logic)

## Related Decisions

- ADR-014: GitHub Actions ARM Runner Migration
- ADR-015: Artifact Storage Minimization Strategy
- ADR-006: Thin Workflows, Testable Modules (related to workflow design)

## References

- [GitHub Actions: Workflow triggers](https://docs.github.com/en/actions/using-workflows/events-that-trigger-workflows)
- [GitHub Actions: Path filters](https://docs.github.com/en/actions/using-workflows/workflow-syntax-for-github-actions#onpushpull_requestpull_request_targetpathspaths-ignore)
- [GitHub Actions: Concurrency](https://docs.github.com/en/actions/using-workflows/workflow-syntax-for-github-actions#concurrency)
- Issue: #[issue-number] - GitHub Actions cost audit and optimization

---

*Template Version: 1.0*
*Created: 2025-12-22*
*GitHub Issue: Cost optimization initiative*
