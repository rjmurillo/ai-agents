# GraphQL vs REST Decision Matrix

**Statement**: Choose GraphQL or REST based on operation type and data needs

**Context**: Deciding which GitHub API to use

**Atomicity**: 90%

**Impact**: 8/10

## Decision Matrix

| Use Case | GraphQL | REST | Rationale |
|----------|---------|------|-----------|
| Reply to review thread | Yes | Yes | GraphQL if PRRT_xxx ID, REST if numeric ID |
| Resolve review thread | Yes | No | GraphQL only (no REST endpoint) |
| Add reaction | Yes | Yes | REST simpler for single reaction |
| Batch operations | Yes | No | GraphQL supports multiple mutations |
| Query with nested data | Yes | No | GraphQL avoids multiple REST calls |

## When to Use GraphQL

- Need to resolve/unresolve review threads
- Batching multiple operations
- Complex nested queries
- Have node IDs (PRRT_xxx, IC_xxx)

## When to Use REST

- Simple single operations
- Working with numeric IDs
- Adding reactions (simpler syntax)
- Well-documented endpoint exists

## REST Example (Simpler)

```bash
gh api repos/OWNER/REPO/issues/comments/ID/reactions -X POST -f content=eyes
```
