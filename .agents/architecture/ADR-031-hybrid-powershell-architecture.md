# ADR-031: Hybrid PowerShell Architecture for Claude Code Performance

## Status

Proposed

## Date

2025-12-29

## Context

Claude Code suffers from systemic performance issues when invoking PowerShell skills. Each Bash tool call spawns a new `pwsh` process, incurring significant overhead even with `-NoProfile`. User perception is that operations "seem to take FOREVER" due to cumulative spawn overhead.

### Root Cause: Process Spawn Overhead

**Measured performance (2025-12-23):**

| Component | Time (ms) | % of Total |
|-----------|-----------|------------|
| Process creation | 50-100 | 12-24% |
| PowerShell engine init | 100-150 | 24-36% |
| Module discovery | 50-100 | 12-24% |
| Script execution | Variable | N/A |
| Total spawn overhead | 183-416 | ~400ms avg |

**Impact on real-world operations:**

| Session Type | Typical pwsh Calls | Overhead With -NoProfile |
|--------------|-------------------|--------------------------|
| Simple PR review | 3-5 | 0.5-2s |
| Complex PR (20 calls) | 20-25 | 4-10s |
| Multi-PR triage | 50+ | 10-20s |

### Architectural Constraints

- Claude Code's Bash tool is stateless by design (security feature)
- PowerShell designed for long-running sessions, not frequent spawns
- Project constraint (ADR-005): PowerShell is the primary scripting language
- No native support for persistent sessions in Claude Code

## Decision

Implement a **hybrid architecture** for PowerShell skill execution:

1. **Strategy 1: Direct gh CLI** - Convert simple wrapper skills to direct `gh` CLI calls
2. **Strategy 2: Named Pipe Daemon** - Use persistent PowerShell process for complex operations

### Routing Decision Tree

```text
Is the operation a simple wrapper around gh CLI?
├─ YES → Use direct gh CLI call
│         Expected latency: 50ms + API time
│         Examples: Get-PRContext, Set-IssueLabels
│
└─ NO → Use named pipe daemon
          Expected latency: 10-50ms + execution time
          Examples: GraphQL queries, complex pagination
```

### Classification of Current Skills

| Skill | Strategy | Rationale |
|-------|----------|-----------|
| Get-PRContext | gh CLI | Simple `gh pr view --json` |
| Set-IssueLabels | gh CLI | Simple `gh issue edit --add-label` |
| Set-IssueMilestone | gh CLI | Simple `gh issue edit --milestone` |
| Post-IssueComment | gh CLI | Simple `gh issue comment` |
| Get-PRReviewComments | Daemon | GraphQL needed for threads |
| Resolve-PRReviewThread | Daemon | GraphQL mutation required |
| Add-CommentReaction | Daemon | REST API only |
| Test-WorkflowRateLimit | Daemon | Complex multi-resource check |

## Rationale

### Alternatives Considered

| Alternative | Pros | Cons | Why Not Chosen |
|-------------|------|------|----------------|
| Batch all calls into single script | 50-60% improvement, simple | Limited improvement, script complexity | Insufficient performance gain |
| PowerShell MCP Server | 95-99% improvement, native integration | No PowerShell MCP SDK, significant dev effort | Too complex for current needs |
| Runspace pool | 70-85% improvement, standard PowerShell | Violates pure-PowerShell preference, complex | Adds infrastructure complexity |
| Rewrite everything in bash | 90%+ improvement | Violates ADR-005, loses testing infrastructure | Project constraints |
| Do nothing | No effort | Poor UX, 8-20s PR reviews | Unacceptable user experience |

### Trade-offs

**Accepted trade-offs:**

- Two code paths to maintain (gh CLI + daemon)
- Routing complexity (decision tree logic)
- Daemon lifecycle management overhead

**Rejected trade-offs:**

- Rewriting all skills in bash (loses PowerShell testing infrastructure)
- Full MCP server (excessive complexity for current scale)

## Consequences

### Positive

- 70-90% latency reduction for simple operations
- 80-95% latency reduction for complex operations (after daemon warm-up)
- Incremental migration path (can convert skills one at a time)
- Backward compatibility (PowerShell skills continue to work)
- No changes required to Claude Code itself

### Negative

- Two code paths to maintain (gh CLI and PowerShell)
- Routing decision complexity
- Daemon requires lifecycle management
- Potential state leakage in daemon (mitigated by isolation)

### Neutral

- gh CLI skills lose PowerShell Pester testing (use bash testing instead)
- Documentation overhead for routing decisions

## Implementation Notes

### Phase 1: gh CLI Migration (Weeks 1-2)

1. Identify simple wrapper skills (see classification table)
2. Rewrite each as direct gh CLI call
3. Validate with existing test cases
4. Document migration in skill comments

### Phase 2: Named Pipe Daemon (Weeks 3-4)

1. Implement daemon with named pipe IPC
2. Add startup/shutdown management
3. Implement error recovery
4. Integrate with complex skills

### Performance Targets

| Operation Type | Current | Target | Improvement |
|----------------|---------|--------|-------------|
| Simple gh CLI | 400ms | 50ms | 87% |
| Complex daemon | 400ms | 10-50ms | 75-97% |
| PR review (10 ops) | 8s | 1s | 87% |

### Routing Implementation

```yaml
# Routing configuration
gh_cli_operations:
  - Get-PRContext: gh pr view --json number,title,body,state,headRefName,baseRefName
  - Set-IssueLabels: gh issue edit --add-label
  - Set-IssueMilestone: gh issue edit --milestone
  - Post-IssueComment: gh issue comment

daemon_operations:
  - Get-PRReviewComments
  - Resolve-PRReviewThread
  - Add-CommentReaction
  - Test-WorkflowRateLimit
```

## Related Decisions

- ADR-005: PowerShell as primary scripting language
- ADR-006: Thin workflows, testable modules

## References

- Analysis: `.agents/analysis/claude-pwsh-performance-strategic.md`
- Benchmark data: Session 80 (2025-12-23)
- Parent issue: #284 (PowerShell performance optimization)
- Implementation: #286 (gh CLI rewrite), #287 (named pipe daemon)

---

*ADR Version: 1.0*
*Created: 2025-12-29*
*GitHub Issue: #288*
