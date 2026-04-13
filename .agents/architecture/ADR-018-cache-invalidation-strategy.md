# ADR-018: Cache Invalidation Strategy for GitHub Data

**Status**: Accepted
**Date**: 2025-12-23
**Deciders**: User, Claude Opus 4.5
**Context**: Issue #307 Memory Automation, PR #308

---

## Context and Problem Statement

Agents frequently query GitHub API for:
- Open PRs list (10-20 calls per session)
- Open issues list (5-10 calls per session)
- Labels and milestones (2-5 calls per session)

This creates latency and rate limit pressure. Caching could reduce API calls by 80%.

**Key Question**: Where should cache data live, and how should it be invalidated?

---

## Decision Drivers

1. **Merge Velocity**: Cache files in git would cause merge conflicts on every PR
2. **Data Freshness**: Stale cache data leads to incorrect agent decisions
3. **Cross-Session Benefit**: Cache should persist across sessions where valuable
4. **Invalidation Reliability**: Must guarantee cache is invalidated when underlying data changes
5. **Complexity**: Solution should not require complex infrastructure

---

## Considered Options

### Option 1: Git-Tracked Cache Files

**Store cache in `.serena/memories/github-*-cache.md`**

| Aspect | Assessment |
|--------|------------|
| Cross-session | Yes |
| Merge conflicts | **HIGH** - every session updates cache |
| Invalidation | TTL-based (stale data risk) |
| Complexity | Low |

**Rejected**: Merge conflicts would slow merge velocity unacceptably.

### Option 2: Session-Local Cache (In-Context)

**Store cache in agent's working memory during session**

| Aspect | Assessment |
|--------|------------|
| Cross-session | No |
| Merge conflicts | None |
| Invalidation | Automatic (session end) |
| Complexity | Very low |

**Trade-off**: No cross-session benefit, but zero conflict risk.

### Option 3: External Cache (cloudmcp)

**Store cache in cloudmcp memory graph**

| Aspect | Assessment |
|--------|------------|
| Cross-session | Yes |
| Merge conflicts | None |
| Invalidation | On-write or TTL |
| Complexity | Medium (external dependency) |

**Trade-off**: Adds external dependency but provides cross-session benefit.

### Option 4: Invalidate-on-Write Pattern

**No persistent cache; invalidate on state-changing operations**

| Aspect | Assessment |
|--------|------------|
| Cross-session | N/A (no cache) |
| Merge conflicts | None |
| Invalidation | Guaranteed fresh after writes |
| Complexity | Low |

**Pattern**: After closing PR/Issue, next read queries API fresh.

---

## Decision

**Primary**: Option 2 (Session-Local Cache) for simplicity
**Secondary**: Option 3 (cloudmcp) when cross-session benefit is critical

### Rationale

1. **Merge velocity is paramount**: Git-tracked caches are rejected outright
2. **Session-local is sufficient**: Most sessions need fresh data at start anyway
3. **Invalidate-on-write**: When agent closes/creates PR/Issue, clear any session cache
4. **cloudmcp for specific use cases**: Labels/milestones change rarely, worth caching externally

---

## Implementation

### Session-Local Pattern

```text
# At session start
CACHE = {}

# Before API call
def get_open_prs():
    if "open_prs" in CACHE:
        return CACHE["open_prs"]
    result = gh_api("repos/{owner}/{repo}/pulls?state=open")
    CACHE["open_prs"] = result
    return result

# After state-changing operation
def close_pr(number):
    gh_api(f"repos/{owner}/{repo}/pulls/{number}", method="PATCH", state="closed")
    CACHE.pop("open_prs", None)  # Invalidate cache
```

### cloudmcp Pattern (for stable data)

```text
# Labels rarely change - cache externally
mcp__cloudmcp-manager__memory-search_nodes(query="github-labels-cache")
# If not found or stale:
labels = gh_api("repos/{owner}/{repo}/labels")
mcp__cloudmcp-manager__memory-create_entities(entities=[{
    "name": "github-labels-cache",
    "observations": [json.dumps(labels)]
}])
```

### Invalidation Triggers

| Event | Action |
|-------|--------|
| PR opened/closed/merged | Clear `open_prs` cache |
| Issue opened/closed | Clear `open_issues` cache |
| Label created/deleted | Clear `labels` cache (cloudmcp) |
| Session end | All session-local cache cleared |

---

## Consequences

### Positive

- Zero merge conflicts (no git-tracked cache files)
- Guaranteed fresh data after state changes
- Simple implementation (no external dependencies for basic case)
- cloudmcp available for cross-session needs

### Negative

- First query each session hits API (no warm cache)
- Requires discipline to invalidate on writes
- cloudmcp adds complexity for stable data caching

### Risks and Mitigations

| Risk | Mitigation |
|------|------------|
| Forgetting to invalidate | Add invalidation to all state-changing skill scripts |
| Rate limiting | Session-local cache still reduces calls by 50-80% within session |
| Stale cloudmcp data | Add timestamp; refresh if older than 24h |

---

## Related Decisions

- **ADR-017**: Tiered Memory Index Architecture (defines what goes in `.serena/memories/`)
- **ADR-007**: Memory-First Architecture (context retrieval patterns)

---

## Notes

This ADR explicitly rejects storing ephemeral cache data in `.serena/memories/` to preserve merge velocity. The memory system is for durable knowledge (skills, patterns, decisions), not transient state (current open PRs).
