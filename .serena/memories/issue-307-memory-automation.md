# Issue #307: Memory Automation Expansion Proposal

## Current State (ADR-017 Complete)

- **Domain Indexes**: 30 skill domains
- **Indexed Files**: 197 atomic skills
- **Token Efficiency**: 82% savings with session caching

## Cache Strategy (DECISION NEEDED)

### Problem

Ephemeral cache files (open PRs, open issues) in git would:
1. Cause merge conflicts on every PR
2. Slow merge velocity
3. Require constant conflict resolution from main

### Options

| Option | Pros | Cons |
|--------|------|------|
| **Session-local cache** | No merge conflicts | No cross-session benefit |
| **cloudmcp cache** | Cross-session, no conflicts | External dependency |
| **Invalidate-on-write** | Fresh data guaranteed | Requires write hooks |
| **No cache (query API)** | Always fresh | Higher API usage |

### Recommendation

Do NOT store ephemeral cache data in `.serena/memories/`. Use one of:
1. Session-local variables (in-context)
2. cloudmcp for cross-session caching
3. Local temp files outside git tracking

### Invalidation Strategy

Prefer invalidate-on-write over TTL-on-read:
- When closing PR/Issue: invalidate cache
- When creating PR/Issue: invalidate cache
- Avoids stale data from TTL-based reads

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
