# GitHub API Skills

## Skill-GitHub-GraphQL-001: Review Thread Resolution Requires GraphQL

**Statement**: GitHub review thread resolution requires GraphQL API; REST API is read-only

**Context**: When resolving review threads on pull requests programmatically

**Evidence**: PR #121 in rjmurillo/ai-agents - Successfully resolved 5 review conversations using GraphQL mutation `resolveReviewThread`. REST API endpoints for reviews (`GET /repos/{owner}/{repo}/pulls/{number}/reviews/{review_id}`) are read-only and do not support thread resolution.

**Implementation Example**:
```bash
gh api graphql -f query='
  mutation {
    resolveReviewThread(input: {
      threadId: "PRRT_kwDOQoWRls6cKi0O"
    }) {
      thread {
        id
        isResolved
      }
    }
  }
'
```

**Atomicity**: 100%

**Source**: Session 38 retrospective (2025-12-20)

**Related Skills**: None (first GraphQL skill)

---

## When to Use GraphQL vs REST

Use **GraphQL** for:
- Review thread operations (resolve, unresolve)
- Pull request discussions
- Project boards (v2)
- Repository discussions
- Advanced queries with nested data

Use **REST** for:
- Simple CRUD operations (create, read, update, delete)
- Webhooks and events
- Repository management
- Branch protection
- File operations

**Trade-off**: GraphQL requires more complex query structure but enables precise data fetching and operations not available in REST.
