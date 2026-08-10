# Strict Freshness Requires One Front

**Atomicity**: 96%
**Category**: CI cost, branch protection, pull request landing

## Statement

Under strict freshness, refresh and test only the front PR.

## Observation

[2026-08-09] [user]: Updating 41 behind branches in parallel triggered 820
queued or in-progress workflow runs. The first merge would make the other 40
branches stale, so most matrices were guaranteed waste. Auto-merge was disabled
on the other PRs and 818 runs were cancelled.

Strict freshness is the server-side stale-merge lock. The cost-safe drain is:

1. Keep zero or one auto-merge request.
2. Update only the front PR to main.
3. Run one CI matrix.
4. Merge it.
5. Advance to the next PR.

For dependent new work, use stacked PRs. Do not stack unrelated backlog work.

## Relations

- **related_to**: ci-count-ratchets-require-branch-freshness
- **related_to**: decision-every-merge-invalidates-every-open-pr
- **related_to**: ci-required-run-cancellation-destroys-recovery
