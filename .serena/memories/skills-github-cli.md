# GitHub CLI (gh) Skills and Patterns

## Overview

Comprehensive collection of GitHub CLI (`gh`) command patterns, best practices, and common pitfalls. These skills enable effective automation of GitHub operations from the command line and in CI/CD pipelines.

**Last Updated**: 2025-12-19
**Source**: GitHub REST API Documentation, GitHub CLI Manual, and GitHub Copilot Integration

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

# Assign to GitHub Copilot (triggers automated resolution)
gh issue create --title "Analyze codebase" --assignee "copilot-swe-agent"
```

**Note**: Copilot assignee must be `copilot-swe-agent` (exact name). Using `@copilot`, `Copilot`, or `copilot` will fail. See Skill-GH-Copilot-001 below for details.

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

## Skill-GH-Copilot-001: GitHub Copilot Assignment

**Statement**: Assign issues to `copilot-swe-agent` (exact name) to trigger GitHub Copilot automated resolution.

**Context**: When requesting GitHub Copilot to automatically analyze and resolve issues.

**Pattern**:

```bash
# Correct: Trigger Copilot with exact assignee name
gh issue edit 90 --add-assignee copilot-swe-agent

# Create issue and assign to Copilot
gh issue create --title "Analyze build failures" --assignee copilot-swe-agent

# WRONG: These do NOT trigger Copilot to work on the issue
gh issue comment 90 --body "@copilot please analyze"  # Mentions don't ASSIGN, but DO add context
gh issue edit 90 --add-assignee Copilot               # Error: 'Copilot' not found
gh issue edit 90 --add-assignee copilot               # Error: 'copilot' not found
gh issue edit 90 --add-assignee @copilot              # Wrong format
```

**Critical Details**:

- Assignee name must be exactly `copilot-swe-agent` (case-sensitive)
- Assignment is the ONLY trigger mechanism for Copilot to START working
- Use `@copilot` only in comment bodies to mention Copilot; these mentions add context but do **not** assign the issue
- Common assignee-name mistakes (these FAIL when used with `--assignee` / `--add-assignee`): `Copilot`, `copilot`, `@copilot`

**Context Injection Pattern**:
```bash
# Step 1: Post context-rich comment mentioning @copilot
gh issue comment 90 --body "@copilot Use Option 1 from the issue description. Focus on the Apply Labels step. The workflow already has issues:write permission."

# Step 2: Assign Copilot (this triggers work)
gh issue edit 90 --add-assignee copilot-swe-agent
```

When Copilot is assigned, it reads ALL comments where @copilot is mentioned and incorporates them into its context.

**Evidence**:

- Issue #88: Successful pattern with `copilot-swe-agent`
- Issue #90: Failed with "Copilot" and "copilot", succeeded with `copilot-swe-agent`
- Error message: "failed to update: 'Copilot' not found"

**Atomicity**: 98%

**Impact**: 9/10

**Tag**: helpful

**Validated**: 2 (Issues #88, #90)

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

---

## Repository Management Skills

### Skill-GH-Repo-001: Repository Settings Management

**Statement**: Use `gh repo edit` with feature flags to enable/disable repo features; use `--visibility` with acknowledgment flag for visibility changes.

**Pattern**:

```bash
# Enable/disable features
gh repo edit --enable-discussions --enable-projects
gh repo edit --enable-squash-merge --delete-branch-on-merge
gh repo edit --enable-issues=false

# Security features
gh repo edit --enable-advanced-security
gh repo edit --enable-secret-scanning --enable-secret-scanning-push-protection

# Change visibility (requires acknowledgment)
gh repo edit --visibility private --accept-visibility-change-consequences

# Update metadata
gh repo edit --description "New description" --homepage "https://example.com"
gh repo edit --add-topic "ci,automation" --remove-topic "wip"

# Set default branch
gh repo edit --default-branch main

# Make template repository
gh repo edit --template
```

**Atomicity**: 94%

---

### Skill-GH-Repo-002: Fork Synchronization

**Statement**: Use `gh repo sync` to keep forks current with upstream; `--force` for hard reset when fast-forward fails.

**Pattern**:

```bash
# Sync local fork with parent (default)
gh repo sync

# Sync specific branch
gh repo sync --branch v1

# Sync remote fork
gh repo sync owner/fork-repo

# Force sync (hard reset - overwrites local changes)
gh repo sync --force

# Sync from different source
gh repo sync owner/repo --source upstream/repo
```

**Atomicity**: 92%

---

### Skill-GH-Repo-003: Deploy Key Management

**Statement**: Use `gh repo deploy-key` for CI/CD SSH key management; add with write permission for deployment workflows.

**Pattern**:

```bash
# List deploy keys
gh repo deploy-key list

# Add deploy key with title
gh repo deploy-key add ~/.ssh/deploy_key.pub --title "CI/CD Key"

# Add with write permission (for pushing)
gh repo deploy-key add key.pub --title "Deploy Key" --allow-write

# Delete deploy key by ID
gh repo deploy-key delete 12345

# Target different repo
gh repo deploy-key list -R owner/other-repo
```

**Atomicity**: 91%

---

### Skill-GH-Repo-004: Repository Lifecycle

**Statement**: Use `gh repo archive` to deprecate repositories while preserving history; `gh repo unarchive` to reactivate.

**Pattern**:

```bash
# Archive repository (read-only, preserves history)
gh repo archive owner/repo

# Unarchive repository (reactivate)
gh repo unarchive owner/repo

# Rename repository
gh repo rename old-name new-name

# Delete repository (DESTRUCTIVE - requires confirmation)
gh repo delete owner/repo --yes

# Set default repo for commands in current directory
gh repo set-default owner/repo
```

**Anti-pattern**: Deleting repos instead of archiving loses history and breaks links.

**Atomicity**: 90%

---

## Secret and Variable Management

### Skill-GH-Secret-001: Secret Management

**Statement**: Use `gh secret set` with `-f` for batch import from .env files; use `--visibility` for org-level access control.

**Pattern**:

```bash
# Set repo secret (interactive prompt)
gh secret set MY_SECRET

# Set from value
gh secret set API_KEY --body "secret-value"

# Set from file (pipe stdin)
gh secret set SSH_KEY < ~/.ssh/id_rsa

# Batch import from .env file
gh secret set -f .env.production

# Environment-specific secret
gh secret set DB_PASSWORD --env production

# Org secret with visibility control
gh secret set ORG_SECRET --org myorg --visibility all
gh secret set ORG_SECRET --org myorg --visibility private
gh secret set SHARED_SECRET --org myorg --repos repo1,repo2

# Dependabot secret
gh secret set NUGET_TOKEN --app dependabot

# Codespaces secret
gh secret set DEV_TOKEN --user

# List secrets
gh secret list
gh secret list --org myorg
gh secret list --env production

# Delete secret
gh secret delete MY_SECRET
gh secret delete --env production DB_PASSWORD
```

**Security Note**: Values are locally encrypted before transmission to GitHub.

**Atomicity**: 95%

---

### Skill-GH-Variable-001: Variable Management

**Statement**: Use `gh variable` for non-sensitive config values; supports repo/env/org scopes like secrets.

**Pattern**:

```bash
# Set variable
gh variable set MY_VAR --body "value"

# Get variable value
gh variable get MY_VAR

# List variables
gh variable list

# Environment-specific
gh variable set DEBUG --env staging --body "true"

# Organization variable
gh variable set ORG_SETTING --org myorg --repos repo1,repo2

# Delete variable
gh variable delete MY_VAR
```

**Anti-pattern**: Using `gh variable` for sensitive data exposes values in logs. Always use `gh secret` for credentials.

**Atomicity**: 93%

---

## Label Management

### Skill-GH-Label-001: Label Creation and Editing

**Statement**: Use `gh label create` with `--color` (hex) and `--description`; use `--force` to update existing labels.

**Pattern**:

```bash
# Create label with color and description
gh label create "bug" --color E99695 --description "Something isn't working"

# Create priority labels
gh label create "priority:critical" --color FF0000 --description "Critical priority"
gh label create "priority:high" --color FFA500 --description "High priority"
gh label create "priority:medium" --color FFFF00 --description "Medium priority"
gh label create "priority:low" --color 00FF00 --description "Low priority"

# Create type labels
gh label create "type:feature" --color 0E8A16 --description "New feature request"
gh label create "type:bug" --color D93F0B --description "Bug report"
gh label create "type:docs" --color 0075CA --description "Documentation"

# Update existing label (force flag)
gh label create "bug" --color FF0000 --force

# Edit label properties
gh label edit "bug" --color FF0000 --description "Updated description"
gh label edit "old-name" --name "new-name"

# List all labels
gh label list
gh label list --json name,color,description

# Delete label
gh label delete "obsolete-label" --yes
```

**Note**: Color values require exactly 6 hexadecimal characters (no # prefix).

**Atomicity**: 94%

---

### Skill-GH-Label-002: Label Cloning

**Statement**: Use `gh label clone` to copy label sets between repositories; essential for standardizing labels across organizations.

**Pattern**:

```bash
# Clone labels from source to current repo
gh label clone source-owner/source-repo

# Clone to specific target
gh label clone source-owner/template-repo -R target-owner/target-repo

# Overwrite existing labels
gh label clone source-owner/template-repo --force
```

**Best Practice**: Maintain a template repository with standard labels and clone to new repos.

**Atomicity**: 91%

---

## GitHub Actions Cache Management

### Skill-GH-Cache-001: Actions Cache Management

**Statement**: Use `gh cache list` to audit cache usage; `gh cache delete --all` to clear cache and reclaim storage.

**Pattern**:

```bash
# List all caches
gh cache list

# List with details for scripting
gh cache list --json id,key,sizeInBytes,createdAt

# Sort by size (find largest caches)
gh cache list --json key,sizeInBytes --jq 'sort_by(.sizeInBytes) | reverse | .[:5]'

# Delete specific cache by key
gh cache delete "npm-cache-ubuntu-abc123"

# Delete all caches (reclaim storage)
gh cache delete --all

# Target different repo
gh cache list -R owner/other-repo
gh cache delete --all -R owner/other-repo
```

**Use Case**: Clear caches when builds are failing due to stale dependencies or to reduce storage costs.

**Atomicity**: 90%

---

## Ruleset Management

### Skill-GH-Ruleset-001: Ruleset Compliance

**Statement**: Use `gh ruleset check` to validate branch compliance before pushing; `gh ruleset list` to audit governance rules.

**Pattern**:

```bash
# Check if branch complies with rulesets
gh ruleset check feature-branch
gh ruleset check main

# List all rulesets
gh ruleset list

# View specific ruleset details
gh ruleset view
gh ruleset view --web

# Check ruleset for different repo
gh ruleset list -R owner/repo
gh ruleset check main -R owner/repo
```

**Alias**: `gh rs` (shorthand for ruleset commands)

**Use Case**: Pre-flight check before force pushing or creating protected branch PRs.

**Atomicity**: 89%

---

## Software Supply Chain Security

### Skill-GH-Attestation-001: Artifact Verification

**Statement**: Use `gh attestation verify` with `--owner` or `--repo` to validate artifact provenance; essential for secure deployments.

**Pattern**:

```bash
# Verify artifact from repo
gh attestation verify artifact.bin --repo owner/repo

# Verify with organization scope
gh attestation verify artifact.bin --owner myorg

# Verify OCI container image
gh attestation verify oci://ghcr.io/owner/image:tag --owner owner

# Verify with specific workflow enforcement
gh attestation verify artifact.bin --owner org --signer-workflow .github/workflows/build.yml

# JSON output for CI integration
gh attestation verify artifact.bin --repo owner/repo --format json

# Offline verification with local attestation bundle
gh attestation verify artifact.bin --bundle attestation.jsonl --owner owner

# Download attestations for later verification
gh attestation download artifact.bin --owner owner
```

**Alias**: `gh at` (shorthand for attestation commands)

**Security Note**: Only signature.certificate and verifiedTimestamps are tamper-resistant. Predicate contents can be modified by workflow actors.

**Atomicity**: 93%

---

## GitHub Projects (v2)

### Skill-GH-Project-001: Project Management

**Statement**: Use `gh project` for GitHub Projects (v2); requires `project` scope via `gh auth refresh -s project`.

**Prerequisite**:
```bash
# Add project scope before using project commands
gh auth refresh -s project
gh auth status  # Verify scope added
```

**Pattern**:

```bash
# Create project
gh project create --owner myorg --title "Q1 Roadmap"

# List projects
gh project list
gh project list --owner myorg

# View project (opens in browser)
gh project view 1 --owner myorg --web

# Edit project
gh project edit 1 --owner myorg --title "Updated Title"

# Close project
gh project close 1 --owner myorg

# Delete project
gh project delete 1 --owner myorg

# Copy project (template)
gh project copy 1 --source-owner source-org --target-owner target-org --title "Copy"

# Mark as template
gh project mark-template 1 --owner myorg

# Link repository to project
gh project link 1 --owner myorg --repo myorg/myrepo

# Unlink repository
gh project unlink 1 --owner myorg --repo myorg/myrepo
```

**Atomicity**: 92%

---

### Skill-GH-Project-002: Project Item Management

**Statement**: Use `gh project item-add` to add issues/PRs to projects; `gh project field-list` to manage custom fields.

**Pattern**:

```bash
# Add issue/PR to project by URL
gh project item-add 1 --owner myorg --url https://github.com/myorg/repo/issues/123

# List project items
gh project item-list 1 --owner myorg
gh project item-list 1 --owner myorg --json id,title,status

# Create draft item (no linked issue)
gh project item-create 1 --owner myorg --title "New task" --body "Description"

# Edit item field
gh project item-edit --id ITEM_ID --field-id FIELD_ID --text "value"
gh project item-edit --id ITEM_ID --field-id STATUS_FIELD_ID --single-select-option-id OPTION_ID

# Archive item
gh project item-archive 1 --owner myorg --id ITEM_ID

# Delete item
gh project item-delete 1 --owner myorg --id ITEM_ID

# List custom fields
gh project field-list 1 --owner myorg

# Create custom field
gh project field-create 1 --owner myorg --name "Priority" --data-type "SINGLE_SELECT"

# Delete custom field
gh project field-delete 1 --owner myorg --id FIELD_ID
```

**Atomicity**: 91%

---

## CLI Extensions

### Skill-GH-Extension-001: Extension Management

**Statement**: Use `gh extension` to install community tools that extend gh functionality; extensions are repos with `gh-` prefix.

**Pattern**:

```bash
# Search for extensions
gh extension search sub-issue
gh extension search copilot

# Browse extensions in browser
gh extension browse

# Install extension
gh extension install owner/gh-extension-name
gh extension install github/gh-copilot

# List installed extensions
gh extension list

# Upgrade single extension
gh extension upgrade extension-name

# Upgrade all extensions
gh extension upgrade --all

# Remove extension
gh extension remove extension-name

# Run extension (useful for name conflicts)
gh extension exec extension-name [args]

# Create new extension (for development)
gh extension create my-extension
```

**Extension Directory**: https://github.com/topics/gh-extension

**Aliases**: `gh ext`, `gh extensions`

**Atomicity**: 92%

---

### Skill-GH-Extension-002: Sub-Issue Management (via Extension)

**Statement**: Install `gh-sub-issue` extension to manage hierarchical issue relationships from CLI.

**Important**: Sub-issues are NOT in core gh CLI - requires community extension.

**Installation**:
```bash
gh extension install yahsan2/gh-sub-issue
```

**Pattern**:

```bash
# Create new sub-issue linked to parent
gh sub-issue create --parent 123 --title "Sub-task for parent issue"

# Link existing issue as sub-issue
gh sub-issue add 123 456  # 123=parent, 456=child

# List sub-issues of a parent
gh sub-issue list 123

# Remove sub-issue link
gh sub-issue remove 123 456

# JSON output for scripting
gh sub-issue list 123 --json
```

**Native Alternative**: Use GitHub REST API for sub-issues if extension not available:
```bash
# Add sub-issue via API
gh api repos/{owner}/{repo}/issues/{parent}/sub_issues -f sub_issue_id={child_id}

# List sub-issues via API
gh api repos/{owner}/{repo}/issues/{parent}/sub_issues
```

**Note**: GitHub supports up to 8 levels of issue hierarchy.

**Atomicity**: 90%

---

## Additional Anti-Patterns

### Anti-Pattern-GH-006: Ignoring Ruleset Compliance

**Problem**: Pushing without checking ruleset compliance causes CI failures and frustration.

**Solution**: Run `gh ruleset check branch-name` before pushing to protected branches.

```bash
# Pre-push check
gh ruleset check my-branch && git push origin my-branch
```

### Anti-Pattern-GH-007: Hardcoding Secrets in Variables

**Problem**: Using `gh variable` for sensitive data exposes secrets in workflow logs and API responses.

**Solution**: Always use `gh secret` for credentials, tokens, and sensitive values. Variables are for non-sensitive configuration only.

```bash
# WRONG: Exposes in logs
gh variable set API_KEY --body "sk-secret123"

# CORRECT: Encrypted and masked
gh secret set API_KEY --body "sk-secret123"
```

### Anti-Pattern-GH-008: Missing Project Scope

**Problem**: Project commands fail with 403 permission errors.

**Solution**: Add project scope before using project commands:

```bash
gh auth refresh -s project
```

### Anti-Pattern-GH-009: Not Using Label Templates

**Problem**: Manually creating labels in each repository leads to inconsistency.

**Solution**: Maintain a template repository with standard labels and use `gh label clone`:

```bash
# Clone from template repo to new repo
gh label clone org/label-template -R org/new-repo
```

---

## Recommended Extensions for Maintainers

The following community extensions significantly enhance maintainer productivity. Install with `gh extension install <repo>`.

### Skill-GH-Ext-Dash-001: Interactive PR/Issue Dashboard

**Extension**: `dlvhdr/gh-dash`

**Statement**: Use `gh dash` for a keyboard-driven TUI to manage PRs and issues without leaving the terminal.

**Installation**:

```bash
gh extension install dlvhdr/gh-dash
```

**Configuration** (`~/.config/gh-dash/config.yml`):

```yaml
prSections:
  - title: My PRs
    filters: is:open author:@me
  - title: Needs Review
    filters: is:open review-requested:@me
  - title: Team PRs
    filters: is:open org:myorg

issuesSections:
  - title: Assigned
    filters: is:open assignee:@me
  - title: High Priority
    filters: is:open label:priority:high
```

**Pattern**:

```bash
# Launch dashboard
gh dash

# Key bindings (vim-style):
# j/k - Navigate up/down
# Enter - View details
# d - View diff
# c - Checkout branch
# m - Merge PR
# o - Open in browser
# r - Refresh
# q - Quit
```

**Use Case**: Monitor multiple repositories, triage PRs, and perform actions without context switching to browser.

**Atomicity**: 94%

---

### Skill-GH-Ext-Combine-001: Batch Dependabot PRs

**Extension**: `rnorth/gh-combine-prs`

**Statement**: Use `gh combine-prs` to merge multiple PRs (especially Dependabot) into a single PR for cleaner history.

**Prerequisites**: Requires `jq` installed.

**Installation**:

```bash
gh extension install rnorth/gh-combine-prs
```

**Pattern**:

```bash
# Combine all Dependabot PRs
gh combine-prs --query "author:app/dependabot"

# Combine specific PRs by number
gh combine-prs --query "author:app/dependabot" --selected-pr-numbers "12,34,56"

# Limit number of PRs combined
gh combine-prs --query "author:app/dependabot" --limit 10

# Skip status checks (use with caution)
gh combine-prs --query "author:app/dependabot" --skip-pr-check

# Combine PRs by label
gh combine-prs --query "label:dependencies"
```

**Important**: When merging the combined PR, use **Merge Commit** (not squash) so GitHub marks original PRs as merged.

**Use Case**: Reduce PR noise from Dependabot by batching weekly dependency updates.

**Atomicity**: 93%

---

### Skill-GH-Ext-Metrics-001: PR Analytics

**Extension**: `hectcastro/gh-metrics`

**Statement**: Use `gh metrics` to calculate PR review metrics for identifying bottlenecks and improving team velocity.

**Installation**:

```bash
gh extension install hectcastro/gh-metrics
```

**Metrics Calculated**:

- **Time to First Review**: PR creation → first review
- **Feature Lead Time**: First commit → merge
- **First to Last Review**: First → final approval
- **First Approval to Merge**: Approval → merge

**Pattern**:

```bash
# Default metrics (last 10 days)
gh metrics --repo owner/repo

# Custom date range
gh metrics --repo owner/repo --start 2025-01-01 --end 2025-01-31

# Filter by author
gh metrics --repo owner/repo --query "author:username"

# CSV export for analysis
gh metrics --repo owner/repo --csv > metrics.csv

# Multiple repos
gh metrics --repo owner/repo1 --repo owner/repo2
```

**Use Case**: Track team health, identify slow reviewers, and benchmark sprint performance.

**Atomicity**: 91%

---

### Skill-GH-Ext-Notify-001: Notification Management

**Extension**: `meiji163/gh-notify`

**Statement**: Use `gh notify` with fzf integration for interactive notification triage from CLI.

**Prerequisites**: Optional but recommended: `fzf` for interactive mode.

**Installation**:

```bash
gh extension install meiji163/gh-notify
```

**Pattern**:

```bash
# Interactive mode (requires fzf)
gh notify

# List all notifications
gh notify -a

# Only participating/mentioned
gh notify -p

# Filter by pattern (regex)
gh notify -f "security"

# Exclude pattern
gh notify -e "dependabot"

# Limit results
gh notify -n 20

# Mark all as read
gh notify -r

# Static mode (no interaction)
gh notify -s

# Enable preview window
gh notify -w
```

**Interactive Key Bindings**:

- `Enter` - View in pager
- `Ctrl+A` - Mark all as read
- `Ctrl+D` - View diff
- `Ctrl+T` - Mark selected as read
- `Ctrl+X` - Write comment
- `Esc` - Exit

**Use Case**: Triage notifications without browser, quickly dismiss noise, focus on important items.

**Atomicity**: 92%

---

### Skill-GH-Ext-Milestone-001: Milestone Management

**Extension**: `valeriobelli/gh-milestone`

**Statement**: Use `gh milestone` for release planning with create/list/edit/delete operations.

**Installation**:

```bash
gh extension install valeriobelli/gh-milestone
```

**Pattern**:

```bash
# Create milestone (interactive)
gh milestone create

# Create with flags
gh milestone create --title "v2.0.0" --description "Major release" --due-date 2025-03-01

# List milestones
gh milestone list
gh milestone ls  # Alias
gh milestone list --state closed
gh milestone list --state all

# Filter and format
gh milestone list --query "v2"
gh milestone list --json id,title,progressPercentage

# View milestone
gh milestone view 1

# Edit milestone
gh milestone edit 1 --title "v2.0.0-rc1" --due-date 2025-02-15

# Delete milestone (with confirmation)
gh milestone delete 1

# Delete without prompt
gh milestone delete 1 --confirm

# Target different repo
gh milestone list --repo owner/repo
```

**Use Case**: Plan releases, track sprint progress, set deadlines for issue groupings.

**Atomicity**: 93%

---

### Skill-GH-Ext-Hook-001: Webhook Management

**Extension**: `lucasmelin/gh-hook`

**Statement**: Use `gh hook` for interactive webhook setup and management.

**Installation**:

```bash
gh extension install lucasmelin/gh-hook
```

**Pattern**:

```bash
# Create webhook (interactive TUI)
gh hook create

# Create from JSON file
gh hook create --file webhook.json

# List webhooks
gh hook list

# Delete webhook
gh hook delete <webhook-id>
```

**JSON Configuration Format**:

```json
{
  "active": true,
  "events": ["push", "pull_request"],
  "config": {
    "url": "https://example.com/webhook",
    "content_type": "json",
    "insecure_ssl": "0",
    "secret": "optional-secret"
  }
}
```

**Use Case**: Set up CI/CD integrations, Slack notifications, or external service triggers.

**Atomicity**: 89%

---

### Skill-GH-Ext-GR-001: Multi-Repository Operations

**Extension**: `sarumaj/gh-gr`

**Statement**: Use `gh gr` to manage multiple repositories simultaneously: pull, push, and status across repos.

**Installation**:

```bash
gh extension install sarumaj/gh-gr
```

**Pattern**:

```bash
# Initialize with directory
gh gr init -d ~/projects

# Initialize with concurrency limit
gh gr init -d ~/projects -c 10

# Exclude repos by pattern
gh gr init -d ~/projects -e ".*-archive" -e "fork-.*"

# Pull all repos
gh gr pull

# Check status of all repos
gh gr status

# Push all repos
gh gr push

# View configuration
gh gr view

# Export/import config
gh gr export > config.json
gh gr import < config.json

# Cleanup untracked local repos
gh gr cleanup
```

**Global Options**:

- `-c, --concurrency N` - Parallel operations (default: 12)
- `-t, --timeout DURATION` - Max time for operations (default: 10m)

**Use Case**: Maintain multiple related repositories, sync forks, batch operations across org.

**Atomicity**: 90%

---

### Skill-GH-Ext-Grep-001: Cross-Repository Code Search

**Extension**: `k1LoW/gh-grep`

**Statement**: Use `gh grep` to search code patterns across repositories via GitHub API.

**Installation**:

```bash
gh extension install k1LoW/gh-grep
```

**Pattern**:

```bash
# Search in specific repo
gh grep "TODO" --repo owner/repo

# Search with owner scope (all repos)
gh grep "deprecated" --owner myorg

# Filter by file pattern (IMPORTANT for performance)
gh grep "FROM.*alpine" --owner myorg --include "Dockerfile"

# Exclude files
gh grep "password" --repo owner/repo --exclude "*test*"

# Case insensitive with line numbers
gh grep -i -n "fixme" --repo owner/repo

# Output with GitHub URLs
gh grep "security" --repo owner/repo --url
```

**Performance Warning**: This tool is slow because it uses GitHub API. Always use `--include` to filter files.

**Use Case**: Audit patterns across org (security, deprecated APIs, license headers).

**Atomicity**: 88%

---

## Extension Maintenance

### Update All Extensions

```bash
gh extension upgrade --all
```

### List Installed Extensions

```bash
gh extension list
```

### Remove Extension

```bash
gh extension remove extension-name
```

### Find New Extensions

```bash
gh extension search keyword
gh extension browse  # Opens browser
```

---

## References

- [GitHub CLI Manual](https://cli.github.com/manual/)
- [GitHub REST API Documentation](https://docs.github.com/en/rest)
- [GitHub CLI Examples](https://cli.github.com/manual/examples)
- [GitHub CLI Extensions](https://github.com/topics/gh-extension)
- [GitHub Sub-Issues Documentation](https://docs.github.com/en/issues/tracking-your-work-with-issues/using-issues/adding-sub-issues)
- [Awesome gh CLI Extensions](https://github.com/kodepandai/awesome-gh-cli-extensions)
