# URL Routing Patterns

## Pattern Recognition

### PR URLs

```text
Standard PR:
  https://github.com/owner/repo/pull/123
  → Get-PRContext.ps1 -PullRequest "123" -Owner "owner" -Repo "repo"

PR with specific review:
  https://github.com/owner/repo/pull/123#pullrequestreview-456789
  → gh api "repos/owner/repo/pulls/123/reviews/456789"

PR with discussion comment:
  https://github.com/owner/repo/pull/123#discussion_r987654321
  → gh api "repos/owner/repo/pulls/comments/987654321"

PR with issue-style comment:
  https://github.com/owner/repo/pull/123#issuecomment-123456789
  → gh api "repos/owner/repo/issues/comments/123456789"

PR files tab:
  https://github.com/owner/repo/pull/123/files
  → Get-PRContext.ps1 -PullRequest "123" -IncludeChangedFiles

PR commits tab:
  https://github.com/owner/repo/pull/123/commits
  → Get-PRContext.ps1 -PullRequest "123" (includes commit count)

PR checks tab:
  https://github.com/owner/repo/pull/123/checks
  → Get-PRChecks.ps1 -PullRequest "123"
```

### Issue URLs

```text
Standard issue:
  https://github.com/owner/repo/issues/456
  → Get-IssueContext.ps1 -Issue "456" -Owner "owner" -Repo "repo"

Issue with comment:
  https://github.com/owner/repo/issues/456#issuecomment-789123456
  → gh api "repos/owner/repo/issues/comments/789123456"
```

### File/Tree URLs

```text
File on branch:
  https://github.com/owner/repo/blob/main/src/app.py
  → gh api "repos/owner/repo/contents/src/app.py?ref=main"

File at commit:
  https://github.com/owner/repo/blob/abc123/src/app.py
  → gh api "repos/owner/repo/contents/src/app.py?ref=abc123"

Directory:
  https://github.com/owner/repo/tree/main/src
  → gh api "repos/owner/repo/contents/src?ref=main"
```

### Commit URLs

```text
Commit:
  https://github.com/owner/repo/commit/abc123def456
  → gh api "repos/owner/repo/commits/abc123def456"
```

### Compare URLs

```text
Branch comparison:
  https://github.com/owner/repo/compare/main...feature-branch
  → gh api "repos/owner/repo/compare/main...feature-branch"

Tag comparison:
  https://github.com/owner/repo/compare/v1.0.0...v2.0.0
  → gh api "repos/owner/repo/compare/v1.0.0...v2.0.0"
```

## Script Selection Guide

### When to Use Scripts (Primary)

| Need | Script | Why |
|------|--------|-----|
| PR overview | Get-PRContext.ps1 | Structured JSON, proper error handling |
| Review comments | Get-PRReviewComments.ps1 | Pagination handled, threading preserved |
| Review threads | Get-PRReviewThreads.ps1 | Full thread context |
| CI status | Get-PRChecks.ps1 | Can wait for completion, structured output |
| Issue overview | Get-IssueContext.ps1 | Structured JSON, proper error handling |

### When to Use gh api (Fallback)

| Need | Command Pattern | Why |
|------|-----------------|-----|
| Specific comment by ID | `gh api repos/{o}/{r}/pulls/comments/{id}` | No script for single comment |
| Specific review by ID | `gh api repos/{o}/{r}/pulls/{n}/reviews/{id}` | No script for single review |
| File contents | `gh api repos/{o}/{r}/contents/{path}` | File operations not in github skill |
| Commit details | `gh api repos/{o}/{r}/commits/{sha}` | Commit operations not in github skill |
| Branch comparison | `gh api repos/{o}/{r}/compare/{base}...{head}` | Compare not in github skill |

## Context Optimization

### Size Comparison by Method

| URL Type | HTML Size | API/Script Size | Savings |
|----------|-----------|-----------------|---------|
| PR view | 5-10 MB | 10-100 KB | 50-100x |
| Issue view | 2-5 MB | 5-50 KB | 40-100x |
| File blob | 1-5 MB | 1-500 KB | 2-10x |
| Commit | 2-8 MB | 10-100 KB | 20-80x |
| Compare | 3-10 MB | 50-500 KB | 6-20x |

### When Size Matters Most

1. **Large PRs** (100+ files, 1000+ lines)
   - Use `-DiffStat` instead of full diff
   - Use `-IncludeChangedFiles` without `-IncludeDiff`

2. **Busy issues** (50+ comments)
   - Get issue context first
   - Fetch specific comments only if needed

3. **Large files**
   - API returns base64, decode only what's needed
   - Consider line-range requests if supported

## Error Handling

### Common Errors and Recovery

| Error | Cause | Recovery |
|-------|-------|----------|
| 404 Not Found | Wrong owner/repo or PR/issue | Verify URL components |
| 403 Forbidden | Private repo, no access | Check `gh auth status` |
| 401 Unauthorized | Token expired | Run `gh auth refresh` |
| Rate limited | Too many requests | Wait or use authenticated requests |

### Script vs API Error Handling

**Scripts** (preferred):

- Return structured `Success: $false` with error details
- Exit codes indicate error type
- Stderr contains human-readable messages

**Raw gh api**:

- Returns HTTP error codes
- JSON error body with message
- Less structured handling needed
