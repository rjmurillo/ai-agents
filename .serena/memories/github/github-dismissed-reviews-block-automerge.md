# GitHub: DISMISSED Reviews Block Auto-Merge

## Context
When investigating why PR #920 couldn't auto-merge despite all checks passing and auto-merge being enabled.

## Key Learning
DISMISSED reviews clear the `reviewDecision` field to null, which blocks auto-merge even when all required status checks pass and auto-merge is enabled.

## Evidence
- PR #920: mergeStateStatus: BLOCKED, mergeable: MERGEABLE, reviewDecision: null
- All 36 required checks: PASSED (11 SKIPPED)
- Auto-merge enabled at 2026-01-16T16:57:02Z
- Latest review from rjmurillo: DISMISSED at 2026-01-16T16:56:52Z (10 seconds before auto-merge enabled)

## Root Cause
GitHub branch protection policies typically require at least one active approval. When reviews are DISMISSED (not just commented/approved), it removes the approval state entirely, leaving reviewDecision as null. This prevents auto-merge from executing even though the PR is technically mergeable.

## Resolution Pattern
1. Check reviewDecision field via GraphQL: `gh api graphql -f query='query { repository(owner: "X", name: "Y") { pullRequest(number: Z) { reviewDecision mergeStateStatus } } }'`
2. If reviewDecision is null and mergeStateStatus is BLOCKED, request fresh approval from authorized reviewer
3. Auto-merge will proceed automatically once approval is granted

## Technical Details
- `mergeStateStatus: BLOCKED` indicates branch protection preventing merge
- `mergeable: MERGEABLE` indicates no merge conflicts
- `reviewDecision: null` indicates no active approval/rejection
- GitHub computes merge state asynchronously (may show UNKNOWN initially)

## A COMMENTED re-review does not clear a CHANGES_REQUESTED block

`reviewDecision` moves only on `APPROVED`, `CHANGES_REQUESTED`, and `DISMISSED`.
A bot that re-reviews after the fix and posts `COMMENTED` leaves its older
`CHANGES_REQUESTED` review active. All threads can be resolved and every check
green, and the PR stays blocked. Only a later `APPROVED` from the same reviewer,
or a human dismissal, clears it.

`detect_stale_bot_review.py` encodes this: `_VERDICT_STATES` at line 82 lists the
three states that count, and its `DISMISSAL_HANDOFF` verdict prints the dismissal
command for a human to run. The agent does not dismiss reviews.

Source: the 2026-10-12 sweep (issue #5950), re-read in the script on `origin/main` at `ec3214659`.

## Related
- Session: 2026-01-16-session-8-pr-920-merge
- ADR-014: HANDOFF.md read-only architecture
- Branch protection policies

## Last Updated
2026-01-16
