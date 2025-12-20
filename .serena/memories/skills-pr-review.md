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

**Validated**: 1

**Pattern**:

```bash
# Check for unresolved conversations before attempting merge
gh pr view <PR_NUMBER> --json reviewThreads --jq '.reviewThreads[] | select(.isResolved == false)'

# If output is non-empty, conversations need resolution
# Address each comment, then mark as resolved in GitHub UI or via API
```

**Anti-Pattern**:

- Attempting to merge with unresolved conversations → merge will be blocked
- Using `--admin` flag to bypass → violates repository policy

**Related Skills**: None yet

**Notes**:

- This is a hard requirement enforced by branch protection
- Applies to all PRs in rjmurillo/ai-agents repository
- Resolution must happen before merge attempt
