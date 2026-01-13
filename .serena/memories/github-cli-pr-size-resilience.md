# GitHub CLI PR Size Resilience Pattern

**Created**: 2025-12-28
**Source**: Issue #468 Phase 1 Implementation
**Context**: Replacing `gh pr diff` with files API to handle large PRs

## Problem

`gh pr diff --name-only` fails with HTTP 406 when PR diff exceeds 20,000 lines:

```text
could not find pull request diff: HTTP 406: Sorry, the diff exceeded the maximum number of lines (20000)
PullRequest.diff too_large
```

## Solution Pattern

Replace `gh pr diff` with GitHub files API which has no line limit:

### PowerShell Pattern

```powershell
# Before (breaks at 20k lines)
$changedFiles = gh pr diff $env:PR_NUMBER --name-only

# After (works for any size)
$changedFiles = gh api "repos/$env:GITHUB_REPOSITORY/pulls/$env:PR_NUMBER/files" --paginate --jq '.[].filename' | Out-String
```

### Bash Pattern

```bash
# Before (breaks at 20k lines)
CHANGED_FILES=$(gh pr diff $PR_NUMBER --name-only)

# After (works for any size)
CHANGED_FILES=$(gh api "repos/$GH_REPO/pulls/$PR_NUMBER/files" --paginate --jq '.[].filename')
```

## Key Requirements

1. **Use `--paginate` flag**: Files API returns max 100 files per page
2. **Use JQ filter `.[].filename`**: Extract just the filename field
3. **Correct endpoint**: `/repos/{owner}/{repo}/pulls/{number}/files`
4. **Error handling**: Handle API failures appropriately for context

## Implementation Locations

Successfully applied in:

- `.github/workflows/pr-validation.yml:118` (PowerShell inline)
- `.github/workflows/ai-session-protocol.yml:47` (Bash inline)
- `.github/scripts/AIReviewCommon.psm1:722-725` (PowerShell reusable function)

## Validation

**Test case**: PR #466 with 62 files, 25,666 total diff lines

**Before**: HTTP 406 failure
**After**: Successful file list retrieval

## Related Patterns

- [github-cli-api-patterns](github-cli-api-patterns.md) - General API usage
- [github-rest-api-reference](github-rest-api-reference.md) - Full API documentation
- [workflow-patterns-run-from-branch](workflow-patterns-run-from-branch.md) - Workflow resilience patterns

## When to Use

Use files API instead of `gh pr diff` when:

- Retrieving list of changed files in a PR
- PR size is unknown or potentially large
- Workflow must be resilient to PR size
- Pagination support is needed (>100 files)

## When NOT to Use

Use `gh pr diff` when:

- Need actual diff content (not just filenames)
- PR is guaranteed small (<20k lines)
- Performance is critical (files API requires pagination)
- Local git checkout is available (use `git diff` instead)

## API Details

**Endpoint**: `GET /repos/{owner}/{repo}/pulls/{pull_number}/files`

**Response fields**:

- `filename` - Path to changed file
- `status` - added, removed, modified, renamed
- `additions` - Lines added
- `deletions` - Lines deleted
- `changes` - Total changes
- `patch` - Unified diff (may be truncated)

**Pagination**: 100 files/page (default 30)
**Rate limit**: 5,000/hour (authenticated)

## Related

- [github-cli-001-bidirectional-issue-linking](github-cli-001-bidirectional-issue-linking.md)
- [github-cli-anti-patterns](github-cli-anti-patterns.md)
- [github-cli-api-patterns](github-cli-api-patterns.md)
- [github-cli-extensions](github-cli-extensions.md)
- [github-cli-issue-operations](github-cli-issue-operations.md)
