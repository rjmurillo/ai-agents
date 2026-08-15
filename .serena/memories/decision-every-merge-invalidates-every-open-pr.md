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

Contributors keep re-deriving it because nothing makes a branch current
automatically, and there is still no merge queue to test the combined result:

```
grep -rln merge_group .github/workflows/
  -> (nothing)
```

**Update 2026-08-15: strict is now `false` again. The count ratchets enforce
effective branch freshness independently, so the serial one-front landing
protocol is unchanged. See `docs/landing-workflow.md`. The `merge_group` half
still holds: no workflow answers that event, and a merge queue cannot be enabled
on this repository anyway (user-owned).**

The consequence is stronger than "branches go stale". The count ratchets compare
a branch's whole tree against a baseline integer that main lowers whenever main
clears violations. So **every merge invalidates every other open PR**, and a
drain of N PRs is not N independent units of work. It is a queue that re-dirties
itself behind you.

### The strict policy history

This memory originally recorded
`"strict_required_status_checks_policy": false`, and reasoned that no PR was
ever *required* to be current. It was flipped to `true` on 2026-08-04, then
returned to `false` before 2026-08-15. Measured 2026-08-15:

```
gh api repos/rjmurillo/ai-agents/rules/branches/main \
  --jq '[.[] | select(.type=="required_status_checks")
         | .parameters.strict_required_status_checks_policy]'
  -> [false]
```

The operational conclusion is unchanged regardless of the strict setting: the
count ratchets enforce effective branch freshness because they compare the
branch baseline against main's lowered value. A branch behind main fails CI
whether or not GitHub also blocks the merge button.

The drain is therefore strictly serial. Auto-merge does not rescue the
serialization, because auto-merge never updates a branch: it stays armed and
waits indefinitely while the PR sits `BEHIND`. Refreshing the branch is the
step a human still has to take; re-arming is not.

The serial one-front landing protocol controls concurrency and CI cost. See
`docs/landing-workflow.md`.

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

## Implementation update, 2026-08-11

Issue #4691's workflow inventory changed during implementation. Ruleset
11104075 requires 16 contexts from 10 workflows. Both `Analyze` contexts come
from `codeql-analysis.yml`; `ai-metrics-analysis.yml` is not a required-check
producer.

The code-readiness change adds `merge_group` support to those 10 workflows.
Tree-sensitive checks run against the queued merge ref. PR-shaped checks
conclude at job level because the PR already passed the same required context
before queue entry. Structural tests pin all 16 live contexts, main-only event
targeting, queue-ref concurrency, path-filter forcing, and PR anti-vacuity.
Local `gh act merge_group` execution ran `Validate Path Normalization` against
3,967 tracked Markdown files.

Code readiness does not enable the queue. The repository API reports
`owner.type = User`, while GitHub limits merge queues to organization-owned
repositories for this configuration. The owner must transfer the repository to
an organization or GitHub must expand eligibility before the ruleset gains a
`merge_queue` rule.

`strict_required_status_checks_policy` is `false` as of 2026-08-15. The count
ratchets block a behind branch only when main has lowered a relevant baseline
(not universally). The serial one-front landing protocol controls concurrency.
See `docs/landing-workflow.md`.

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

Run it from a clean worktree at `origin/main`, not from a branch checkout, or
the branch's own content contaminates the answer:

```bash
git fetch origin main
git worktree add "$HOME/src/scratch/worktrees/mainverify" origin/main --detach
```

Applied 2026-08-08 after landing #4614, #4572, #4755, and #4741: `181 passed
in 11.98s` against `e7018e4b7`, so that sweep composed cleanly. The check is
worth running even on a small sweep, since the 2026-08-03 breakage came from
four PRs that never opened the file that broke.

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

## The same shape outside the count ratchets: hand-written corpus figures

The ratchets are not the only absolute baseline measured against the whole
tree. `tests/validation/test_always_on_corpus_claims.py` parses six figures out
of `.claude/skills/context-optimizer/references/model-context-doctrine.md` and
asserts each against a live measurement of the always-on rule corpus. The
figures are hand-written prose, so they behave exactly like a ratchet baseline:

- Any branch that adds bytes to an always-on rule must rewrite them.
- Two such branches rewrite the **same prose lines**, so they conflict in
  narrative text rather than failing a counter. The conflict is a mid-air
  collision on numbers that look arbitrary, which is worse to resolve than a
  counter bump.
- Merging either one invalidates the other's figures even after the textual
  conflict is settled, because the measurement moved.

Practical consequence: **stack always-on rule edits on one branch instead of
opening parallel ones.** On 2026-08-05 the retro branch already owned the
current figures, so a second rule edit went on the same branch deliberately
rather than onto a fresh branch off main, which would have conflicted by
construction.

Two properties make the fix cheap once you know them. A small delta fails four
of the six numeric assertions, the mirror, Python, source-total, and plugin
claims. The multiplier and largest-rule checks hold because they only move when
a rounded value or a ranking changes, so a small edit reads like a different
problem. And the guard runs in 0.5 seconds standalone while the pre-push hook
that contains it took 825 seconds in that run:

```bash
uv run --frozen pytest tests/validation/test_always_on_corpus_claims.py -q
```

Know what is **not** guarded. The table of per-rule sizes has its rule *names*
checked against the measured set by
`test_doctrine_table_matches_measured_always_on_set`, but not its *byte
values*. The rounded KB figures in the narrative prose and the book-rule
percentage are unparsed entirely. All three go stale in silence. Recompute them
by hand in the same edit.
