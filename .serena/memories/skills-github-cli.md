# GitHub CLI (gh) Skills and Patterns

## Overview

Comprehensive collection of GitHub CLI (`gh`) command patterns, best practices, and common pitfalls. These skills enable effective automation of GitHub operations from the command line and in CI/CD pipelines.

**Last Updated**: 2025-12-18
**Source**: GitHub REST API Documentation and GitHub CLI Manual

---

## Skill-GH-PR-001: Pull Request Creation

**Statement**: Use `gh pr create` with explicit flags for automation; use `--fill` for auto-population from commits.

**Pattern**:

```bash
# Interactive creation
gh pr create

# Automated creation with explicit values
gh pr create --base main --head feature-branch \
  --title "feat: add new feature" \
  --body "## Summary\n\nDescription here\n\nCloses #123"

# Auto-fill from commit messages
gh pr create --fill

# Create draft PR
gh pr create --draft --title "WIP: feature" --body "Work in progress"

# Link to issue (auto-closes on merge)
gh pr create --title "Fix bug" --body "Fixes #123"
```

**Atomicity**: 95%

---

## Skill-GH-PR-002: Pull Request Review

**Statement**: Use `gh pr review` with `-b` flag for body text; `-r` for request changes, `-a` for approve.

**Pattern**:

```bash
# Approve current branch's PR
gh pr review --approve

# Approve with comment
gh pr review --approve -b "LGTM! Great work."

# Request changes with feedback
gh pr review 123 -r -b "Please address the security concern in line 45"

# Leave comment (no approval/rejection)
gh pr review --comment -b "Interesting approach, have you considered..."

# Review specific PR
gh pr review 456 --approve
```

**Atomicity**: 93%

---

## Skill-GH-PR-003: Pull Request Merge

**Statement**: Use `gh pr merge` with `-s` for squash, `-d` for delete branch, `--auto` for auto-merge when checks pass.

**Pattern**:

```bash
# Squash and delete branch (most common)
gh pr merge -sd

# Auto-merge when checks pass (squash + delete)
gh pr merge --auto -sd

# Merge with merge commit
gh pr merge --merge

# Rebase merge
gh pr merge --rebase

# Merge specific PR
gh pr merge 123 -sd

# Disable auto-merge
gh pr merge 123 --disable-auto
```

**Anti-pattern**: Forgetting `-d` leaves stale branches.

**Atomicity**: 94%

---

## Skill-GH-PR-004: Pull Request Listing and Filtering

**Statement**: Use `gh pr list` with `--state`, `--label`, `--author` filters; `--json` for scripting.

**Pattern**:

```bash
# List open PRs (default)
gh pr list

# List PRs by state
gh pr list --state closed
gh pr list --state merged
gh pr list --state all

# Filter by author
gh pr list --author @me
gh pr list --author username

# Filter by label
gh pr list --label "bug"
gh pr list --label "needs-review"

# JSON output for scripting
gh pr list --json number,title,author --jq '.[] | "\(.number): \(.title)"'

# List PRs needing review
gh pr list --search "review:required"
```

**Atomicity**: 92%

---

## Skill-GH-Issue-001: Issue Creation

**Statement**: Use `gh issue create` with `--label`, `--assignee`, `--project` for rich metadata; `@me` for self-assignment.

**Pattern**:

```bash
# Interactive creation
gh issue create

# Full creation with metadata
gh issue create \
  --title "Bug: Login fails on Safari" \
  --body "## Steps to Reproduce\n\n1. Open Safari\n2. Click Login\n\n## Expected\nLogin succeeds" \
  --label "bug,high-priority" \
  --assignee "@me" \
  --milestone "v2.0"

# Assign to multiple users
gh issue create --title "Review needed" --assignee alice,bob,charlie

# Open in browser after creation
gh issue create --web

# Use template
gh issue create --template "Bug Report"

# Assign to Copilot
gh issue create --title "Analyze codebase" --assignee "@copilot"
```

**Atomicity**: 94%

---

## Skill-GH-Issue-002: Issue Editing and Management

**Statement**: Use `gh issue edit` for bulk operations; supports multiple issues and incremental label/assignee changes.

**Pattern**:

```bash
# Edit title and body
gh issue edit 23 --title "Updated title" --body "New description"

# Add labels (preserves existing)
gh issue edit 23 --add-label "bug,help-wanted"

# Remove labels
gh issue edit 23 --remove-label "wontfix"

# Change assignees
gh issue edit 23 --add-assignee "@me" --remove-assignee olduser

# Set milestone
gh issue edit 23 --milestone "v2.0"

# Edit multiple issues at once
gh issue edit 23 34 45 --add-label "needs-triage"

# Add to project
gh issue edit 23 --add-project "Roadmap"

# Body from file
gh issue edit 23 --body-file updated-description.md
```

**Note**: Adding labels to projects requires `gh auth refresh -s project`.

**Atomicity**: 93%

---

## Skill-GH-Issue-003: Issue Lifecycle

**Statement**: Use `gh issue close`, `gh issue reopen`, `gh issue lock` for lifecycle management.

**Pattern**:

```bash
# Close issue
gh issue close 23

# Close with comment
gh issue close 23 -c "Fixed in PR #45"

# Close as completed
gh issue close 23 -r completed

# Close as not planned
gh issue close 23 -r "not planned"

# Reopen closed issue
gh issue reopen 23

# Lock controversial issue
gh issue lock 23 -r "too heated"

# Unlock
gh issue unlock 23

# Pin important issue
gh issue pin 23

# Transfer to another repo
gh issue transfer 23 owner/other-repo
```

**Atomicity**: 91%

---

## Skill-GH-Run-001: Workflow Run Management

**Statement**: Use `gh run list` with `-w` for specific workflow, `--status` for filtering; `gh run view --log-failed` for debugging.

**Pattern**:

```bash
# List recent runs
gh run list

# List runs for specific workflow
gh run list -w "CI"
gh run list -w ci.yml

# Filter by status
gh run list --status failure
gh run list --status success
gh run list --status in_progress

# Limit results
gh run list -L 20

# View specific run
gh run view 12345678

# View with logs
gh run view 12345678 --log

# View only failed logs (best for debugging)
gh run view 12345678 --log-failed

# Watch running workflow
gh run watch 12345678

# Exit with error if run failed
gh run view 12345678 --exit-status && echo "Passed"

# Download artifacts
gh run download 12345678
gh run download 12345678 -n artifact-name
```

**Atomicity**: 94%

---

## Skill-GH-Run-002: Workflow Triggering

**Statement**: Use `gh workflow run` for manual triggers; workflow must have `workflow_dispatch` trigger.

**Pattern**:

```bash
# Trigger workflow (interactive selection)
gh workflow run

# Trigger specific workflow
gh workflow run deploy.yml

# Trigger with inputs
gh workflow run deploy.yml -f environment=staging -f version=1.2.3

# Trigger from specific branch
gh workflow run ci.yml --ref feature-branch

# Trigger with JSON inputs
gh workflow run build.yml --json -f '{"target": "linux", "debug": true}'

# View workflow definition
gh workflow view deploy.yml
gh workflow view deploy.yml --yaml

# Enable/disable workflow
gh workflow enable deploy.yml
gh workflow disable deprecated.yml
```

**Prerequisite**: Workflow must include `on: workflow_dispatch:` trigger.

**Atomicity**: 92%

---

## Skill-GH-Release-001: Release Creation

**Statement**: Use `gh release create` with `--generate-notes` for auto-changelog; attach assets with display labels using `#`.

**Pattern**:

```bash
# Interactive release
gh release create

# Create with auto-generated notes
gh release create v1.2.3 --generate-notes

# Create with notes file
gh release create v1.2.3 -F CHANGELOG.md

# Create with inline notes
gh release create v1.2.3 --notes "## Bug Fixes\n- Fixed login issue"

# Create draft release
gh release create v1.2.3 --draft

# Create prerelease
gh release create v1.2.3-beta.1 --prerelease

# Upload assets with display labels
gh release create v1.2.3 ./dist/*.tgz
gh release create v1.2.3 'app.zip#Application Bundle'

# Create from specific commit (not latest)
gh release create v1.2.3 --target abc1234

# Verify tag exists first
gh release create v1.2.3 --verify-tag

# Start discussion
gh release create v1.2.3 --discussion-category "Announcements"
```

**Atomicity**: 95%

---

## Skill-GH-Release-002: Release Asset Management

**Statement**: Use `gh release download` with `--pattern` for selective downloads; `gh release upload` for adding assets post-creation.

**Pattern**:

```bash
# Download all assets from specific release
gh release download v1.2.3

# Download by pattern (latest release)
gh release download --pattern '*.deb'
gh release download -p '*.deb' -p '*.rpm'

# Download source archive
gh release download v1.2.3 --archive=zip
gh release download v1.2.3 --archive=tar.gz

# Download to specific directory
gh release download v1.2.3 -D ./downloads/

# Upload additional assets
gh release upload v1.2.3 new-asset.zip

# Upload with display label
gh release upload v1.2.3 'checksums.txt#SHA256 Checksums'

# Overwrite existing asset
gh release upload v1.2.3 updated.zip --clobber

# List releases
gh release list

# View specific release
gh release view v1.2.3

# Delete release
gh release delete v1.2.3

# Delete with associated tag
gh release delete v1.2.3 --yes --cleanup-tag
```

**Atomicity**: 93%

---

## Skill-GH-API-001: Direct API Access

**Statement**: Use `gh api` for endpoints not covered by built-in commands; `--paginate` for complete results, `--jq` for filtering.

**Pattern**:

```bash
# Simple GET request
gh api repos/{owner}/{repo}/issues

# With path parameters
gh api repos/cli/cli/releases/latest

# POST request with data
gh api repos/{owner}/{repo}/issues -f title="Bug" -f body="Description"

# Custom headers
gh api -H "Accept: application/vnd.github+json" \
  -H "X-GitHub-Api-Version: 2022-11-28" \
  /repos/{owner}/{repo}/pulls

# Pagination (all results)
gh api --paginate repos/{owner}/{repo}/issues

# JSON filtering with jq
gh api repos/{owner}/{repo}/issues --jq '.[].title'
gh api repos/{owner}/{repo}/issues --jq '.[] | {number, title, state}'

# Slurp paginated results into single array
gh api --paginate --slurp repos/{owner}/{repo}/issues --jq 'flatten | length'

# Cache responses (performance)
gh api --cache 1h repos/{owner}/{repo}/contributors

# GraphQL queries
gh api graphql -f query='
  query {
    viewer {
      login
      repositories(first: 10) {
        nodes { name }
      }
    }
  }
'

# GraphQL with pagination
gh api graphql --paginate -f query='
  query($endCursor: String) {
    viewer {
      repositories(first: 100, after: $endCursor) {
        nodes { nameWithOwner }
        pageInfo { hasNextPage endCursor }
      }
    }
  }
'
```

**Atomicity**: 96%

---

## Skill-GH-Auth-001: Authentication Management

**Statement**: Use `gh auth login` with `--scopes` for minimal permissions; `gh auth refresh` to add scopes without re-login.

**Pattern**:

```bash
# Interactive login (browser)
gh auth login

# Login with token
echo $GITHUB_TOKEN | gh auth login --with-token

# Login to enterprise
gh auth login --hostname github.mycompany.com

# Add additional scopes
gh auth refresh -s workflow
gh auth refresh -s project
gh auth refresh -s read:packages

# Check auth status
gh auth status

# View token
gh auth token

# Logout
gh auth logout

# Switch accounts
gh auth switch
```

**Required Scopes**:

- Minimum: `repo`, `read:org`, `gist`
- Workflows: Add `workflow`
- Projects: Add `project`
- Packages: Add `read:packages` or `write:packages`

**Atomicity**: 91%

---

## Skill-GH-JSON-001: JSON Output and jq Patterns

**Statement**: Use `--json` flag with field names, pipe to `jq` for complex transformations.

**Pattern**:

```bash
# Basic JSON output
gh pr list --json number,title,author

# With jq filtering
gh pr list --json number,title --jq '.[].title'

# Complex jq transformation
gh pr list --json number,title,labels \
  --jq '.[] | select(.labels | any(.name == "bug")) | .number'

# Extract specific fields
gh issue list --json number,title,state \
  --jq '.[] | "\(.number): \(.title) [\(.state)]"'

# Count items
gh pr list --json number --jq 'length'

# Filter by condition
gh run list --json status,conclusion,name \
  --jq '.[] | select(.conclusion == "failure")'

# Sort results
gh release list --json tagName,publishedAt \
  --jq 'sort_by(.publishedAt) | reverse | .[0]'

# Raw output (no quotes)
gh pr view 123 --json title --jq -r '.title'

# Multiple field extraction
gh api repos/{owner}/{repo} --jq '{name, stars: .stargazers_count, forks: .forks_count}'
```

**Atomicity**: 94%

---

## Common Pitfalls and Anti-Patterns

### Anti-Pattern-GH-001: Repository Rename Silent Failures

**Problem**: After a repository is renamed on GitHub, `gh` commands may fail silently in non-interactive scripts while working in terminals.

**Cause**: GitHub's automatic redirects work interactively but not in scripts.

**Solution**: Update local git remote URL after repo renames:

```bash
git remote set-url origin git@github.com:owner/new-repo-name.git
```

### Anti-Pattern-GH-002: Using GITHUB_TOKEN for workflow_run

**Problem**: `gh workflow run` in GitHub Actions with `GITHUB_TOKEN` causes panic errors.

**Cause**: `GITHUB_TOKEN` has limitations to prevent recursive actions.

**Solution**: Use a Personal Access Token (PAT) with `workflow` scope:

```yaml
env:
  GH_TOKEN: ${{ secrets.PAT_WITH_WORKFLOW_SCOPE }}
```

### Anti-Pattern-GH-003: Running Commands Outside Repositories

**Problem**: Many `gh` commands fail with unhelpful errors when run outside a git repository.

**Solution**: Either:

1. Change to a repository directory first
2. Use `-R owner/repo` flag to specify repository

```bash
gh pr list -R cli/cli
gh issue view 123 -R owner/repo
```

### Anti-Pattern-GH-004: Expecting Pagination by Default

**Problem**: List commands only return 30 items by default.

**Solution**: Use `--limit` or `--paginate`:

```bash
# Get more results
gh pr list -L 100

# Get all results (API commands)
gh api --paginate repos/{owner}/{repo}/issues
```

### Anti-Pattern-GH-005: Using gh pr view for Review Threads

**Problem**: `gh pr view --json reviewThreads` fails with "Unknown JSON field".

**Cause**: The `gh pr view` command does not support the `reviewThreads` field, even though it's part of the GitHub API.

**Solution**: Use GraphQL API for review thread operations:

```bash
# Query review threads (only way to get them)
gh api graphql -f query='
query($owner: String!, $repo: String!, $number: Int!) {
  repository(owner: $owner, name: $repo) {
    pullRequest(number: $number) {
      reviewThreads(first: 100) {
        nodes {
          id
          isResolved
          path
          comments(first: 3) { nodes { id body author { login } } }
        }
      }
    }
  }
}' -f owner=OWNER -f repo=REPO -F number=PR_NUMBER

# Reply to thread (GraphQL only)
gh api graphql -f query='mutation($id: ID!, $body: String!) {
  addPullRequestReviewThreadReply(input: {pullRequestReviewThreadId: $id, body: $body}) {
    comment { id }
  }
}' -f id="PRRT_xxx" -f body="Reply"

# Resolve thread (GraphQL only - no REST equivalent)
gh api graphql -f query='mutation($id: ID!) {
  resolveReviewThread(input: {threadId: $id}) { thread { isResolved } }
}' -f id="PRRT_xxx"
```

**Note**: See `skills-pr-review` for the complete PR review workflow.

### Anti-Pattern-GH-006: Direct Token Storage

**Problem**: Storing PATs in plain text (.env, .Renviron, scripts).

**Solution**: Use `gh auth` credential store or secure secrets management:

```bash
# Token is securely stored by gh
gh auth login

# In CI, use secrets
env:
  GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
```

---

## Rate Limiting Guidelines

### Limits by Authentication

| Auth Type | Limit |
|-----------|-------|
| Unauthenticated | 60 requests/hour |
| PAT/OAuth | 5,000 requests/hour |
| GitHub App | 5,000-15,000 requests/hour |
| GITHUB_TOKEN (Actions) | 1,000 requests/hour/repo |
| Enterprise Cloud | 15,000 requests/hour |

### Monitoring Rate Limits

```bash
# Check remaining requests
gh api rate_limit --jq '.resources.core'

# Response headers
# x-ratelimit-limit: Maximum allowed
# x-ratelimit-remaining: Remaining requests
# x-ratelimit-reset: Reset time (Unix epoch)
```

### Best Practices

1. **Cache responses**: Use `gh api --cache 1h` for repeated queries
2. **Batch operations**: Combine API calls where possible
3. **Use conditional requests**: Check `ETag`/`If-Modified-Since`
4. **Handle 403/429**: Implement exponential backoff

---

## CI/CD Integration Patterns

### GitHub Actions Setup

```yaml
jobs:
  example:
    runs-on: ubuntu-latest
    env:
      GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
    steps:
      - uses: actions/checkout@v4
      - name: Create PR comment
        run: gh pr comment ${{ github.event.pull_request.number }} --body "CI passed!"
```

### Environment Variable Precedence

1. `GH_TOKEN` (highest priority)
2. `GITHUB_TOKEN`
3. Stored credentials from `gh auth login`

### Safe Variable Handling

```yaml
# GOOD: Use env vars for user content
env:
  PR_BODY: ${{ github.event.pull_request.body }}
run: |
  gh pr comment $PR_NUMBER --body "$PR_BODY"

# BAD: Direct interpolation (injection risk)
run: |
  gh pr comment ${{ github.event.pull_request.number }} --body "${{ github.event.pull_request.body }}"
```

---

## Related Memories

- `skills-github-workflow-patterns.md` - GitHub Actions workflow patterns
- `skills-ci-infrastructure.md` - CI/CD infrastructure skills

## References

- [GitHub CLI Manual](https://cli.github.com/manual/)
- [GitHub REST API Documentation](https://docs.github.com/en/rest)
- [GitHub CLI Examples](https://cli.github.com/manual/examples)
