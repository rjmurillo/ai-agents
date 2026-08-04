# Twenty-nine green pull requests merged into a red main

Date: 2026-08-04
Branch: `fix/red-main-after-merge-sweep`
Pull request: #4508
Related issue: #4507

## Summary

Two merge sweeps took the open pull request count from 55 to 27. Every one of
those pull requests was green when it merged. `main` was red when the sweeps
finished, and stayed red long enough that a second contributor hit it
independently and filed #4507.

Nothing in the sweep was wrong on its own terms. The mistake was treating a
per-pull-request green check as a statement about `main`. It is a statement
about the base the branch was cut from, and that base stops existing the moment
the preceding pull request lands.

## Failure mode classification

Primary: **5. Premature merge and deploy** (Critical) in
`.agents/governance/FAILURE-MODES.md`. The merges were authorized by a signal
that had already expired.

Secondary: **4. False completion markers** (High). "29 merged, queue drained"
was reported as an outcome. The outcome was a red trunk, which is worse than
the 29 open pull requests it replaced.

## Impact

| Area | Severity | Effect |
|---|---|---|
| Trunk health | High | Three required jobs red on `main` for several hours |
| Contributor throughput | High | Pre-push runs the full suite, so every branch that merged `main` inherited the failures and could not push. #4507 documents one instance. |
| Signal quality | Medium | Red `main` trains readers to skim past red, which is how the next real regression gets through |
| Rework | Medium | One pull request (#4508) to repair damage that no single merged change contained |

## Timeline

1. Two sweeps merge 29 pull requests. Each shows green required checks at the
   moment of merge.
2. `main` run `30859303495` at `f326f3399` finishes with three failing jobs:
   `Run Python Tests`, `Python Security Checks`, and `Run Windows path-contract
   tests`.
3. A contributor pushing an unrelated branch hits the same failures locally and
   files #4507 with the exact test identifiers.
4. Branch `fix/red-main-after-merge-sweep` reproduces all of them, fixes them,
   and opens #4508.

## Root cause

Five whys.

1. **Why is `main` red?** Tests that pass on each merged branch fail on the
   merge result.
2. **Why do they fail there?** Several are whole-tree assertions. The always-on
   corpus tests count bytes across every always-on instruction file and compare
   against a pinned figure. Any pull request that changes any of those files
   moves the count. Each branch measured a tree that contained only its own
   change.
3. **Why did per-branch CI not see it?** Because CI ran against the base the
   branch was cut from. By merge time, up to 28 other changes had landed on top
   of that base.
4. **Why did the merges proceed?** The merge decision consumed the pull
   request's own check rollup. That rollup is truthful about a commit that is no
   longer the merge base.
5. **Why is that the default?** The repository does not require branches to be
   up to date before merging, and no merge queue is configured. Confirmed
   mechanically: none of the 62 workflow files carries a `merge_group` trigger,
   so a queue would have no checks to run even if it were switched on.

The generalizable statement: **per-pull-request green does not compose.** Two
changes that are each correct in isolation can be incorrect together, and
whole-tree assertions make that outcome likely rather than exotic. Batch merging
without re-establishing green between merges converts that likelihood into a
certainty at scale.

## What worked

The repair path was fast because the failures were deterministic and local.
Running the full suite in a worktree reproduced every failure #4507 listed
without needing CI. The pre-push hook, which runs the same suite, is what forced
the problem into view rather than letting it sit.

Reading `main`'s own latest completed run before attributing anything to #4508
prevented a wasted investigation. The three failing jobs were already failing at
`f326f3399`, which established them as inherited rather than introduced.

## What did not work

**A no-op change that no test could contradict.** While fixing
`test_pr_validation_workflow.py`, an entry was added to the
`_ALLOWED_BEHIND_GUARD` frozenset that the set already contained. Every local
test passed, because adding a member that is already present changes nothing.
Only ruff caught it, as B033. The negative control confirmed the point: removing
the addition entirely leaves 51 tests passing. The real fix had been the
workflow file all along.

The lesson generalizes past this instance. A test suite cannot distinguish a
redundant set insertion from a necessary one, so "the tests pass after my
change" is not evidence that the change did anything. Membership operations are
idempotent, and idempotent edits are invisible to behavioral tests by
construction.

**A wrong root cause, nearly filed as an issue.** The `Python Security Checks`
failure was first attributed to a line reading `Dependency not found on PyPI and
could not be audited: ai-agents (0.1.0)`. That line is a skip-reason table, and
pip-audit only treats a skipped dependency as fatal under `--strict`, which this
step does not pass. The real cause was `CVE-2026-69247` in `cryptography 49.0.0`
with a fix in `50.0.0`. Reading the exit-code line and working backwards found
it. The issue was held pending log evidence rather than filed on the hypothesis,
which is the only reason a wrong issue does not exist now.

## Remediation

| Action | Status |
|---|---|
| Fix the red tests on `main` | #4508, open |
| Upgrade `cryptography` past `CVE-2026-69247` | In #4508. Required adding a per-package `exclude-newer` opt-out, because the repository-wide `exclude-newer = "7 days"` window pinned the resolver to the vulnerable release. |
| Pin the `GITHUB_STEP_SUMMARY` inheritance trap so a non-hermetic subprocess test cannot recur | In #4508, as SHOULD 12 in `.claude/rules/testing.md` with both mirrors regenerated |
| Record that every merge invalidates every open pull request | In #4508, as a Serena memory |
| Make the rate-limit guard able to observe the limit that actually fires | Issue drafted, see the secondary rate limit finding |
| Decide whether to require up-to-date branches or configure a merge queue | Open question, no issue yet |

## The open question worth deciding

Requiring branches to be up to date before merge trades throughput for trunk
health. At 55 open pull requests that trade is expensive, and the expense is
exactly why the sweep happened. A merge queue gets most of the safety without
serializing human work, but it needs `merge_group` triggers added to the
workflows that matter, which none of the 62 currently carry.

The cheap middle option, and the one this session should have used: after every
batch of merges, run `main` and fix before merging more. That converts an
unbounded blast radius into a bounded one without changing any repository
setting.

## References

- #4507. Independent report of the same failures from a different branch
- #4508. The repair
- `main` run `30859303495` at `f326f3399`. Three failing jobs, pre-existing
- `.agents/governance/FAILURE-MODES.md`. Classes 4 and 5
- `.serena/memories/decision-every-merge-invalidates-every-open-pr.md`
