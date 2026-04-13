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

## Related
- Session: 2026-01-16-session-8-pr-920-merge
- ADR-014: HANDOFF.md read-only architecture
- Branch protection policies

## Last Updated
2026-01-16
