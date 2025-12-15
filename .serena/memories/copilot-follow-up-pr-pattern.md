# Copilot Follow-Up PR Pattern

## Behavior

When Copilot receives a reply to its PR review comments, it often creates a follow-up PR:

1. **Branch naming**: `copilot/sub-pr-{original_pr_number}`
2. **Target branch**: The original PR's branch (not main)
3. **Notification**: Posts issue comment: "I've opened a new pull request, #{number}, to work on those changes"

## Handling Duplicate Follow-Up PRs

If the original comment was already addressed before Copilot created the follow-up:

1. Check review count: `gh pr view {number} --json reviews --jq '.reviews | length'`
2. If 0 reviews and issue was already fixed, close with explanation:

   ```bash
   gh pr close {number} --comment "Closing: This follow-up PR is a duplicate of the fix already applied in commit {sha} on PR #{original}."
   ```

## Example: PR #32 / PR #33

- **Original PR**: #32 (feat/feature-ideation-workflow)
- **Copilot comments**: 5 comments about missing `devops` in agent sequences
- **Fix applied**: Commit 760f1e1 addressed all 5 comments
- **Follow-up PR**: #33 (copilot/sub-pr-32) - duplicate of the fix
- **Resolution**: Closed PR #33 as duplicate

## Timeline

- 2025-12-14T13:23:10Z: Copilot posted 5 review comments
- 2025-12-14T13:38:21Z: User replied with fix acknowledgment
- 2025-12-14T13:38:28Z: Copilot announced follow-up PR #33
- 2025-12-14T14:14:42Z: PR #33 closed as duplicate
