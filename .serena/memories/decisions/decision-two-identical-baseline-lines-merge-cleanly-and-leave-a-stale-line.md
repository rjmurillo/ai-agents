# Two PRs that each delete one of two identical baseline lines merge with no conflict and leave a stale line

**Atomicity**: 90%
**Category**: CI ratchets, baseline files
**Source**: Agent session sweep, sessions dated 2026-11. Sweep ids E084. State checked on main at 1be533c496 (2026-11-26).

## Question

Is a shrink-only per-entry baseline safe for parallel cleanup PRs?

## Conventional answer

A per-entry baseline was described as shrink-only. That was taken to make parallel cleanup PRs safe.

## First-principles position

A `git merge-file` probe used a base with two identical lines. Each side deleted one line. The merge gave 0 conflicts and kept one line. Both findings were fixed, so the kept line is stale. The gate then fails on the base branch. Identical lines turn two valid deletions into one stale entry.

## Evidence with limits

- A synthetic `git merge-file` probe deleted one of two identical `ARG001 owner` lines on each side. The merge reported zero conflicts and left one stale line (2026-11-05).
- The stale line fails the gate on main and on later PRs.
- At review time, 6 baseline keys were duplicated (2026-11-05).
- Limits: Synthetic three-line probe on one git version, run during review of PR 7080 before merge. No real merge of two live PRs was run. The owner was added to the key in the same PR.
- State on main at 1be533c496 (2026-11-26): fixed. `unused_arguments_owner.py:7` says git merges two deletions of identical lines into a stale line that fails the gate on the base branch. Duplicate baseline lines on main: 0.

## Decision

Key every per-entry baseline line so no two lines are identical, for example by adding the owning function. Identical lines turn two valid deletions into a stale entry that reds the base branch.

## Related

- `.serena/memories/decision-every-merge-invalidates-every-open-pr.md`
