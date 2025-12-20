# PR Review Skills

Collection of proven strategies for GitHub pull request review and merge workflows in rjmurillo/ai-agents.

---

## Skill-PR-Review-001

**Statement**: Before merging a PR in rjmurillo/ai-agents, ALL review conversations MUST be resolved. Unresolved threads block the merge due to branch protection rules.

**Context**: GitHub PR review and merge workflow

**Evidence**: Maintainer guidance from 2025-12-20 session - branch protection rules require conversation resolution before merge.

**Atomicity**: 95%

**Tag**: helpful

**Impact**: 9/10

**Created**: 2025-12-19

**Validated**: 2

**Pattern**:

```bash
# Check for unresolved conversations before attempting merge
# NOTE: gh pr view does NOT support reviewThreads - must use GraphQL API
gh api graphql -f query='
query($owner: String!, $repo: String!, $number: Int!) {
  repository(owner: $owner, name: $repo) {
    pullRequest(number: $number) {
      reviewThreads(first: 100) {
        nodes {
          isResolved
          path
          line
          comments(first: 3) {
            nodes { body author { login } }
          }
        }
      }
    }
  }
}' -f owner=OWNER -f repo=REPO -F number=PR_NUMBER

# Filter to show only unresolved threads with jq:
# | jq '.data.repository.pullRequest.reviewThreads.nodes[] | select(.isResolved == false)'
```

**Invalid Pattern** (does not work):

```bash
# This fails - reviewThreads is not a valid field for gh pr view
gh pr view <PR_NUMBER> --json reviewThreads  # ERROR: Unknown JSON field
```

**Anti-Pattern**:

- Attempting to merge with unresolved conversations → merge will be blocked
- Using `--admin` flag to bypass → violates repository policy

**Related Skills**: None yet

**Notes**:

- This is a hard requirement enforced by branch protection
- Applies to all PRs in rjmurillo/ai-agents repository
- Resolution must happen before merge attempt
- The GraphQL API is the only way to access reviewThreads programmatically
