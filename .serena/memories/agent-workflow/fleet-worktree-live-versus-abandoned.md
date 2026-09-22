# Fleet Worktrees: Live Versus Abandoned (measurements)

<!-- placement: evidence; reason: records the measurements and incidents behind the worktree triage procedure, which the git-advanced-workflows skill owns -->

**Last Updated**: 2026-09-21
**Source**: Session measurement, overturn #169

The procedure (age check, file-list check, pull request join, anchor before
removal) lives in the `git-advanced-workflows` skill at
`references/worktree-triage.md`. This memory keeps the numbers that justify
each step.

## Incident: dirty read as owned

The runtime wiped a 32-agent fleet mid-session and left every worktree behind.
An ownership check that treated "dirty" as "owned" froze every issue whose
worktree the wipe orphaned. When that rule was broadcast to the fleet, two
agents stood down and shipped nothing across 1598 seconds of combined runtime,
on issues nobody was working.

## Incident: basename collision

An abandoned `ai-agents-mergerace-3483113` (263 minutes stale) read as the
live agent `mergerace` because the basename carried a numeric collision
suffix. Acting on the name match froze the review-thread cluster a second
time; the retraction went out ten minutes after the original correction. The
live `mergerace` worktree held `scripts/ci/ruff_ratchet.py`; the abandoned one
held the review-thread files. Only the file list settled it.

## Measurement: commit counts overstate unlanded work

In this squash-merge repository, one stale worktree reported 56 commits ahead
and 329 changed files, of which 11 still differed from `main`. Another
reported 255 changed files with 7 still differing.

## Measurement: fleet-scale join

Across 185 worktrees, 125 matched "not on main, no remote branch" while about
9 held work that was never proposed. The pull request join split the fleet
into 50 detached checkouts, 23 heads of merged pull requests, and 52 named
branches with no pull request in the fetched set. Four of the 52 were clean
and under a week old; two of those four fixed a byte budget the fleet had been
failing against for five days.

## Measurement: anchoring cost

Anchoring 136 unreachable tips with `refs/salvage/` refs plus one bundle took
107 MB and a few minutes. `git bundle create` refused a list of bare SHAs with
`Refusing to create empty bundle`, which is why the refs come first.

## Related

- `quality/verify-squash-merge-by-content-not-ancestry.md`: why ancestry
  cannot prove a squash-merged branch landed.
- `git/git-a-worktree-whose-directory-is-gone-can-still-be-removed-by-path.md`:
  reachability check before removal.
