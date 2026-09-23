# PR Landing Session Retrospective

Date: 2026-08-04

## What We Did

Drove four open PRs (4459, 4477, 4479, 4484) to terminal states. All four were conflicting due to stale branches. Resolved conflicts by merging origin/main into each branch, addressed review threads, lowered taste-count baselines as main improved, and pushed for CI verification.

## What Went Well

- Identified root cause of push failures (taste-count ratchet chasing a moving main baseline).
- All four PRs passed full pre-push hook suite after fixes.
- Review threads addressed in each PR with correct commit SHAs.

## What Went Wrong

- Branch name mismatch: local land-4477, land-4459, land-4479 would push to wrong remote branches. Caught and fixed before any bad push.
- Multiple rounds of baseline updates needed because origin/main keeps receiving PRs that lower the baseline. Each round required a new merge commit.

## Learnings

- When multiple PRs touch taste_count_baseline.txt, the baseline on origin/main moves continuously. Landing a stale branch requires merging origin/main immediately before pushing, not hours before.
- push_any_slot.sh uses `git branch --show-current` for the remote branch name. Local branches must match the remote PR branch name exactly, or push to wrong branch.
