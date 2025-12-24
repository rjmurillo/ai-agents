**Behavior**: Copilot creates follow-up PR after reply to review comments.

- Branch: `copilot/sub-pr-{original_pr_number}`
- Target: Original PR branch (not main)

**Handle duplicates**:

```bash
gh pr view {number} --json reviews --jq '.reviews | length'
# If 0 reviews and already fixed:
gh pr close {number} --comment "Duplicate of fix in commit {sha} on PR #{original}."
```
