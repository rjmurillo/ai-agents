# Copilot Follow-Up PR Pattern

## Behavior

When Copilot receives a reply to its PR review comments, it creates a follow-up PR:

- Branch naming: `copilot/sub-pr-{original_pr_number}`
- Target branch: The original PR's branch (not main)
- Notification: Posts issue comment: "I've opened a new pull request, #{number}"

## Handling Duplicate Follow-Up PRs

```bash
# 1. Check review count
gh pr view {number} --json reviews --jq '.reviews | length'

# 2. If 0 reviews and issue was already fixed, close as duplicate
gh pr close {number} --comment "Closing: This follow-up PR is a duplicate of the fix already applied in commit {sha} on PR #{original}."
```

## Example (PR #32 / PR #33)

- Original PR #32: 5 Copilot comments about missing `devops`
- Fix applied: Commit 760f1e1 addressed all 5 comments
- Follow-up PR #33: Created by Copilot, duplicate of fix
- Resolution: Closed PR #33 as duplicate

## Index

Parent: `skills-copilot-index`
