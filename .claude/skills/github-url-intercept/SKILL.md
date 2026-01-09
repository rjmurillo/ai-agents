---
name: github-url-intercept
version: 2.0.0
description: Intercept GitHub PR/issue/file URLs and route to API calls instead of fetching HTML. Use when ANY github.com URL appears in user input. Prevents 5-10MB HTML fetches that exhaust context windows. Triggers on pull/, issues/, blob/, tree/, commit/, compare/ URL patterns.
license: MIT
model: claude-opus-4-5
metadata:
  domains:
  - github
  - url-parsing
  - context-optimization
  type: interceptor
  complexity: low
  related_skills:
  - github
---
# GitHub URL Intercept

**Never fetch GitHub URLs directly. Parse and route to the github skill or API.**

---

## Triggers

| Phrase | Action |
|--------|--------|
| Any `github.com/...` URL in input | Parse and route |
| `what's in this PR` + URL | Route to Get-PRContext.ps1 |
| `check this issue` + URL | Route to Get-IssueContext.ps1 |
| `look at this file` + URL | Route to gh api contents |

---

## Decision Flow

```text
GitHub URL detected in user input
│
├─ Has fragment (#pullrequestreview-, #discussion_r, #issuecomment-)?
│     Yes → Extract ID, use gh api for specific comment/review
│
├─ Is /pull/{n}?
│     Yes → Get-PRContext.ps1 -PullRequest {n} -Owner {o} -Repo {r}
│           (or Get-PRReviewComments.ps1 / Get-PRReviewThreads.ps1 for comments)
│
├─ Is /issues/{n}?
│     Yes → Get-IssueContext.ps1 -Issue {n} -Owner {o} -Repo {r}
│
├─ Is /blob/{ref}/{path} or /tree/{ref}/{path}?
│     Yes → gh api repos/{o}/{r}/contents/{path}?ref={ref}
│
├─ Is /commit/{sha}?
│     Yes → gh api repos/{o}/{r}/commits/{sha}
│
└─ Is /compare/{base}...{head}?
      Yes → gh api repos/{o}/{r}/compare/{base}...{head}
```

---

## Process

### Phase 1: URL Detection and Parsing

| Step | Action | Verification |
|------|--------|--------------|
| 1.1 | Detect github.com URL in user input | URL pattern matched |
| 1.2 | Extract owner/repo from path | Both values non-empty |
| 1.3 | Identify URL type (pull, issues, blob, tree, commit, compare) | Type classified |
| 1.4 | Extract fragment ID if present | Fragment parsed or null |

### Phase 2: Route Selection

| Step | Action | Verification |
|------|--------|--------------|
| 2.1 | Check if github skill script exists for URL type | Script path resolved |
| 2.2 | If script exists → use github skill (primary route) | Script invocation planned |
| 2.3 | If no script → use gh api (fallback route) | API command constructed |
| 2.4 | For fragments → always use gh api with specific endpoint | Endpoint includes ID |

### Phase 3: Execution

| Step | Action | Verification |
|------|--------|--------------|
| 3.1 | Execute selected command | Command runs without error |
| 3.2 | Receive structured JSON response | `Success: true` for scripts |
| 3.3 | Parse relevant fields for user query | Response processed |

---

## URL Routing Table

### Primary: Use GitHub Skill Scripts

| URL Pattern | Script | Parameters |
|-------------|--------|------------|
| `/pull/{n}` | `Get-PRContext.ps1` | `-PullRequest {n} -Owner {o} -Repo {r}` |
| `/pull/{n}` (with diff) | `Get-PRContext.ps1` | `-PullRequest {n} -IncludeDiff` |
| `/pull/{n}` (review comments) | `Get-PRReviewComments.ps1` | `-PullRequest {n}` |
| `/pull/{n}` (review threads) | `Get-PRReviewThreads.ps1` | `-PullRequest {n}` |
| `/pull/{n}` (CI status) | `Get-PRChecks.ps1` | `-PullRequest {n}` |
| `/issues/{n}` | `Get-IssueContext.ps1` | `-Issue {n} -Owner {o} -Repo {r}` |

**Script location**: `.claude/skills/github/scripts/`

### Fallback: Raw gh Commands

Use only when no script exists for the operation:

| URL Pattern | API Call |
|-------------|----------|
| `/pull/{n}#pullrequestreview-{id}` | `gh api repos/{o}/{r}/pulls/{n}/reviews/{id}` |
| `/pull/{n}#discussion_r{id}` | `gh api repos/{o}/{r}/pulls/comments/{id}` |
| `/pull/{n}#issuecomment-{id}` | `gh api repos/{o}/{r}/issues/comments/{id}` |
| `/issues/{n}#issuecomment-{id}` | `gh api repos/{o}/{r}/issues/comments/{id}` |
| `/blob/{ref}/{path}` | `gh api repos/{o}/{r}/contents/{path}?ref={ref}` |
| `/tree/{ref}/{path}` | `gh api repos/{o}/{r}/contents/{path}?ref={ref}` |
| `/commit/{sha}` | `gh api repos/{o}/{r}/commits/{sha}` |
| `/compare/{base}...{head}` | `gh api repos/{o}/{r}/compare/{base}...{head}` |

---

## URL Parsing Pattern

Extract owner, repo, and resource from GitHub URLs:

```text
https://github.com/{owner}/{repo}/pull/{number}
https://github.com/{owner}/{repo}/issues/{number}
https://github.com/{owner}/{repo}/blob/{ref}/{path}
https://github.com/{owner}/{repo}/tree/{ref}/{path}
https://github.com/{owner}/{repo}/commit/{sha}
https://github.com/{owner}/{repo}/compare/{base}...{head}
```

**Fragment extraction** (when present):

- `#pullrequestreview-{id}` → Review ID
- `#discussion_r{id}` → Discussion comment ID
- `#issuecomment-{id}` → Issue comment ID

---

## Why This Matters

| Method | Size | Tokens | Time |
|--------|------|--------|------|
| HTML fetch | 5-10 MB | 1-2.5M | 10-30s |
| API call | 1-50 KB | 250-12K | 0.5-2s |
| Script (structured) | 1-50 KB | 250-12K | 0.5-2s |

**100x reduction in context consumption.**

---

## Examples

### PR URL → Script

```text
Input: "Review this: https://github.com/owner/repo/pull/123"

Action:
  pwsh .claude/skills/github/scripts/pr/Get-PRContext.ps1 -PullRequest 123 -Owner owner -Repo repo
```

### Issue URL → Script

```text
Input: "What's the status of https://github.com/owner/repo/issues/456"

Action:
  pwsh .claude/skills/github/scripts/issue/Get-IssueContext.ps1 -Issue 456 -Owner owner -Repo repo
```

### PR with Comment Fragment → API

```text
Input: "Respond to https://github.com/owner/repo/pull/123#discussion_r987654321"

Action:
  gh api repos/owner/repo/pulls/comments/987654321
```

### File URL → API

```text
Input: "Show me https://github.com/owner/repo/blob/main/src/app.py"

Action:
  gh api repos/owner/repo/contents/src/app.py?ref=main
```

---

## Anti-Patterns

| Avoid | Why | Instead |
|-------|-----|---------|
| `web_fetch` on github.com | 5-10 MB HTML response | Parse URL, use script or API |
| `curl` on GitHub URLs | Same problem | Use `gh` CLI |
| Raw `gh pr view` | Unstructured output | Use `Get-PRContext.ps1` |
| Fetching full page for one comment | Massive waste | Extract fragment ID, call specific endpoint |
| Hardcoding owner/repo | Breaks in forks | Let scripts infer or extract from URL |

---

## Related Skills

| Skill | When to Use |
|-------|-------------|
| [github](../github/SKILL.md) | Full PR/issue operations (mutations, reactions, labels) |
| [pr-comment-responder](../pr-comment-responder/SKILL.md) | Systematic PR review response |

---

## Verification Checklist

Before processing any GitHub URL:

- [ ] Extracted owner/repo from URL path
- [ ] Identified URL type (PR, issue, blob, commit, compare)
- [ ] Extracted fragment ID if present (#discussion_r, #issuecomment-, #pullrequestreview-)
- [ ] Selected appropriate github skill script (primary) or gh command (fallback)
- [ ] Did NOT use web_fetch, curl, or browser-based fetch on the URL
- [ ] Received structured JSON response with `Success: true` (for scripts)
