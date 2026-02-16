# Claude Code PowerShell Performance Strategy

**Created**: 2025-12-23
**Session**: 80
**Source**: `.agents/analysis/claude-pwsh-performance-strategic.md`

## Problem Summary

Claude Code's Bash tool spawns a new pwsh process for each command:
- Without -NoProfile: 1,044ms per call
- With -NoProfile: 183ms per call (82.4% faster, but still significant)
- PR #285 implemented -NoProfile (done)
- Issue #283 batching papers over the problem

## Root Cause

- Claude Code Bash tool is stateless by design (security feature)
- PowerShell has no native "server mode"
- Engine initialization overhead is unavoidable per-spawn
- No solution exists within current architecture

## Solution Hierarchy (Priority Order)

### 1. gh CLI Rewrite (Do First)
- **Impact**: 50-70% latency reduction
- **Effort**: Low (1-2 weeks)
- **Approach**: Replace simple PowerShell skills with direct `gh` calls
- **Target skills**: Get-PRContext, Set-IssueLabels, Set-IssueMilestone, Post-IssueComment

### 2. Hybrid Approach (Target Architecture)
- **Impact**: 70-90% latency reduction
- **Effort**: Medium (3-4 weeks)
- **Approach**: Route simple ops to `gh`, complex ops to pwsh daemon

### 3. Named Pipe Daemon (Phase 2)
- **Impact**: 80-95% latency reduction
- **Effort**: Medium (2-3 weeks)
- **Approach**: Persistent pwsh process accepting commands via named pipe

### 4. PowerShell MCP Server (Long-term)
- **Impact**: 95-99% latency reduction
- **Effort**: Very High (4-8 weeks)
- **Approach**: Build MCP server exposing skills as MCP tools
- **Blocker**: No PowerShell MCP SDK exists

## Skills Classification

### Can Use gh CLI Directly
- Get-PRContext -> `gh pr view --json`
- Set-IssueLabels -> `gh issue edit --add-label`
- Set-IssueMilestone -> `gh issue edit --milestone`
- Post-IssueComment -> `gh issue comment`
- Close-PR -> `gh pr close`
- New-Issue -> `gh issue create`

### Require PowerShell (GraphQL/Complex Logic)
- Resolve-PRReviewThread (GraphQL mutation)
- Get-PRReviewComments (pagination + processing)
- Add-CommentReaction (REST API only)

## Security Considerations

| Risk | Severity | Mitigation |
|------|----------|------------|
| State leakage (daemon) | Medium | Clear runspace between calls |
| IPC injection | Medium | Strict command validation |
| Credential caching | Low | gh CLI handles auth |

## Immediate Next Step

Benchmark `gh pr view --json` vs Get-PRContext.ps1 to validate expected 50-70% improvement.

## Related

- Skill-Perf-001 in skills-powershell memory (-NoProfile optimization)
- Issue #283 (batching approach)
- PR #285 (-NoProfile implementation)

## Related

- [claude-code-hooks-opportunity-analysis](claude-code-hooks-opportunity-analysis.md)
- [claude-code-skill-frontmatter-standards](claude-code-skill-frontmatter-standards.md)
- [claude-code-skills-official-guidance](claude-code-skills-official-guidance.md)
- [claude-code-slash-commands](claude-code-slash-commands.md)
- [claude-flow-research-2025-12-20](claude-flow-research-2025-12-20.md)
