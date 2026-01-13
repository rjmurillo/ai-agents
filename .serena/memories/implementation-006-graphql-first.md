# Skill-Implementation-006: GraphQL-First API Analysis

**Statement**: Check GraphQL capabilities before assuming REST API sufficient for feature

**Atomicity**: 92%

**Context**: During design phase for GitHub API integrations, verify both REST and GraphQL endpoints

**Evidence**: PR #402 - REST API lacked `isResolved` field, GraphQL query required

## When to Apply

**Trigger Conditions**:
- Designing new GitHub API integrations
- Existing REST API missing required fields
- Need nested data structures (comments → threads → status)
- Performance-critical queries (fetch multiple related entities)

**Applies To**:
- GitHub API integrations
- Any GraphQL-capable external API
- Feature design phase (before implementation)

## How to Apply

1. **Check REST API First**: GitHub REST API is simpler, start there
2. **Identify Gaps**: List fields/relationships not exposed via REST
3. **Consult GraphQL Schema**: `gh api graphql --paginate -f query='{__schema{types{name}}}'`
4. **Evaluate Tradeoffs**:
   - REST: Simpler, widely understood, rate limit = 5000/hour
   - GraphQL: Flexible, nested queries, rate limit = 5000/hour (separate bucket)
5. **Document Decision**: Why GraphQL required (or why REST sufficient)

## Example (PR #402)

**Feature**: Detect unresolved review threads

**REST API Check**:
- Endpoint: `GET /repos/{owner}/{repo}/pulls/{pull_number}/comments`
- Fields: `id`, `body`, `user`, `reactions`, `created_at`, `updated_at`
- **Missing**: `isResolved` field (thread resolution status)

**GraphQL Discovery**:
- Query: `repository -> pullRequest -> reviewThreads -> isResolved`
- **Available**: `isResolved` boolean field

**Decision**: Use GraphQL (REST insufficient)

**Outcome**: GraphQL query successful on first attempt

## GraphQL Query Pattern (Reference)

```graphql
query {
  repository(owner: "$Owner", name: "$Repo") {
    pullRequest(number: $PR) {
      reviewThreads(first: 100) {
        nodes {
          id
          isResolved
          comments(first: 1) {
            nodes { databaseId }
          }
        }
      }
    }
  }
}
```

**PowerShell Invocation**:
```powershell
$query = @"
query {
  repository(owner: "$Owner", name: "$Repo") {
    pullRequest(number: $PR) {
      reviewThreads(first: 100) {
        nodes {
          id
          isResolved
        }
      }
    }
  }
}
"@

$result = gh api graphql -f query="$query" | ConvertFrom-Json
```

## Anti-Patterns

❌ **REST Assumption**: "REST API should have everything I need"
✅ **Verify First**: "Check both REST and GraphQL, use appropriate API"

❌ **Late Discovery**: "Implement with REST, discover GraphQL needed during testing"
✅ **Early Analysis**: "Identify API gaps during design phase"

❌ **Single-API Mindset**: "Only use REST because it's familiar"
✅ **Best-Fit Selection**: "Use GraphQL when REST insufficient, REST when simpler"

## Related Skills

- **Skill-Implementation-005**: GraphQL reference pattern reuse
- **Skill-Planning-004**: Critic checkpoint before implementation (catches API selection issues)

## Performance Considerations

- **GraphQL Rate Limit**: Separate from REST (5000/hour vs 5000/hour)
- **Query Complexity**: Nested queries count as 1 API call
- **Pagination**: Use `first: 100` with `endCursor` for large result sets

## Reference Implementations

- **PR #402**: `Get-UnresolvedReviewThreads` function (lines 588-640 in `Invoke-PRMaintenance.ps1`)
- **Existing Pattern**: `.claude/skills/github/scripts/pr/Resolve-PRReviewThread.ps1`

## Validation

**Metric**: GraphQL query succeeds on first attempt = correct API selection

**Evidence**: PR #402 GraphQL integration worked immediately

**Impact**: Medium (saved research time, avoided REST refactor)

## Tags

- implementation
- graphql
- api-selection
- design-phase
- github-api

## Related

- [implementation-001-memory-first-pattern](implementation-001-memory-first-pattern.md)
- [implementation-001-pre-implementation-test-discovery](implementation-001-pre-implementation-test-discovery.md)
- [implementation-002-test-driven-implementation](implementation-002-test-driven-implementation.md)
- [implementation-additive-approach](implementation-additive-approach.md)
- [implementation-clarification](implementation-clarification.md)
