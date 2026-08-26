---
# taste-lint: ignore file-size, ten numbered rules cited by number from the debate log and from tests; splitting renumbers them and the linter's suggested split into helpers, types, and constants has no meaning for a decision record.
id: ADR-104
status: proposed
date: 2026-08-25
decision-makers: [rjmurillo]
supersedes: []
superseded-by: null
explainer: null
implemented: false
---

# ADR-104: Gate Tier Placement

## Status

Proposed. Six-seat adr-review debate held 2026-08-25; log at
`.agents/critique/ADR-104-debate-log.md`. The first revision was blocked by two
seats and this record is the rewrite. `implemented` stays false until the
branch merges, per ADR-073's definition of that field.

Acceptance was gated on an end-to-end wall-clock measurement of the hook during
a real push, because `ci-scripts.md` MUST-16 forbids sizing a pre-push budget
from a standalone run. That measurement now exists and is in Consequences
below: 142.39s, against 679s recorded for a comparable push. The gate is
cleared. The remaining reason this stays `proposed` is that the branch has not
merged.

## Date

2026-08-25

## Context

Three local gate tiers exist. No record states what any of them may cost.
ADR-004 chose a pre-commit entry point, ADR-086 replaced the custom scheduler
with Lefthook, ADR-049 defined the pre-PR validation runner, ADR-071 placed the
credentialed CLI end-to-end smokes in pre-push, and issue #5066 staged pre-push
into a fast half and an expensive half. Each answered a scheduling question.

ADR-054 came closest to a placement rule and stayed qualitative: it rejected
the CodeQL CLI from pre-push as "too slow for pre-push (30-60 seconds
minimum)". So a cost bar existed for one job, set by judgement, with no number
another author could apply to a different job.

Without a number, placement accreted toward the earliest tier that could host
the check, because earlier feedback reads as better in isolation. Pre-push grew
to hold a whole-suite pytest run, a semgrep scan, two CLI end-to-end smokes, a
workflow runner, a type check, and a 47-gate pre-PR validation runner.

### What that cost

Measured 2026-08-25, 4-CPU remote container, full clone,
`AI_AGENTS_PYTEST_WORKER_CAP=4`, jobs run standalone rather than in-hook:

| pre-push job | wall clock |
|---|---|
| `python-tests`, whole suite | 382s |
| `pytest --collect-only` over the same suite | 8.9s internal, 14s wall idle, 34.6s wall loaded |
| every fast-stage gate | 0.1s to 19.6s each |

The 382s run also exited 1, in the mutation partition. That is **not** evidence
of anything: the mutation harness refuses to run when one of its target files
is dirty, and the target was being edited while the run was in flight. Two
attempts to get a clean run hit the same self-inflicted problem. 382s is a
duration measurement and nothing more. An earlier revision of this record
attributed the failure to container behavior and to a `gh` GraphQL call; both
were wrong, the second by conflating output from a partition that passed.

An independent measurement of a real in-hook push, recorded in
`.serena/memories/ci/ci-pre-push-wall-clock-is-python-tests.md` for a one-file
Markdown push on the same container class, agrees on the shape: 679s total,
498.52s of it `python-tests`, 110.12s `pre-pr-validation`, every one of the
other ten jobs in that group under 3s.

### The failure this produced

A remote-container session is reclaimed after a period without progress. A push
that blocks for eleven minutes inside a hook can outlive its container. The
push dies, the container restarts, the session re-reads its own state to work
out what landed, and pushes again. Each cycle costs wall clock and tokens and
yields no signal the remote gate would not have produced. The local gate was
preventing the push from reaching the gate it was imitating.

### The asymmetry that made it avoidable

`scripts/test_selection/select_tests.py` falls back to the whole suite on
`non-Python change: <rel>`. Probed on this checkout:

```text
README.md                        -> FULL (non-Python change)
lefthook.yml                     -> FULL (runtime-read pattern)
.serena/memories/memory-index.md -> FULL (non-Python change)
scripts/validation/pre_pr.py     -> 25 tests via import graph
```

This repository's changes are mostly Markdown, so the common change took the
whole-suite path. CI does not: `.github/workflows/pytest.yml` gates its matrix
behind a `dorny/paths-filter` allowlist.

## Decision

Three tiers, each with a stated job. A check is placed by the rules below, not
by which tier can technically host it.

### Tier definitions

| Tier | Question it answers | Reads | Target |
|---|---|---|---|
| pre-commit | Is this edit well formed? | the staged files | 60s per commit |
| pre-push | Would this branch waste a CI run or a reviewer? | the branch delta against `origin/main` | 300s per push |
| CI | Is this change correct, in isolation, at full scale? | the merge result | its own job timeouts |

**Neither target is enforced at runtime.** A hook that failed because the host
was busy would replace a slow push with a refused one. The 60s pre-commit
figure in particular has no measurement behind it: this record audited pre-push
only, and pre-commit's 47 jobs were not timed. Treat it as a placeholder until
someone measures it (issue #5318).

What is enforced is the **declared** worst case, which is what a container
actually has to survive. `tests/ci/test_lefthook_declared_budget.py` sums each
hook's caps through lefthook's own scheduling semantics (top level piped, so
entries sum; a parallel group costs its slowest member; a piped group sums) and
ratchets the total. It may only fall.

That number was 4170s for pre-push, 69.5 minutes, against real pushes of
142.39s. Caps resized from in-hook measurement bring it to 2850s.

The first attempt cut further and was wrong to. Nine jobs went below a floor
the config does not state: `test_each_python_subprocess_budget_has_lefthook_headroom`
requires every job invoking `git_hook_policy` to carry a cap at least 30s above
its inner child budget, so the inner timeout fires first and the reader gets a
diagnostic rather than a bare kill (ADR-086 item 9). With
`DEFAULT_SUBPROCESS_TIMEOUT_SECONDS` at 90, a job that can spawn a 90s child
cannot be capped at 20s however cheap it measures. That is the third coupling
in this record holding a number in place from somewhere the number is not
written down.

A workstation and a container are asking different questions, so they get
different answers. A workstation needs a long cap for a job with legitimate
work to do; the worst that a long cap costs there is patience. A container is
reclaimed after a period without progress, so the same cap is a job that can
outlive its environment and take the push with it, leaving no diagnostic.

`git_hook_policy._container_clamped` answers the second question.
`_run_command` is the funnel every expensive job's work passes through, and it
clamps its child's deadline to 150s when `_is_remote_container()` is true.
Workstations and CI are untouched. `tests/ci/test_lefthook_declared_budget.py`
models that clamp against the declared caps and asserts the result:

The bound that matters is **per job**, not the sum of every cap. An earlier
revision of this record summed the clamped caps and compared the total against
the roughly 679s at which a reclamation was observed. That comparison is not
sound, and saying so is worth more than the number it produced: the sum is the
case where every job in the graph hangs to its cap on the same push, which
cannot happen, and the figure it was compared against is a single measured push
rather than a cap. Two different quantities.

A hang is one job. So:

```text
declared sum, workstation        2850s   47.5 min   (was 4170s)
largest single child, container    150s    2.5 min   (was 1800s)
```

No single pre-push **subprocess** can run longer than 150s inside a container.
That is the enforced property, and it is narrower than the per-job bound an
earlier revision of this paragraph claimed. `pre-pr-validation` does not route
through `_run_command` and carries its own 240s cap; every job whose work is a
single subprocess is bounded by the clamp.

Two jobs are not single-subprocess and are therefore not bounded at 150s.
`run_pytest` holds an aggregate deadline across its children but at 780s on the
opt-in path, and `scan_pushed_heads` holds none: it loops over pushed refs and
each scan gets a fresh clamp, so N refs cost up to N times 150s. Rule 8 remains
open for both. The measured hook is ~148s end to end and the default collection
path spawns one child, so this is the tail rather than the common case; that
sizes the fix, it does not excuse the claim. Corrected in review on PR #5319,
tracked in #5318.

The container detection is issue #2548's, imported rather than redefined; that
issue established both the mechanism and the precedent of degrading a pre-push
job in a container.

Unpicking one coupling made the rest possible, and it is worth recording
because it is the same shape as the reverted deduplication. `pre-pr-validation`
was pinned at a 15m cap by its Generated Artifact Staleness gate, whose budget
plus grace must fit in half that cap. That budget was 420s for work measured at
1s, a 100x margin holding 900s of the graph's worst case in place two files
away from anything that mentions it.

The other instrument is rule 3, which says what a tier may do. Where rule 3 is
applied, the target is redundant with it.

### Placement rules

1. **Pre-commit takes checks the author fixes in the same edit.** Formatting,
   syntax, secrets, prohibited characters, conflict markers, staged-file
   policy. If the finding does not change what the author is typing right now,
   it does not belong here.

2. **Pre-push takes checks that are cheap and would otherwise be discovered
   remotely.** Ratchets, branch-scope and push-ref policy, targeted tests
   selected from the diff. The test is not "is this check valuable" but "does
   running it here cost seconds and save a CI round trip".

3. **CI takes everything expensive, isolated, matrixed, or credentialed.**
   Whole-suite execution, end-to-end smokes, static analysis at full scope,
   workflow runs, anything needing a service or a secret. See Known
   non-conformances: five pre-push jobs match this rule today and stay, for
   reasons this record does not overturn.

4. **A local check MUST NOT be a more expensive copy of a required CI check.**
   Duplicating a remote gate locally is only justified when the local copy is
   cheaper than the remote one for the common change class. When the local copy
   is more expensive, as `python-tests` was for Markdown, it is not early
   feedback; it is the thing preventing feedback.

5. **When a check would exceed its tier's target, replace it with the cheapest
   check that catches a defect class you have measured it to catch.** Not with
   nothing, and not with a raised target. The whole-suite run becomes a
   whole-suite collection. State only the classes you probed, and probe them
   under production configuration: collection blocks on a broken import and on
   a syntax error. It does not catch a missing fixture, does not catch two
   same-named test functions in one module, and does not catch a same-basename
   module collision.

   That third miss was published here as a catch. It is a collection error
   under pytest's default `prepend` import mode and not under
   `--import-mode=importlib`, which `pyproject.toml` sets; the probe ran in a
   throwaway tree with no config and got the wrong mode. A probe that does not
   carry the configuration production carries measures a different program, so
   rule 5's "measured to catch" means measured under that configuration.
   Corrected in review on PR #5319.

6. **A deferral is a claim about the scheduler, so it must name what it relies
   on and be tested on that.** Naming the job it defers to is not enough. See
   Rejected below for the version of this that shipped and was reverted.

7. **A cap is a promise about the worst case, so it is sized from a measured
   in-hook run and ratcheted.** MUST-16 forbids sizing a pre-push cap from a
   standalone run. A cap nobody revisits drifts upward one job at a time, which
   is how the declared worst case reached 29x the real one.

8. **A local tier MUST NOT be able to outlive the environment it runs in.**
   Where an environment can end the process, the tier's bound is that
   environment's tolerance, not the cap that suits a workstation. A hung job
   killed with a diagnostic is strictly better than one reclaimed with none,
   so the clamp is not a weakening of the gate: without it the gate produces
   no verdict at all.

9. **A job that cannot fail is not a gate, so it is not placed by the rules
   above.** Rules 1 through 4 all sort by what a check blocks and how early.
   A reporter blocks nothing, so it buys none of the justification pre-push
   rests on: the tier exists to fail cheaply before CI, and a reporter never
   fails. It earns a local slot only when its output changes what the developer
   does in the next minute. An advisory whose output is read on the PR belongs
   on the PR, where the reader already is. Its cap counts against the tier
   budget at full weight, because latency is the entire cost it imposes and
   latency is the complaint this record answers.

   State the mechanism next to the job, because the two in use are not
   interchangeable. Five of the six pre-push reporters return 0 in their own
   code, where a test can read the guarantee: `python-lint-advisory` through
   `ruff --exit-zero`, and `additions-advisory`, `observation-sync-advisory`,
   `bot-cascade-advisory`, and `infrastructure-advisory` through handlers whose
   only top-level return is `return 0`. The sixth, `worktree-gc-report`, is
   different: `gc_worktrees.py` returns 2 or 3 on failure and the job appends
   `|| echo ...` in `lefthook.yml` to swallow it. Nothing reading the script
   can see that it is advisory, and deleting nine characters of YAML silently
   promotes it to a blocking gate that was never sized as one.

10. **A job that mutates local state is placed by ordering, not by tier: it
    runs before every gate that reads what it wrote.** `repair-packed-refs`
    writes `.git/packed-refs` and is first in the piped hook for that reason.
    It is still a gate, because it returns 1 on failure; "repair" names what it
    does on the happy path, not its blocking behavior, and the two must not be
    conflated when sizing it.

    Only one pre-push job is in this class. The review that raised this gap
    counted two, pairing `repair-packed-refs` with `mutation-safety`. That is
    wrong on the code: `mutation_workspace` takes `check` or `recover`, only
    `recover` mutates, and the hook runs `check`. `mutation-safety` is an
    ordinary read-only blocking guard already covered by rule 2, and placing it
    under a mutation rule would have justified an ordering constraint it does
    not need. Sixth instance of this branch's recurring pattern: a count
    carried from a name rather than from the thing named.

### Rejected: deferral by scheduler claim

`pre-pr-validation` re-runs four checks the pre-push fast stage also runs. An
earlier revision skipped them on a flag the job set for itself, justified by
the hook being `piped: true`.

That is unsound. Piping proves no earlier job **failed**. It does not prove one
**ran**. Every deferral target carries a `glob:` and `pre-pr-validation`
carries none. Measured on lefthook 2.1.10 against a fixture repo with one
glob-gated job and one un-gated job, pushing a docs-only commit:

```text
|  py-only-gate (skip) no matching push files
|  always-gate > ALWAYS GATE RAN
summary: (done in 0.02 seconds)   OK always-gate
EXIT=0
```

A glob-skipped job is indistinguishable from a passed one. A Python-only push
would have skipped Path Normalization and Planning Artifacts with nothing
running them; a workflow-only push would have skipped all four.

The test that shipped with it checked the wrong half: it resolved job names and
entry order, which catches a rename, and never read `glob`. Reverted.
`tests/ci/test_lefthook_prepush_tiering.py` now fails if the flag or a deferral
returns, and carries the condition that would make one sound. The duplication
is real and worth roughly 40s; issue #5317 carries three costed options.

### What ships with this record

- `_resolve_pytest_commands` routes the whole-suite fallback through
  `_full_suite_stand_in`, which collects rather than executes.
  `AI_AGENTS_PYTEST_FULL_SUITE_LOCALLY=1` restores execution and rejects any
  other value rather than quietly doing less.
- The collection stand-in carries a 300s budget rather than the execution
  suite's 780s, sized from the loaded 34.6s figure, not the idle 14s one.
- `run_pytest` refuses an empty command list: a push must never pass by running
  zero tests.
- `.github/workflows/pytest.yml` gained the Markdown roots its own tests read,
  so the delegation in rule 4 has somewhere to land at PR time.

### Measured in-hook, first real push of this branch

Lefthook 2.1.10, same 4-CPU container, `git push` of this branch. These are
in-hook numbers, so MUST-16 is satisfied and no projection is involved.

```text
total                        142.39s   (679s recorded for a comparable push)
  pre-pr-validation          105.48s   (110.12s recorded)
  fast parallel stage         55.32s   ( 56.21s recorded, max member 20.62s)
  python-tests                15.10s   (498.52s recorded)
  security-scan               13.02s
  every other job              under 3s each
```

Note the shape change. `python-tests` fell 33x and is no longer the hook.
`pre-pr-validation` is now 74% of it, which makes the duplication issue #5317
describes the next thing worth removing, not a leftover detail. The fast stage
did not move, and its 2.67x contention over 4 cores is unaddressed here.

One more thing this push demonstrated, unplanned. The `mutation-safety` guard
refused the first attempt in 0.33s, on leftover harness state from a SIGKILLed
run. Under the pre-change hook that refusal would still have been first, but
the point stands for the tier model: a cheap guard placed ahead of the
expensive stage returns its verdict in under a second. The guard's `recover`
command could not clear the marker, because it compares against a snapshot
taken before commits that legitimately advanced HEAD; clearing it needed a
manual check that the tree matched HEAD. Recorded for issue #5318.

## Known non-conformances

Rule 3 assigns end-to-end smokes, workflow runs, and full-scope static analysis
to CI. Five pre-push jobs match and stay:

| Job | Declared cap | Why it stays |
|---|---|---|
| `hook-anchoring-e2e` | 20m | ADR-071 placed it here deliberately; glob-gated to hook paths |
| `plugin-load-e2e` | 20m | ADR-071, same |
| `workflow-local-run` | 10m | glob-gated to `.github/workflows/**`; DEGRADED to a warning in a container, which has no actionlint, so its container cost is 0s and its cost on a developer machine is unmeasured |
| `python-type-check` | 2m | scoped to changed files; measured 2.73s in-hook |
| `security-scan` | 15m | ADR-054 sets an enforced 900s budget for it; not glob-gated |

Four are glob-gated, so they cost nothing on the change class this record
measured, and that was verified rather than assumed: on the second push of this
branch all four printed `(skip) no matching push files`. Attempts to measure
them firing were inconclusive, because each scopes its work to
`origin/main...HEAD` and short-circuits when the branch does not touch its
inputs. So the honest position is that these four remain **unmeasured while
firing**, and they are the pushes that can still outlive a container. That is
the tail this record does not close (issue #5318).

The two e2e smokes at 20m each set the expensive group's declared cost, so they
alone account for 1200s of the 2850s workstation total. Cutting those caps
needs a measurement, not a guess. In a container they are clamped to 150s
regardless, which is why the container bound does not wait on that
measurement.

ADR-054's 900s budget for `security-scan` is three times the 300s pre-push
target. The target does not overturn it. Whichever record is wrong, they cannot
both stand; reconciling them is out of scope here and named rather than left
for a reader to notice.

## Prior Art Investigation

### What Currently Exists

- **Structure being changed**: the pre-push job graph in `lefthook.yml` and the
  pytest command resolution in `scripts/validation/git_hook_policy.py`.
- **When introduced**: ADR-004 (2025-12-17) chose a custom pre-commit script.
  ADR-086 (2026-07-20, PR #3259) replaced the scheduler with Lefthook. ADR-054
  set the one qualitative pre-push cost bar. ADR-071 (2026-08-19) placed the
  credentialed e2e smokes in pre-push. Issue #5066 (2026-08-15) staged
  pre-push. Issue #5050 added import-graph test selection with a non-Python
  fail-safe.

### Historical Rationale

ADR-004's drivers were immediate feedback and one discoverable entry point.
Both still hold. Neither says what a tier may cost, so "run it locally too" was
always the locally optimal answer.

### Why Change Now

The suite grew to roughly 27,900 tests, so "run the tests locally" costs
minutes rather than seconds, and the common execution environment moved to
4-CPU containers with a reclamation deadline, which turns a slow hook into a
push that never lands. Import-graph selection (issue #5050) and collection now
cover what the local suite run covered, at a fraction of the cost. Neither
existed when the local suite run was placed.

Risk of the change: a defect that only an executed test catches surfaces in CI
rather than locally. Blast radius is one CI round trip per such defect, against
a status quo where the push does not complete.

## Rationale

### Alternatives Considered

| Alternative | Pros | Cons | Why Not Chosen |
|-------------|------|------|----------------|
| Raise the container's patience | No repository change | Not a repository setting | Rejected: accepts an eleven-minute local gate and asks the environment to tolerate it |
| Narrow the local selector to a per-path allowlist | Keeps local execution for real Python changes | An allowlist does not bound cost for a large Python change, where the graph maps everything and the subset is still large | Rejected as the primary fix. The fail-open objection an earlier revision gave was wrong: CI already maintains exactly such an allowlist and `runtime_read_patterns.txt` is nearly a copy of it. Making the two agree is worth doing and is issue #5318 |
| Drop `python-tests` from pre-push entirely | Cheapest possible hook | A broken import would reach CI and burn a whole matrix | Rejected: gives up the defect class that most deserves a local gate |
| Keep execution, drop the mutation, safe-push and pr-autofix partitions locally | Saves the measured 212s those three cost | Leaves the 258s bulk partition | Rejected as insufficient, though CI does run those three as separate matrix legs, so they were already duplicated |
| A hard hook deadline that defers remaining gates to CI on expiry | Bounds the push directly | Untried here; needs a resume story | Not chosen now, recorded because a container-reclaimed push is strictly worse than a self-aborted one, and that asymmetry deserves weighing (issue #5318) |
| Collect instead of execute on the fallback | 14s against 382s, still blocks import and syntax defects, CI executes the same commit | Gives up local assertion results for the fallback class | **Chosen** |

### Trade-offs

For a change the import graph cannot map, a failing assertion is discovered by
CI rather than by the push.

That trade rests on CI executing the commit, and the shape of that is worth
stating precisely because an earlier revision got it wrong. `pytest.yml` runs
the full partition matrix unconditionally in the merge queue
(`merge_group` is in `FORCE_RUN_EVENTS`, which bypasses the paths filter), and
at PR time only when the diff matches the filter. So `main` was never exposed.
What was exposed, before this change widened the filter, was a reviewer
approving a green PR whose relevant tests had not run. `Run Python Tests` is a
required context (`scripts/ci/ruleset_required_contexts.py`), and the same name
is carried by the skip-through job, so a required green check does not by
itself mean tests ran.

## Consequences

### Positive

- A pre-push on a Markdown change costs seconds of pytest rather than minutes,
  so it fits inside a container's lifetime.
- Placement is a decision with a stated target, so the next check that wants to
  be local has a rule to argue against rather than a precedent to follow.
- The gap between what CI skips and what the hook runs is closed for the common
  change class.
- Hook output on the fallback path dropped from 31,765 lines to 878, which is a
  token cost as well as a wall-clock one.
- Measured end to end on a real push: 142.39s against 679s recorded for a
  comparable push, a 4.8x reduction, with `python-tests` falling from 498.52s
  to 15.10s.

### Negative

- Local feedback for the fallback class is weaker. A test that fails an
  assertion, rather than failing to import, now surfaces in CI.
- `AI_AGENTS_PYTEST_FULL_SUITE_LOCALLY` is one more configuration axis, and an
  escape hatch nobody exercises rots. Its wiring is covered by a test.
- The duplication between `pre-pr-validation` and the fast stage stays, and
  costs roughly 40s per push, because the cheap way to remove it was unsound.
- The workstation declared sum is still 47.5 minutes against a 300s target, and
  the ratchet stops it rising rather than bringing it down. Closing that needs
  the unmeasured jobs measured (issue #5318). On a workstation a hung e2e smoke
  can still run for 20 minutes, which is slow rather than destructive.
- **The failure this record exists to stop is narrowed, not closed.** In a
  container no single *subprocess* can exceed 150s, which is asserted. That is
  not the same as a per-job bound, and an earlier revision of this section said
  it was. `run_pytest` holds an aggregate deadline over its children but at
  780s on the opt-in path, and `scan_pushed_heads` holds none at all: it loops
  over pushed refs and each scan gets a fresh clamp, so N refs cost up to N
  times 150s. Rule 8 therefore remains open for those two paths.

  The measured hook is ~148s end to end and the default collection path spawns
  one child, so the exposure is a tail case rather than the common one. That is
  an argument for sizing the fix deliberately, not for leaving the record
  claiming a bound it does not have. Corrected in review on PR #5319; the
  aggregate deadline is tracked in #5318.

### Neutral

- The cap on `python-tests` fell from 30m to 15m. It is the ceiling for the
  opt-in execution path, whose inner budget is 780s; the default collection
  path is bounded by the inner 300s budget, and by the 150s container clamp
  where one applies.
- Lefthook remains the local scheduler (ADR-086); protected CI remains the
  authoritative backstop.

## Re-evaluation Triggers

Revisit this record when any of these becomes true. Owner: the repository
maintainer; mechanism: a comment on issue #5315.

- A real push measures the pre-push hook above 300s.
- A new pre-push job is proposed.
- `pytest.yml` stops being a required context, or its merge-queue force-run is
  removed. Rule 4's premise dies with either.
- A defect reaches `main` that an executed local suite would have caught.

## Impact on Dependent Components

| Component | Dependency Type | Required Update | Risk |
|-----------|----------------|-----------------|------|
| `scripts/validation/git_hook_policy.py` | Direct | Whole-suite fallback routed through the collection stand-in with its own budget | Medium |
| `.github/workflows/pytest.yml` | Direct | Paths filter widened to the Markdown roots its own tests read | Medium |
| `tests/validation/test_pytest_import_selection.py` | Direct | Old tests asserted the fallback equals the executing partitions | Low |
| `tests/test_safe_push_pr_branch.py`, `tests/validation/test_pytest_parallelism_policy.py` | Direct | Multi-command budget and worker-flag contracts opt into local execution | Low |
| ADR-090 | Indirect | Its 30-minute lease TTL is calibrated against "the known 20 to 30 minute pre-push gate"; that input changed | Low |
| `.claude/rules/session-logs.md` MUST-2 | Indirect | Describes the episode ratchet as running inside `python-tests`, which is now true only on the executing path | Low |

## Implementation Notes

```bash
# Whole-suite execution, as pre-push ran it before this record
AI_AGENTS_PYTEST_FULL_SUITE_LOCALLY=1 AI_AGENTS_PYTEST_WORKER_CAP=4 \
  uv run --frozen python scripts/validation/git_hook_policy.py pytest

# What pre-push runs now for a Markdown-only push
AI_AGENTS_PYTEST_WORKER_CAP=4 \
  uv run --frozen python scripts/validation/git_hook_policy.py pytest README.md

# The selector's verdict for a given path
uv run --frozen python scripts/test_selection/select_tests.py --format json README.md
```

On a 48-thread workstation the opt-in path also needs
`AI_AGENTS_PYTEST_WORKERS=auto`, because `lefthook.yml` pins
`AI_AGENTS_PYTEST_WORKER_CAP=4` for the container case and the cap wins.

Every defect-class claim in rule 5 was probed against a throwaway tree, and the
two that failed are recorded as failing rather than dropped quietly.

## Related Decisions

- ADR-086: Lefthook owns local hook orchestration. This record says what the
  pre-push event may hold.
- ADR-071: placed the credentialed CLI e2e smokes in pre-push. Not overturned;
  listed under Known non-conformances.
- ADR-054: set the one prior pre-push cost bar, qualitatively, and an enforced
  900s budget for `security-scan` that this record's 300s target contradicts.
- ADR-049: pre-PR validation gates.
- ADR-101: enforcement planes. Complementary: that record asks whether a gate's
  verdict can be trusted, this one asks where a gate should run.
- ADR-073: frontmatter status enum and the `implemented` field's definition.
- ADR-004: superseded by ADR-086.

## References

- Issue #5315: the incident and the measurements.
- Issue #5317: the duplication this record declined to remove unsoundly.
- Issue #5318: the tail, the pre-commit measurement, and the selector/CI-filter
  reconciliation.
- Issue #4710: local hook and validation latency.
- Issue #5066: the fast-fail staging this record builds on.
- Issue #5050: import-graph test selection and its non-Python fail-safe.
- `.serena/memories/ci/ci-pre-push-wall-clock-is-python-tests.md`
- `.claude/rules/ci-scripts.md` MUST-14, MUST-16, MUST-19, MUST-21.
