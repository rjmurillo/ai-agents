---
status: accepted
date: 2026-03-25
decision-makers: ["architect", "orchestrator"]
consulted: ["analyst", "security", "devops"]
informed: ["all agents"]
supersedes: null
amends: ADR-003
---

# ADR-053: GitHub Search Tool Expansion for Research-Capable Agents

## Context

PR #1517 identified a capability gap: agents with web/external research tools lacked equivalent GitHub search capabilities. The analyst agent had GitHub search tools, but other research-capable agents (orchestrator, devops, implementer, security, backlog-generator) could only list items via `list_issues`/`list_pull_requests` but could not perform text search across GitHub.

This created an asymmetry where agents could search the web for information but could not search the repository's own issues, PRs, or code through the GitHub MCP server.

**Problem**: How should GitHub search tools be allocated to maintain ADR-003's principle of least privilege while ensuring research-capable agents can search GitHub effectively?

## Decision

Extend GitHub search tool allocation to agents that already have search/research capabilities, following a tiered approach based on role requirements.

### Tool Allocation by Agent

| Agent | GitHub Search Tools Added | Rationale |
|-------|---------------------------|-----------|
| analyst | search_repositories, search_users | Complete research suite (already had search_code, search_issues, search_pull_requests) |
| orchestrator | search_code, search_issues, search_pull_requests, search_repositories | Coordination requires finding related issues/PRs |
| devops | search_code, search_issues, search_repositories, list_issues | CI/CD troubleshooting requires finding related issues and code |
| implementer | search_code, search_issues | Finding existing implementations and related issues |
| security | search_code | CVE/vulnerability pattern search in codebase |
| backlog-generator | search_issues, search_pull_requests, search_repositories, list_issues, list_pull_requests | Autonomous backlog generation requires surveying project state |

### Agents Deliberately Excluded

The following agents do NOT receive GitHub search tools per ADR-003 principles:

- **architect, critic, planner**: Internal design/review focus; delegate research to analyst
- **explainer, high-level-advisor, roadmap**: Documentation/strategic focus; no GitHub search needed
- **independent-thinker**: Has web/DeepWiki/Perplexity but uses analyst for GitHub-specific research
- **memory, retrospective, skillbook, qa**: Specialized roles without research mandate

## Rationale

### Why Not Give All Agents GitHub Search?

1. **Context window cost**: Each GitHub MCP tool adds ~100-300 tokens of schema overhead
2. **Role clarity**: ADR-003 established that tool boundaries reinforce specialization
3. **Delegation model**: The orchestrator routes research-heavy tasks to analyst; not every agent needs independent search

### Why These Specific Agents?

| Agent | Has Search Tools | Has Execute | Research Role | GitHub Search Needed |
|-------|------------------|-------------|---------------|----------------------|
| analyst | web, perplexity, context7, deepwiki | No | Primary | Yes - full suite |
| orchestrator | Basic | Yes | Coordination | Yes - for routing decisions |
| devops | Basic | Yes | CI/CD troubleshooting | Yes - issue/code search |
| implementer | Basic | Yes | Implementation | Yes - code/issue search |
| security | web, perplexity | No | Vulnerability research | Yes - code pattern search |
| backlog-generator | web | No | Project state analysis | Yes - issue/PR survey |

### Alternatives Considered

| Alternative | Pros | Cons | Why Not Chosen |
|-------------|------|------|----------------|
| No GitHub search expansion | Minimal context overhead | Research asymmetry persists | Agents can search web but not their own repo |
| Full GitHub search for all agents | Maximum flexibility | Violates ADR-003 least privilege | 77 tools per agent is anti-pattern |
| GitHub search only for analyst | Single source of truth | Bottleneck for simple searches | Orchestrator/implementer need quick lookups |

## Consequences

### Positive

- Agents can search their own repository with the same ease as web search
- Reduced delegation overhead for simple "find related issue" queries
- Backlog generator can autonomously survey project state

### Negative

- Increased tool schema overhead for 6 agents (~600-1800 tokens total)
- More tools means more potential for tool misuse (ASI02)

### Neutral

- Requires ADR-003 decision matrix update to reflect new allocations

## Implementation Notes

### Adding GitHub Search to an Agent

1. Verify agent has existing search/research capability (per ADR-003 Category 3)
2. Select minimal GitHub search tools for role:
   - Code-focused: `search_code`
   - Issue-focused: `search_issues`, `list_issues`
   - PR-focused: `search_pull_requests`, `list_pull_requests`
   - Repository-focused: `search_repositories`
3. Update agent frontmatter `tools:` section
4. Document rationale in this ADR

### Validation

Verify implementation by checking modified agent files:

```bash
grep -l "search_code\|search_issues\|search_pull_requests" .claude/agents/*.md
```

## Related Decisions

- [ADR-003: Role-Specific Tool Allocation](ADR-003-agent-tool-selection-criteria.md) - Parent allocation strategy (this ADR amends)
- [ADR-027: GitHub MCP Agent Isolation](ADR-027-github-mcp-agent-isolation.md) - Repository scope restrictions

## References

- PR #1517: fix(agents): add GitHub search tools to agent definitions
- Issue #1511: Agent tool allocation gap (GitHub search)
