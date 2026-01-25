# GitHub REST API Reference

## Overview

Comprehensive reference for GitHub REST API endpoints, authentication, rate limiting, and error handling patterns. This serves as a quick reference for agents working with GitHub automation.

**Last Updated**: 2025-12-18
**API Version**: 2022-11-28

---

## Authentication

### Token Types

| Token Type | Use Case | Limits |
|------------|----------|--------|
| Personal Access Token (Classic) | General API access | 5,000/hour |
| Fine-grained PAT | Scoped repository access | 5,000/hour |
| GitHub App Installation | App integrations | 5,000-15,000/hour |
| OAuth Token | Third-party apps | 5,000/hour |
| GITHUB_TOKEN (Actions) | CI/CD workflows | 1,000/hour/repo |

### Required Headers

```http
Accept: application/vnd.github+json
Authorization: Bearer <token>
X-GitHub-Api-Version: 2022-11-28
User-Agent: <app-name>
```

### Minimum Scopes (Classic PAT)

- `repo` - Full repository access
- `read:org` - Read organization membership
- `gist` - Gist access

### Fine-grained PAT Permissions

- `contents: read` - Read repository contents
- `pull_requests: write` - Create/update PRs
- `issues: write` - Create/update issues
- `workflows: write` - Trigger workflows

---

## Core Endpoints Quick Reference

### Pull Requests

| Operation | Method | Endpoint |
|-----------|--------|----------|
| List PRs | GET | `/repos/{owner}/{repo}/pulls` |
| Create PR | POST | `/repos/{owner}/{repo}/pulls` |
| Get PR | GET | `/repos/{owner}/{repo}/pulls/{pull_number}` |
| Update PR | PATCH | `/repos/{owner}/{repo}/pulls/{pull_number}` |
| Merge PR | PUT | `/repos/{owner}/{repo}/pulls/{pull_number}/merge` |
| List PR files | GET | `/repos/{owner}/{repo}/pulls/{pull_number}/files` |
| List PR commits | GET | `/repos/{owner}/{repo}/pulls/{pull_number}/commits` |
| Create review | POST | `/repos/{owner}/{repo}/pulls/{pull_number}/reviews` |
| List reviews | GET | `/repos/{owner}/{repo}/pulls/{pull_number}/reviews` |
| Request reviewers | POST | `/repos/{owner}/{repo}/pulls/{pull_number}/requested_reviewers` |

**Common Parameters**:

- `state`: open, closed, all
- `head`: Filter by head branch (user:ref-name)
- `base`: Filter by base branch
- `sort`: created, updated, popularity
- `direction`: asc, desc

### Issues

| Operation | Method | Endpoint |
|-----------|--------|----------|
| List issues (user) | GET | `/issues` |
| List issues (repo) | GET | `/repos/{owner}/{repo}/issues` |
| Create issue | POST | `/repos/{owner}/{repo}/issues` |
| Get issue | GET | `/repos/{owner}/{repo}/issues/{issue_number}` |
| Update issue | PATCH | `/repos/{owner}/{repo}/issues/{issue_number}` |
| Lock issue | PUT | `/repos/{owner}/{repo}/issues/{issue_number}/lock` |
| Add labels | POST | `/repos/{owner}/{repo}/issues/{issue_number}/labels` |
| Add assignees | POST | `/repos/{owner}/{repo}/issues/{issue_number}/assignees` |
| Create comment | POST | `/repos/{owner}/{repo}/issues/{issue_number}/comments` |

**Common Parameters**:

- `state`: open, closed, all
- `labels`: Comma-separated label names
- `assignee`: Username or "none"
- `milestone`: Milestone number or "none"
- `since`: ISO 8601 timestamp

### Repositories

| Operation | Method | Endpoint |
|-----------|--------|----------|
| List repos (org) | GET | `/orgs/{org}/repos` |
| List repos (user) | GET | `/users/{username}/repos` |
| Create repo | POST | `/user/repos` or `/orgs/{org}/repos` |
| Get repo | GET | `/repos/{owner}/{repo}` |
| Update repo | PATCH | `/repos/{owner}/{repo}` |
| Delete repo | DELETE | `/repos/{owner}/{repo}` |
| List branches | GET | `/repos/{owner}/{repo}/branches` |
| Get branch | GET | `/repos/{owner}/{repo}/branches/{branch}` |
| Get contents | GET | `/repos/{owner}/{repo}/contents/{path}` |
| Create/Update file | PUT | `/repos/{owner}/{repo}/contents/{path}` |
| List contributors | GET | `/repos/{owner}/{repo}/contributors` |
| List forks | GET | `/repos/{owner}/{repo}/forks` |
| Create fork | POST | `/repos/{owner}/{repo}/forks` |

### Actions/Workflows

| Operation | Method | Endpoint |
|-----------|--------|----------|
| List workflows | GET | `/repos/{owner}/{repo}/actions/workflows` |
| Get workflow | GET | `/repos/{owner}/{repo}/actions/workflows/{workflow_id}` |
| Trigger workflow | POST | `/repos/{owner}/{repo}/actions/workflows/{workflow_id}/dispatches` |
| List runs | GET | `/repos/{owner}/{repo}/actions/runs` |
| Get run | GET | `/repos/{owner}/{repo}/actions/runs/{run_id}` |
| Cancel run | POST | `/repos/{owner}/{repo}/actions/runs/{run_id}/cancel` |
| Re-run workflow | POST | `/repos/{owner}/{repo}/actions/runs/{run_id}/rerun` |
| Re-run failed jobs | POST | `/repos/{owner}/{repo}/actions/runs/{run_id}/rerun-failed-jobs` |
| List artifacts | GET | `/repos/{owner}/{repo}/actions/artifacts` |
| Download artifact | GET | `/repos/{owner}/{repo}/actions/artifacts/{artifact_id}/zip` |
| List secrets | GET | `/repos/{owner}/{repo}/actions/secrets` |

### Releases

| Operation | Method | Endpoint |
|-----------|--------|----------|
| List releases | GET | `/repos/{owner}/{repo}/releases` |
| Create release | POST | `/repos/{owner}/{repo}/releases` |
| Get release | GET | `/repos/{owner}/{repo}/releases/{release_id}` |
| Get latest | GET | `/repos/{owner}/{repo}/releases/latest` |
| Get by tag | GET | `/repos/{owner}/{repo}/releases/tags/{tag}` |
| Update release | PATCH | `/repos/{owner}/{repo}/releases/{release_id}` |
| Delete release | DELETE | `/repos/{owner}/{repo}/releases/{release_id}` |
| List assets | GET | `/repos/{owner}/{repo}/releases/{release_id}/assets` |
| Upload asset | POST | `{upload_url}` (from release object) |
| Generate notes | POST | `/repos/{owner}/{repo}/releases/generate-notes` |

### Commits

| Operation | Method | Endpoint |
|-----------|--------|----------|
| List commits | GET | `/repos/{owner}/{repo}/commits` |
| Get commit | GET | `/repos/{owner}/{repo}/commits/{ref}` |
| Compare commits | GET | `/repos/{owner}/{repo}/compare/{base}...{head}` |
| Get status | GET | `/repos/{owner}/{repo}/commits/{ref}/status` |
| Create status | POST | `/repos/{owner}/{repo}/statuses/{sha}` |
| List PR commits | GET | `/repos/{owner}/{repo}/commits/{commit_sha}/pulls` |

### Checks

| Operation | Method | Endpoint |
|-----------|--------|----------|
| Create check run | POST | `/repos/{owner}/{repo}/check-runs` |
| Get check run | GET | `/repos/{owner}/{repo}/check-runs/{check_run_id}` |
| Update check run | PATCH | `/repos/{owner}/{repo}/check-runs/{check_run_id}` |
| List check runs | GET | `/repos/{owner}/{repo}/commits/{ref}/check-runs` |
| List check suites | GET | `/repos/{owner}/{repo}/commits/{ref}/check-suites` |
| Create check suite | POST | `/repos/{owner}/{repo}/check-suites` |
| Rerequest check suite | POST | `/repos/{owner}/{repo}/check-suites/{check_suite_id}/rerequest` |

### Search

| Operation | Method | Endpoint | Rate Limit |
|-----------|--------|----------|------------|
| Search code | GET | `/search/code` | 10/min |
| Search commits | GET | `/search/commits` | 30/min |
| Search issues/PRs | GET | `/search/issues` | 30/min |
| Search repos | GET | `/search/repositories` | 30/min |
| Search users | GET | `/search/users` | 30/min |
| Search labels | GET | `/search/labels` | 30/min |

**Search Qualifiers**:

- `repo:owner/name` - Specific repository
- `user:username` - User's content
- `org:orgname` - Organization's content
- `language:javascript` - By language
- `is:open` / `is:closed` - Issue/PR state
- `label:bug` - By label
- `in:title` / `in:body` - Search location

---

## Rate Limiting

### Primary Rate Limits

| Authentication | Requests/Hour |
|----------------|---------------|
| Unauthenticated | 60 |
| Personal Access Token | 5,000 |
| OAuth Token | 5,000 |
| GitHub App | 5,000 (min) - 15,000 (Enterprise) |
| GITHUB_TOKEN (Actions) | 1,000 per repo |

### Secondary Rate Limits

Triggered by:

- More than 100 concurrent requests
- More than 900 points/minute (GET=1pt, mutating=5pts)
- More than 90 seconds CPU time per 60 seconds
- More than 80 content-generating requests/minute

### Rate Limit Headers

```http
x-ratelimit-limit: 5000
x-ratelimit-remaining: 4999
x-ratelimit-reset: 1372700873
x-ratelimit-used: 1
x-ratelimit-resource: core
```

### Checking Rate Limits

```bash
gh api rate_limit --jq '.resources'
```

### Handling Rate Limits

1. **403 Response**: Check `x-ratelimit-remaining`
2. **If remaining = 0**: Wait until `x-ratelimit-reset`
3. **429 Response**: Check `retry-after` header
4. **Implement exponential backoff**: Start at 1 minute, double each retry

---

## Error Handling

### HTTP Status Codes

| Code | Meaning | Action |
|------|---------|--------|
| 200 | OK | Success |
| 201 | Created | Resource created |
| 204 | No Content | Success (no body) |
| 304 | Not Modified | Use cached response |
| 400 | Bad Request | Fix request format |
| 401 | Unauthorized | Check authentication |
| 403 | Forbidden | Check permissions/rate limits |
| 404 | Not Found | Resource missing or no access |
| 422 | Unprocessable | Validation failed |
| 429 | Too Many Requests | Rate limited (secondary) |
| 500 | Server Error | Retry with backoff |
| 502/503 | Service Unavailable | Retry with backoff |

### Error Response Format

```json
{
  "message": "Validation Failed",
  "errors": [
    {
      "resource": "Issue",
      "field": "title",
      "code": "missing_field"
    }
  ],
  "documentation_url": "https://docs.github.com/..."
}
```

### Error Codes

| Code | Meaning |
|------|---------|
| `missing` | Resource doesn't exist |
| `missing_field` | Required field not provided |
| `invalid` | Field format invalid |
| `already_exists` | Duplicate unique value |
| `unprocessable` | Invalid parameters |

### 404 for Private Resources

GitHub returns 404 (not 403) for private resources to avoid confirming existence. Check:

1. Token has required scopes
2. User has repository access
3. Token is not expired/revoked
4. Path parameters are URL-encoded

---

## Pagination

### Link Header Pagination

```http
Link: <https://api.github.com/user/repos?page=3&per_page=100>; rel="next",
      <https://api.github.com/user/repos?page=50&per_page=100>; rel="last"
```

### Parameters

- `per_page`: Items per page (max 100, default 30)
- `page`: Page number (default 1)

### Using gh CLI

```bash
# Auto-paginate all results
gh api --paginate repos/{owner}/{repo}/issues

# Combine paginated JSON arrays
gh api --paginate --slurp repos/{owner}/{repo}/issues --jq 'flatten'

# Limit results
gh pr list -L 100
```

### GraphQL Pagination

```graphql
query($endCursor: String) {
  repository(owner: "owner", name: "repo") {
    issues(first: 100, after: $endCursor) {
      nodes { title }
      pageInfo {
        hasNextPage
        endCursor
      }
    }
  }
}
```

---

## Best Practices

### Request Optimization

1. **Use conditional requests**: Send `If-None-Match` with `ETag`
2. **Cache responses**: Use `gh api --cache 1h`
3. **Request only needed fields**: Use GraphQL for selective data
4. **Batch where possible**: Combine related operations

### Security

1. **Never commit tokens**: Use secrets management
2. **Use minimal scopes**: Request only needed permissions
3. **Prefer fine-grained PATs**: More granular control
4. **Rotate tokens regularly**: Especially for automation
5. **Use GITHUB_TOKEN in Actions**: Automatically scoped and rotated

### Error Resilience

1. **Implement retry logic**: Exponential backoff for 5xx errors
2. **Handle rate limits gracefully**: Check headers, wait when needed
3. **Validate inputs**: Avoid 422 errors
4. **Log responses**: For debugging failed requests

---

## Related Memories

- `skills-github-cli.md` - GitHub CLI command patterns
- `skills-github-workflow-patterns.md` - GitHub Actions patterns

## References

- [GitHub REST API Documentation](https://docs.github.com/en/rest)
- [Rate Limits Documentation](https://docs.github.com/en/rest/using-the-rest-api/rate-limits-for-the-rest-api)
- [Authentication Documentation](https://docs.github.com/en/rest/authentication)

## Related

- [github-actions-local-testing-integration](github-actions-local-testing-integration.md)
- [github-cli-001-bidirectional-issue-linking](github-cli-001-bidirectional-issue-linking.md)
- [github-cli-anti-patterns](github-cli-anti-patterns.md)
- [github-cli-api-patterns](github-cli-api-patterns.md)
- [github-cli-extensions](github-cli-extensions.md)
