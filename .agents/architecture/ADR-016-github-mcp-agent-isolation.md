---
status: proposed
date: 2025-12-23
decision-makers: User, Architect Agent
consulted: Analyst (Session 80), Independent-Thinker
informed: Implementer, DevOps, Orchestrator
---

# ADR-016: GitHub MCP Server with Agent Isolation Pattern

## Context and Problem Statement

Claude Code's interaction with GitHub currently uses PowerShell wrapper scripts that suffer from significant latency overhead. Each `pwsh` invocation from the Bash tool spawns a new process:

- **Without -NoProfile**: 1,044ms per call
- **With -NoProfile** (PR #285): 183ms per call

For PR review workflows that require 5-10 GitHub API calls, this adds 1-4 seconds of latency per interaction. The question is: what architecture best addresses this performance problem while maintaining code quality, security, and maintainability?

## Decision Drivers

1. **Performance**: Minimize latency for GitHub operations
2. **Context Efficiency**: Prevent tool explosion in main Claude Code context
3. **Maintainability**: Reduce custom code maintenance burden
4. **Security**: Maintain secure credential handling
5. **Platform Portability**: Support Windows, Linux, macOS
6. **ADR-005 Compliance**: Respect PowerShell-only scripting standard where appropriate
7. **Capability Coverage**: Support all current use cases (PRs, issues, reviews, reactions, labels)

## Considered Options

### Option A: PowerShell Wrappers (Current State)

**Description**: 20 PowerShell scripts in `.claude/skills/github/scripts/` called via `pwsh -NoProfile`.

**Performance**: 183-416ms per call (process spawn overhead)

**Capabilities**:

| Operation | Supported | Implementation |
|-----------|-----------|----------------|
| PR metadata | Yes | Get-PRContext.ps1 |
| PR review comments | Yes | Get-PRReviewComments.ps1 |
| Reply to review | Yes | Post-PRCommentReply.ps1 |
| Resolve thread | Yes | Resolve-PRReviewThread.ps1 (GraphQL) |
| Add reaction | Yes | Add-CommentReaction.ps1 |
| Labels | Yes | Set-IssueLabels.ps1 |
| Milestones | Yes | Set-IssueMilestone.ps1 |
| Issue operations | Yes | Get-IssueContext.ps1, etc. |
| GraphQL mutations | Yes | Direct gh api graphql calls |

**Pros**:
- Full capability coverage (100% of use cases)
- Tested and production-proven
- Follows ADR-005 PowerShell-only standard
- Type-safe object pipelines
- Structured error handling

**Cons**:
- 183-416ms latency per call (unavoidable spawn overhead)
- No native server mode in PowerShell
- 20 scripts to maintain

### Option B: gh CLI Rewrite (Issue #286)

**Description**: Replace PowerShell scripts with direct `gh` CLI calls from Bash.

**Performance**: 50-80ms per call (bash spawn, no PowerShell engine)

**Capabilities**:

| Operation | gh CLI Support | Notes |
|-----------|----------------|-------|
| PR metadata | Yes | `gh pr view --json` |
| PR review comments | Partial | `gh api graphql` required for threads |
| Reply to review | Partial | `gh api repos/.../comments` |
| Resolve thread | No | GraphQL only (no gh wrapper) |
| Add reaction | Yes | `gh api .../reactions -X POST` |
| Labels | Yes | `gh issue edit --add-label` |
| Milestones | Yes | `gh issue edit --milestone` |
| Issue operations | Yes | `gh issue view/create/edit` |
| GraphQL mutations | Yes | `gh api graphql -f query='...'` |

**Pros**:
- 50-70% latency reduction vs PowerShell
- Cross-platform (gh CLI available everywhere)
- No custom code for simple operations
- Single-line commands for common tasks

**Cons**:
- Violates ADR-005 PowerShell-only standard
- GraphQL operations require single-line formatting (Skill-GraphQL-001)
- Complex operations still need scripting
- Two languages to maintain (PowerShell for complex, bash for simple)

### Option C: PowerShell Named Pipe Daemon (Issue #287)

**Description**: Persistent PowerShell process accepting commands via named pipe IPC.

**Performance**: 10-50ms after warmup (no spawn overhead)

**Architecture**:

```text
Claude Code --> Named Pipe --> pwsh daemon --> GitHub API
                               (warm process)
```

**Pros**:
- 80-95% latency reduction
- Maintains PowerShell-only standard (ADR-005)
- Reuses existing script logic

**Cons**:
- High implementation complexity (daemon lifecycle, IPC, crash recovery)
- Security concerns (IPC injection, state leakage)
- Windows-specific named pipe semantics
- No existing MCP SDK for PowerShell
- Significant maintenance burden

### Option D: GitHub MCP Server + Agent Isolation (NEW)

**Description**: Use official GitHub MCP server (github/github-mcp-server) with agent-specific attachment following the superpowers-chrome isolation pattern.

**Performance**: 5-20ms per call (native MCP protocol, no process spawn)

**Architecture**:

```text
Main Claude Code Session
        |
        | (Task delegation)
        v
GitHub Agent (isolated context)
        |
        | (MCP protocol - stdio/SSE)
        v
GitHub MCP Server (40+ tools)
        |
        | (REST/GraphQL)
        v
GitHub API
```

**Agent Isolation Pattern** (from superpowers-chrome):

```yaml
name: github-agent
description: GitHub operations specialist
tools: [github-mcp-server tools]
model: sonnet
permissionMode: default
skills: github:operations
```

**Capabilities** (from github/github-mcp-server README):

| Operation | GitHub MCP Support | Tool Name |
|-----------|-------------------|-----------|
| PR metadata | Yes | pull_request_read (method: get) |
| PR diff | Yes | pull_request_read (method: get_diff) |
| PR files | Yes | pull_request_read (method: get_files) |
| PR review comments | Yes | pull_request_read (method: get_review_comments) |
| PR reviews | Yes | pull_request_read (method: get_reviews) |
| Reply to review | Yes | pull_request_review_write |
| Add review comment | Yes | add_comment_to_pending_review |
| Resolve thread | Unknown | May require GraphQL passthrough |
| Add reaction | Unknown | Not explicitly documented |
| Labels | Yes | label_write, get_label, list_label |
| Milestones | Partial | Via issue_write milestone parameter |
| Issue operations | Yes | issue_read, issue_write, list_issues |
| Issue comments | Yes | add_issue_comment |
| Sub-issues | Yes | sub_issue_write |
| Search | Yes | search_issues, search_pull_requests |
| Actions/Workflows | Yes | actions_get, actions_list, actions_run_trigger |
| Copilot integration | Yes | request_copilot_review, assign_copilot_to_issue |

**Pros**:
- 90-95% latency reduction (native MCP, no spawn)
- Official GitHub implementation (maintained by GitHub)
- 40+ tools covering most use cases
- Context isolation (tools only in GitHub agent)
- Cross-platform (MCP is universal)
- Zero custom script maintenance for covered operations

**Cons**:
- Capability gaps (reactions, thread resolution unclear)
- Requires agent isolation configuration (not yet standard in Claude Code)
- New architecture pattern to learn
- Dependency on external MCP server
- May require supplemental PowerShell for gaps

## Decision Outcome

**Chosen option: Phased Hybrid Approach with GitHub MCP as Target Architecture**

### Phase 1: gh CLI Quick Wins (1-2 weeks)

Replace simple PowerShell skills with direct `gh` CLI calls:

| Current Script | gh CLI Replacement |
|----------------|-------------------|
| Get-PRContext.ps1 | `gh pr view --json` |
| Set-IssueLabels.ps1 | `gh issue edit --add-label` |
| Set-IssueMilestone.ps1 | `gh issue edit --milestone` |
| Post-IssueComment.ps1 | `gh issue comment` |
| Close-PR.ps1 | `gh pr close` |
| New-Issue.ps1 | `gh issue create` |

**Expected Impact**: 50-70% latency reduction for these operations.

**ADR-005 Exception**: These specific operations are exempted from PowerShell-only requirement due to significant performance benefit and no loss of capability.

### Phase 2: GitHub MCP Prototype (2-4 weeks)

1. **Configure GitHub MCP server** in project MCP settings
2. **Create github-agent.md** with isolated tool binding
3. **Implement delegation pattern** from main session to GitHub agent
4. **Validate capability coverage** against current use cases
5. **Benchmark performance** vs PowerShell and gh CLI

### Phase 3: Full Migration (4-6 weeks, if prototype validates)

1. **Migrate remaining operations** to GitHub MCP
2. **Implement gap fillers** (PowerShell scripts for unsupported operations)
3. **Deprecate replaced scripts** with 30-day warning
4. **Update documentation** and agent prompts

### Consequences

**Positive**:
- 90-95% latency reduction for GitHub operations
- Reduced custom script maintenance (20 scripts to ~3-5 gap fillers)
- Context isolation prevents tool explosion
- Official GitHub support for core functionality
- Cross-platform without custom code

**Negative**:
- Capability gaps require supplemental implementation
- New architecture pattern increases complexity
- Dependency on external MCP server availability
- Partial ADR-005 exception for gh CLI phase

**Neutral**:
- Existing PowerShell skills remain for gap coverage
- Migration can be incremental (no big-bang cutover)
- Testing infrastructure (Pester) still valuable for gap fillers

### Confirmation

Implementation will be confirmed via:

1. **Benchmark tests**: Measure actual latency for each phase
2. **Capability audit**: Verify all current use cases work
3. **Code review**: Validate agent isolation configuration
4. **Integration tests**: End-to-end PR review workflow validation

## Pros and Cons of the Options

### Option A: PowerShell Wrappers (Current)

- Good, because full capability coverage (100%)
- Good, because follows ADR-005 standard
- Good, because proven in production
- Bad, because 183-416ms latency per call (unavoidable)
- Bad, because no improvement path within architecture
- Bad, because 20 scripts to maintain

### Option B: gh CLI Rewrite

- Good, because 50-70% latency reduction
- Good, because cross-platform
- Good, because reduces custom code
- Neutral, because partial capability coverage
- Bad, because violates ADR-005
- Bad, because GraphQL formatting fragile (Skill-GraphQL-001)
- Bad, because two languages to maintain

### Option C: PowerShell Daemon

- Good, because 80-95% latency reduction
- Good, because maintains ADR-005 compliance
- Good, because reuses existing scripts
- Bad, because high implementation complexity
- Bad, because security concerns (IPC injection)
- Bad, because Windows-specific semantics
- Bad, because no PowerShell MCP SDK exists

### Option D: GitHub MCP + Agent Isolation

- Good, because 90-95% latency reduction
- Good, because official GitHub implementation
- Good, because context isolation
- Good, because zero maintenance for covered ops
- Good, because cross-platform (MCP universal)
- Neutral, because capability gaps require supplemental code
- Bad, because new architecture pattern
- Bad, because external dependency

## Reversibility Assessment

### Rollback Capability

**Phase 1 (gh CLI)**:
- [x] Changes can be rolled back without data loss
- [x] Existing PowerShell scripts preserved
- [x] Simple reversion to original calls

**Phase 2-3 (GitHub MCP)**:
- [x] MCP server can be disabled in settings
- [x] GitHub agent can be removed from routing
- [x] Gap-filler scripts provide fallback

### Vendor Lock-in Assessment

**Dependency**: GitHub MCP Server (github/github-mcp-server)

**Lock-in Level**: Low

**Lock-in Indicators**:
- [ ] Proprietary APIs without standards-based alternatives (MCP is open standard)
- [ ] Data formats that require conversion to export (uses standard GitHub API)
- [x] Licensing terms that restrict migration (MIT license)
- [ ] Integration depth that increases switching cost (delegation pattern is swappable)
- [ ] Team training investment (minimal - MCP is standard)

**Exit Strategy**:
- **Trigger conditions**: GitHub MCP server deprecated, capability gaps expand, performance degrades
- **Migration path**: Revert to gh CLI calls or PowerShell scripts
- **Estimated effort**: 1-2 days to disable MCP, revert routing
- **Data export**: N/A (no data stored in MCP server)

**Accepted Trade-offs**:
We accept the GitHub MCP dependency because:
1. GitHub officially maintains the server
2. MCP is an open protocol with multiple implementations
3. Fallback to gh CLI is straightforward
4. Performance benefit (90-95% reduction) justifies dependency

## GitHub MCP Capability Gap Analysis

### Confirmed Gaps

| Operation | Current Implementation | GitHub MCP | Gap Filler |
|-----------|----------------------|------------|------------|
| Resolve review thread | Resolve-PRReviewThread.ps1 (GraphQL) | Unknown | Keep PowerShell script |
| Add reaction | Add-CommentReaction.ps1 | Unknown | Keep PowerShell script or gh api |

### Validation Required

Before Phase 3, validate these operations work via GitHub MCP:

- [ ] `pull_request_review_write` can resolve threads
- [ ] Reactions supported via some mechanism
- [ ] Pagination handled correctly for large PRs
- [ ] Rate limiting handled gracefully

## Comparison Matrix

| Criterion | Option A (PowerShell) | Option B (gh CLI) | Option C (Daemon) | Option D (MCP) |
|-----------|----------------------|-------------------|-------------------|----------------|
| **Latency** | 183-416ms | 50-80ms | 10-50ms | 5-20ms |
| **Latency Reduction** | Baseline | 50-70% | 80-95% | 90-95% |
| **Context Pollution** | None (skills) | None (bash) | None (IPC) | None (isolated) |
| **Maintenance Burden** | High (20 scripts) | Medium (hybrid) | Very High | Low |
| **Capability Coverage** | 100% | 85% | 100% | ~90% |
| **Platform Portability** | Good (pwsh) | Good (bash) | Limited (Windows) | Excellent (MCP) |
| **ADR-005 Compliance** | Yes | Partial | Yes | N/A (MCP) |
| **Implementation Effort** | Done | Low (1-2 weeks) | High (3-4 weeks) | Medium (2-4 weeks) |
| **Risk Level** | Low | Low | Medium | Low-Medium |

## Related Decisions

- [ADR-005: PowerShell-Only Scripting](./ADR-005-powershell-only-scripting.md) - Exception for gh CLI phase
- [ADR-011: Session State MCP](./ADR-011-session-state-mcp.md) - MCP architecture precedent
- [ADR-0003: Agent Tool Selection](./ADR-0003-agent-tool-selection-criteria.md) - Role-specific tool allocation

## More Information

### GitHub MCP Server Documentation

- Repository: https://github.com/github/github-mcp-server
- Tools Reference: See README.md for complete tool list
- Toolsets: context, repos, issues, pull_requests, users, actions, labels, etc.

### Agent Isolation Pattern Reference

- Source: https://github.com/obra/superpowers-chrome/blob/main/agents/browser-user.md
- Pattern: YAML frontmatter declaring agent-specific MCP servers
- Key Principle: Tools visible only in delegated agent context

### Session Context

- Session 80: Strategic PowerShell performance analysis (`.agents/sessions/2025-12-23-session-80-pwsh-performance-strategic-analysis.md`)
- Session 81: This ADR analysis (`.agents/sessions/2025-12-23-session-81-github-mcp-architecture-analysis.md`)
- Memory: `claude-pwsh-performance-strategy` - Strategy recommendations

### Issues Superseded

If Option D (GitHub MCP) validates in prototype:

- **Issue #286** (gh CLI rewrite): Partially superseded (Phase 1 remains relevant)
- **Issue #287** (PowerShell daemon): Fully superseded
- **Issue #288** (batching): Superseded (latency solved at root)

### Confidence Level

**Recommendation Confidence**: 75%

**Uncertainty Factors**:
1. GitHub MCP capability gaps not fully validated (reactions, thread resolution)
2. Agent isolation pattern not yet standard in Claude Code
3. No production benchmark data for MCP approach

**De-risking Actions**:
1. Phase 2 prototype validates capabilities before full migration
2. Gap-filler scripts provide fallback
3. Phased approach allows course correction

---

*Template Version: MADR 4.0*
*Created: 2025-12-23*
