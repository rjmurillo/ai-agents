# Issue #307: Memory Automation Expansion Proposal

## Current State (ADR-017 Complete)

- **Domain Indexes**: 30 skill domains
- **Indexed Files**: 197 atomic skills
- **Token Efficiency**: 82% savings with session caching

## Proposed Cache-Aside Memory Domains

### Priority 1: High-Value Caches (Reduce GitHub API calls)

| Domain | Cache Target | TTL | Invalidation Trigger |
|--------|--------------|-----|----------------------|
| `github-open-issues-cache` | Open issues list | 1 hour | Issue created/closed webhook |
| `github-open-prs-cache` | Open PRs list | 30 min | PR opened/merged/closed |
| `github-labels-milestones-cache` | Labels and milestones | 24 hours | Manual or on change |

**Benefit**: Agents frequently query open issues/PRs. Caching saves 10-20 API calls per session.

### Priority 2: Architecture Reference (Rarely Changes)

| Domain | Source | Content |
|--------|--------|---------|
| `skills-adr-index` | `.agents/architecture/ADR-*.md` | ADR summaries and decision keywords |

**ADR Index Format**:
```markdown
| ADR | Title | Status | Keywords |
|-----|-------|--------|----------|
| ADR-001 | Markdown Linting | Active | lint markdown fix autofix |
| ADR-017 | Tiered Memory | Active | memory index tier L1 L2 L3 |
```

### Priority 3: Governance Reference

| Domain | Source | Content |
|--------|--------|---------|
| `skills-governance-index` | `.agents/governance/*.md` | Governance policies and constraints |

### Priority 4: Session Context (Optional)

| Domain | Purpose | Scope |
|--------|---------|-------|
| `active-session-context` | Current session state | Single session, cleared on end |

## Cache-Aside Pattern Implementation

```text
1. Agent needs data (e.g., open PRs)
2. Check memory: mcp__serena__read_memory("github-open-prs-cache")
3. If MISS or STALE:
   a. Query GitHub API
   b. Write to memory with timestamp
   c. Use data
4. If HIT and FRESH:
   a. Use cached data directly
```

### Staleness Check

Each cache file includes header:

```markdown
# GitHub Open PRs Cache

**Last Updated**: 2025-12-23T20:30:00Z
**TTL**: 30 minutes
**Next Refresh**: After 2025-12-23T21:00:00Z

## Cached Data
...
```

Agent checks: `if (now > next_refresh) { refresh_cache() }`

## Excluded from Caching (Not Recommended)

| Domain | Reason |
|--------|--------|
| Sessions | Too transient, high churn, low reuse value |
| Planning artifacts | Already in `.agents/planning/`, not frequently queried |
| PR comments state | Changes too rapidly during review |

## Implementation Tasks

1. [ ] Create `skills-adr-index.md` domain index
2. [ ] Create `skills-governance-index.md` domain index
3. [ ] Create cache refresh scripts for GitHub data
4. [ ] Add cache staleness check to agent memory protocol
5. [ ] Update `memory-index.md` with new domains

## Token Cost Analysis

| Cache Domain | Size | Read Cost | Savings per Session |
|--------------|------|-----------|---------------------|
| ADR index | ~500 tokens | 1 read | Avoids 20 file reads |
| Open issues | ~1,000 tokens | 1 read | Avoids 3-5 API calls |
| Open PRs | ~800 tokens | 1 read | Avoids 2-3 API calls |
| Labels/Milestones | ~300 tokens | 1 read | Avoids 2 API calls |

**Total**: ~2,600 tokens for 4 domains vs 10-30 API calls saved
