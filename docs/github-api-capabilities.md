# GitHub API Capability Matrix: GraphQL vs REST

A reference guide documenting capability differences between GitHub's REST and GraphQL APIs to help developers choose the right API for each operation.

## Overview

GitHub provides two APIs:

- **REST API**: Simple, familiar HTTP-based interface with endpoint-per-resource design
- **GraphQL API**: Flexible query language allowing precise data fetching and operations not available in REST

This guide documents which API to use for specific operations based on capabilities and limitations discovered during development.

## Quick Reference: API Selection

| Use Case | Recommended API |
|----------|-----------------|
| Simple CRUD operations | REST |
| File operations | REST |
| Webhooks and events | REST |
| Review thread operations | GraphQL |
| Pull request discussions | GraphQL |
| Project boards v2 | GraphQL |
| Repository discussions | GraphQL |
| Nested data queries | GraphQL |

## Capability Matrix

### Operations Requiring GraphQL

These operations are only available via GraphQL:

| Operation | REST | GraphQL | Notes |
|-----------|------|---------|-------|
| Review thread resolution | Read-only | `resolveReviewThread` mutation | REST cannot resolve threads |
| PR discussions (nested) | Limited | Full CRUD | Nested comments require GraphQL |
| Project boards v2 | Not available | Full support | Projects v2 API is GraphQL-only |
| Repository discussions | Not available | Full support | Discussions API is GraphQL-only |
| Advanced nested queries | Multiple requests | Single query | GraphQL more efficient |

### Operations Available in Both APIs

| Operation | REST | GraphQL | Recommendation |
|-----------|------|---------|----------------|
| Branch protection rules | Full support | Full support | Either |
| Pull request management | Full support | Full support | REST for simple, GraphQL for complex |
| Issue management | Full support | Full support | REST for simple, GraphQL for complex |
| Repository management | Full support | Full support | REST |
| User/organization data | Full support | Full support | REST for simple, GraphQL for nested |

### Operations Preferring REST

| Operation | REST | GraphQL | Notes |
|-----------|------|---------|-------|
| File operations | Full support | Limited | REST preferred for file CRUD |
| Webhooks and events | Full support | Not available | REST only |
| Git data operations | Full support | Limited | REST preferred |
| Repository releases | Full support | Limited | REST preferred |

## When to Use Each API

### Use REST API For

- **Simple CRUD operations**: Create, read, update, delete on single resources
- **Webhooks and event subscriptions**: REST is the only option
- **Repository management**: Branches, tags, releases
- **File operations**: Reading, creating, updating files
- **Quick prototyping**: Simpler syntax, easier debugging
- **Operations with good caching**: Standard HTTP caching support

### Use GraphQL API For

- **Review thread operations**: Resolve, unresolve threads
- **Pull request discussions**: Nested comments, full thread context
- **Project boards v2**: All projects v2 operations
- **Repository discussions**: Create, read, update discussions
- **Advanced queries with nested data**: Fetch related data in one query
- **Minimizing API calls**: Reduce over-fetching and under-fetching

## Implementation Examples

### Example 1: Review Thread Resolution

The most common case where GraphQL is required:

```bash
# REST API - Read-only (CANNOT resolve threads)
gh api repos/{owner}/{repo}/pulls/{number}/reviews/{review_id}
# Returns review data but no resolution capability

# GraphQL - Required for resolution
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

### Example 2: Getting PR with Nested Data

```bash
# REST API - Multiple requests needed
gh api repos/{owner}/{repo}/pulls/{number}
gh api repos/{owner}/{repo}/pulls/{number}/reviews
gh api repos/{owner}/{repo}/pulls/{number}/comments

# GraphQL - Single query for all data
gh api graphql -f query='
  query {
    repository(owner: "{owner}", name: "{repo}") {
      pullRequest(number: {number}) {
        title
        body
        reviews(first: 10) {
          nodes {
            state
            body
          }
        }
        comments(first: 50) {
          nodes {
            body
            author { login }
          }
        }
      }
    }
  }
'
```

### Example 3: Projects v2 (GraphQL Only)

```bash
# Projects v2 requires GraphQL
gh api graphql -f query='
  query {
    repository(owner: "{owner}", name: "{repo}") {
      projectsV2(first: 5) {
        nodes {
          title
          items(first: 20) {
            nodes {
              content {
                ... on Issue { title number }
                ... on PullRequest { title number }
              }
            }
          }
        }
      }
    }
  }
'
```

## Trade-offs

### GraphQL Advantages

- **Precise data fetching**: Request exactly what you need
- **Single request for related data**: No over-fetching or under-fetching
- **Exclusive operations**: Threads, discussions, projects v2

### GraphQL Disadvantages

- **Complex query structure**: Learning curve for mutations and queries
- **Less familiar**: Developers often default to REST
- **Harder to debug**: Single endpoint for all operations

### REST Advantages

- **Simple syntax**: Just HTTP + JSON
- **Familiar pattern**: One endpoint per resource type
- **Easy debugging**: Clear endpoint-to-resource mapping
- **Standard caching**: Built-in HTTP caching support

### REST Disadvantages

- **Multiple requests for related data**: Over-fetching common
- **Missing operations**: Threads, discussions, projects v2 not available
- **Less efficient for complex queries**: More API calls needed

## Project Skills Using Each API

### REST API Skills

| Skill | Location | Purpose |
|-------|----------|---------|
| `Get-PRContext.ps1` | `.claude/skills/github/scripts/pr/` | Get PR metadata |
| `Set-IssueLabels.ps1` | `.claude/skills/github/scripts/issue/` | Manage issue labels |
| `Add-CommentReaction.ps1` | `.claude/skills/github/scripts/reactions/` | Add emoji reactions |

### GraphQL API Skills

| Skill | Location | Purpose |
|-------|----------|---------|
| `Resolve-PRReviewThread.ps1` | `.claude/skills/github/scripts/pr/` | Resolve review threads |
| `Get-PRReviewThreads.ps1` | `.claude/skills/github/scripts/pr/` | Get thread details |
| `Get-UnresolvedReviewThreads.ps1` | `.claude/skills/github/scripts/pr/` | Find unresolved threads |

## Common Patterns

### Pattern 1: Check REST First, Fall Back to GraphQL

```powershell
# Try REST API first (simpler)
$result = gh api repos/{owner}/{repo}/pulls/{number} | ConvertFrom-Json

# If operation not available, use GraphQL
if ($needThreadResolution) {
    gh api graphql -f query='mutation { resolveReviewThread... }'
}
```

### Pattern 2: Use GraphQL for Complex Data Gathering

```powershell
# When you need multiple related pieces of data, prefer GraphQL
$query = '
query($owner: String!, $repo: String!, $number: Int!) {
  repository(owner: $owner, name: $repo) {
    pullRequest(number: $number) {
      title
      author { login }
      reviews(first: 50) { nodes { state author { login } } }
      reviewThreads(first: 100) { nodes { isResolved comments(first: 1) { nodes { body } } } }
    }
  }
}
'
$data = gh api graphql -f query="$query" -f owner="$owner" -f repo="$repo" -F number="$number" | ConvertFrom-Json
```

## Related Resources

- [GitHub GraphQL API Documentation](https://docs.github.com/en/graphql)
- [GitHub REST API Documentation](https://docs.github.com/en/rest)
- [GraphQL Explorer](https://docs.github.com/en/graphql/overview/explorer)
- Project Serena memories: `graphql-vs-rest`, `github-cli-api-patterns`

## Discovery Notes

This guide was created based on discoveries from development sessions:

- **Session 38**: Discovered review thread resolution requires GraphQL
- **PR #121**: First implementation of GraphQL thread resolution
- **Issue #155**: Consolidated API capability documentation

## Related Memories

For additional context, see these Serena memories:

- `graphql-vs-rest`: General API comparison
- `graphql-pr-operations`: PR-specific GraphQL patterns
- `github-cli-api-patterns`: Common `gh api` usage patterns
- `github-rest-api-reference`: REST API quick reference
