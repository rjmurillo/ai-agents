# EUREKA: draining this PR queue is self-throttling, because each merge invalidates every PR behind it

## Question

Why does a backlog of green-looking PRs refuse to drain, and why does the same
stale-branch advice keep having to be rediscovered?

## Conventional answer

`.claude/rules/ci-scripts.md` MUST 12 teaches the remedy: merge `origin/main`
and re-measure before hunting a tripped count ratchet, because a branch behind
main reports an increase it did not cause. That rule is correct and it reads as
contributor discipline, a thing you remember to do.

## First-principles position

Contributors keep re-deriving it because the repository is configured so that no
PR is ever required to be current before merging, and there is nothing to make
it current automatically:

```
gh api repos/rjmurillo/ai-agents/rules/branches/main
  -> "strict_required_status_checks_policy": false
grep -rln merge_group .github/workflows/
  -> (nothing)
```

The consequence is stronger than "branches go stale". The count ratchets compare
a branch's whole tree against a baseline integer that main lowers whenever main
clears violations. So **every merge invalidates every other open PR**, and a
drain of N PRs is not N independent units of work. It is a queue that re-dirties
itself behind you.

## Evidence

Measured 2026-08-03, one session.

Starting state: all 35 open PRs behind main by 1 to 33 commits, 15 conflicting,
zero mergeable-clean. `Run Python Tests` failed on nearly all of them. Sampled
PR #4095's three failures and ran them on current main: `29 passed`. The red was
inherited, not authored.

Then I caused it myself. Merging PR #4017 lowered `taste_count_baseline.txt`
from 600 to 598. My own two-file documentation PR #4399, which never touched a
baseline, immediately failed:

```
taste count ratchet: BASELINE ABOVE BASE. This tree records 600, FETCH_HEAD records 598 (+2).
```

`git merge origin/main` with no source edit returned it to
`OK (count == baseline 598)`.

The same root cause surfaced in three unrelated disguises in one session:

1. Inherited CI red across 35 PRs.
2. `new_pr.py` measuring the changed-file set against a stale local `main`,
   seeing 41 files where GitHub renders 3, and aborting on a session log
   belonging to a different PR (#4324).
3. A ratchet false positive on a PR that touched no code.

A second self-throttling loop compounds it: unresolved review threads are the
actual merge gate here (`required_review_thread_resolution: true`, 112 open
across 36 PRs), and clearing a thread requires a push, which triggers a fresh
Copilot review, which can add threads. Observed on #4336: cleared its only
thread, pushed the fix, immediately acquired a new one. So the thread count is
not a burndown either.

## Decision

Treat the queue as self-invalidating and plan accordingly rather than treating
each stale signal as a defect to diagnose:

- Re-fetch and merge `origin/main` immediately before measuring anything, and
  treat a `main` fetched earlier in the same session as already stale. This
  repository merges several times an hour.
- Expect to re-merge main into every remaining PR after each landing. Batching
  merges reduces the number of invalidation waves.
- A merge queue is the structural fix, because it tests the combined result
  before the merge instead of after. Enabling it is an owner decision, and it is
  not free here: several required checks are PR-scoped (`Validate PR title`,
  `Validate Spec Coverage`, the ten LLM review axes feeding `Aggregate Results`)
  and key off `github.event.pull_request`. A `merge_group` event has no pull
  request, so adding the queue rule without first remapping those checks leaves
  them permanently unreported and wedges the queue.

Owner decision recorded 2026-08-03: enable a merge queue, sequenced after the
drain rather than before it, since a queue serializes merges and would have made
the drain slower.

**Superseded 2026-08-05: the merge queue is not available to this repository, so
do not plan around it.** GitHub gates merge queues to organization-owned
repositories. `rjmurillo/ai-agents` is public but owned by a user account, so it
does not qualify:

```
gh api repos/rjmurillo/ai-agents --jq '{visibility, owner_type: .owner.type}'
  -> {"visibility":"public","owner_type":"User"}
gh api orgs/rjmurillo
  -> 404 Not Found
```

The gating string is GitHub's own, from
`data/reusables/gated-features/merge-queue.md` in `github/docs`: "Pull request
merge queues are available in any public repository owned by an organization, or
in private repositories owned by organizations using GitHub Enterprise Cloud."
Public plus user-owned is the one combination that fails. Enabling it requires
transferring the repository to an organization first. Work on `merge_group`
triggers is dead code until that happens. A partial attempt was made on
2026-08-05 and reverted in the working tree before any commit, so it leaves no
trace in history.

**Do not "correct" `strict_required_status_checks_policy` back to `false`. It is
deliberately `true`.** This is the trap that the stale `false` reading recorded
earlier in this memory sets for the next agent, and it was walked into on
2026-08-05. Ruleset `11104075` version `45433643` armed strict at
2026-08-04 21:52 PT, hours after the red-`main` incident, as the remediation the
retrospective left open. Issue #4646 is open against exactly this drift and says
so plainly:

> Strict checks defend against the "individually green pull requests do not
> compose" failure in #4503. The problem is that nothing in the repository was
> updated to match, so every agent that consults the recorded value is now
> working from an inverted fact.

`docs/merge-guards.md` agrees: "Require Branches to be Up to Date. Enabled. Yes.
Rationale: Ensures validation runs against latest `main`, prevents race
conditions."

The near miss, recorded so the reasoning is not repeated: strict was read as an
unexplained throttle, set to `false` at 22:08 PT, and restored to `true` at
22:29 PT the same evening once the ruleset history and #4646 were checked. The
lesson is procedural. Before changing a live protection setting, read
`gh api repos/rjmurillo/ai-agents/rulesets/11104075/history` and search the
issue tracker for the setting's name. A setting that contradicts a committed
memory is more likely to be a deliberate change the memory has not caught up to
than it is to be drift.

**The merge-tree ratchet is not a substitute for strict, and must not be cited
as one.** `scripts/ci/merge_tree_ratchet_check.py` (issue #4398) is blocking on
every pull request: it runs in job `validate-pr` of `pr-validation.yml`, whose
name `Validate PR` is one of the 17 required contexts, with no `if` guard and no
`continue-on-error`. But it evaluates only the five ratchets registered in
`scripts/ci/merge_tree_ratchet_registry.py` (ruff count, taste count,
type-ignore count, memory-index count, CLI exit contract) against the merged
result. Strict is what makes the other sixteen required contexts run against a
tree containing current `main`.

The uncovered class is the one that caused the incident. `Run Python Tests`
carries whole-tree assertions, including the pinned corpus figures in
`tests/validation/test_always_on_corpus_claims.py`. Two pull requests that each
edit a different always-on rule and each update the figure to their own
measurement both pass alone and fail merged. That is root cause 2 of the
2026-08-04 retrospective, and it is not in the merge-tree registry.

Two holes would open if strict were disabled: the stale-base hole for every
check outside those five ratchets, and the concurrent-admission hole (#4345),
where three pull requests each pass alone and breach only when all three land. A
merge queue would have closed both, and it is unavailable on this repository.

## Corollary: the merged result can be red even when every input was green

The section above is about PRs behind main going red. The sharper failure is the
other direction: `main` itself goes red after a sweep in which every merged PR
had a green required-check rollup. Textual mergeability does not imply semantic
compatibility, and `git merge-tree` cannot see the difference.

Measured 2026-08-03. A 29-PR sweep took the queue from 55 open to 27 and left
`main` at `b2729ee54` failing 9 tests across 4 unrelated causes. Proof it was
not the sweeping branch's fault: a clean worktree at `origin/main`, with no
branch content, ran the same 9 node ids and reported `9 failed, 13 passed`.

Four kinds of file couple PRs that share no bytes:

| Coupling | Instance observed |
|---|---|
| Whole-repo ratchet baseline | `.agents/governance/GOTCHAS.md` reached 521 lines in one PR; the baseline stayed 595; count became 596 |
| Figures measured from the whole tree | `voice.instructions.md` shrank 2097 bytes, so 6 figures in `model-context-doctrine.md` went stale and 5 corpus-claim tests went red |
| Mutation harness pinned to exact bytes | `mutation_harness_ciperms.py` M7 pinned `--max 58`; a PR lowered the ADR-006 ratchet to `--max 0` |
| Allowlist keyed by step name | A PR put `Setup uv` behind the bot-skip guard without adding it to `_ALLOWED_BEHIND_GUARD` |

None of those four PRs opened the file that broke.

The operational rule: after merging a batch, run the suite against the resulting
`main` before declaring the sweep done. Per-PR green does not compose. The four
global-invariant checks above run in under 10 seconds together and would have
caught all 9:

```bash
uv run --frozen pytest -q -p no:randomly \
  tests/ci/test_count_ratchet_against_real_git.py \
  tests/ci/test_mutation_harness_ciperms.py \
  tests/ci/test_pr_validation_workflow.py \
  tests/validation/test_always_on_corpus_claims.py \
  tests/validation/test_check_subprocess_encoding.py
```

This is independent evidence for the merge queue recorded above. A queue tests
the combined tree before the merge, which is exactly the check that was missing.

It also compounds with the pre-push hook: the red surfaced to me as a blocked
push with no statement that the failures were pre-existing, so every agent
pushing during the window paid a full suite run and diagnosed from scratch.
Filed as issue #4503.

## Confirmed again on 2026-08-04, with the cheapest remedy named

PR #4508 sat at merge-base `a81239d0c` carrying `ruff_count_baseline.txt` = 308
and measuring 306, so its own ratchet passed and all 102 checks were green.
`origin/main` had since advanced to `7281a710d` and lowered that baseline to
126. Merging main into the branch reproduced issue #4538 exactly:

```
ruff count ratchet: REGRESSION. 140 violations > baseline 126 (+14).
```

Nothing in the branch caused it. The branch inherited a ceiling it was never
measured against, which is the same non-monotonicity recorded above, seen from
the receiving end rather than the causing end.

The remedy is cheaper than it looks, and it is not a baseline edit. Of the 140
violations, 100 were `RUF100` (unused `noqa` directive). A `noqa` for a rule
that is not enabled at that location is dead text: ruff itself proves it is
unreachable, so deleting it cannot change any diagnostic. Removing 18 of them
across three files took the count to 122:

```bash
uv run --frozen ruff check --fix <changed test files>
uv run --frozen python scripts/ci/ruff_count_ratchet.py
# ruff count ratchet: OK. 122 violations <= baseline 126 (-4 slack).
```

Check `RUF100` first when an inherited ruff ratchet blocks a push. It is the
one violation class where the fix is provably behavior-preserving, so it buys
ratchet headroom without a baseline change and without a new suppression.

Note the second, quieter gate: the changed-files ruff run is zero-tolerance, so
a dead `noqa` on a line the branch never touched still blocks the push once the
branch edits anything else in that file. `tests/validation/test_always_on_corpus_claims.py:36`
carried `# noqa: E402` from PR #4485 on main and failed `python-lint-ratchet`
for exactly that reason.
