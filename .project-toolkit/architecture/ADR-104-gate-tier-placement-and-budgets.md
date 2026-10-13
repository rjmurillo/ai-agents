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
`.project-toolkit/critique/ADR-104-debate-log.md`. The first revision was blocked by two
seats and this record is the rewrite. `implemented` stays false until the
branch merges, per ADR-073's definition of that field.

Acceptance was gated on an end-to-end wall-clock measurement of the hook during
a real push, because `ci-scripts.md` MUST-16 forbids sizing a pre-push budget
from a standalone run. That measurement now exists and is in Consequences
below: 142.39s, against 679s recorded for a comparable push. The gate is
cleared. The remaining reason this stays `proposed` is that the branch has not
merged.

Amended 2026-10-08 (PR #6239): the import-graph test selector is deleted.
Until 2026-10-09, pre-push by default ran pytest collection only over
`tests/`. The `AI_AGENTS_PYTEST_FULL_SUITE_LOCALLY=1` opt-in still runs the full
suite. In CI,
every pytest matrix leg runs its full partition on every event: the `test` job
has no job-level `if:` or `needs:` (`pytest.yml:262-265`). Four pinned files
(`_UNPARTITIONED_TESTS` in `run_pytest_partition.py`) run in `split-1` pin
steps. `security` and `test-windows-pwsh` remain gated by `check-paths` and
`scripts/ci/path_policy.yml`. The 300 s collection budget was not re-measured
after #6239. Text below that describes selection is history unless it says
otherwise.

Amended 2026-10-09 (owner decision, issue #6239 follow-up; the seed work and the
measurements followed on 2026-10-10): pre-push no longer only collects. It runs
`pytest --testmon` (pytest-testmon 2.2.0, MIT) over `tests/`, so tests impacted
by the branch run locally and a failure blocks the push. When `.testmondata` is
missing, the hook first fetches the database that main's CI built (see Seed and
fallback below). When that fetch failed, it built the database locally by running
the whole suite; the 2026-10-13 amendment below replaced that build with a
collection. CI keeps running every leg in full and is the gate.
Collection alone was not enough: it never ran an assertion, so a failure
surfaced only in CI and cost a round trip for each one.

Three facts of testmon 2.2.0 shape the command. The partitions pass
`-m "not integration"`, and testmon turns selection off whenever `-m` or `-k` is
present ("selection automatically deactivated because -m was used"), which would
run the whole suite on every push, so the hook adds `--testmon-forceselect`.
Python 3.14 makes coverage default to the sysmon core, which under-records, so
the hook sets `COVERAGE_CORE=ctrace` (9 selected tests against 56 in the replay
trial). And selection is best effort: testmon records which code each test runs
in-process, so it misses code a test reaches only through a subprocess
(confirmed in the 2026-10-09 trial: it did not re-select the two tests that fail
when `scripts/validate_skill_output.py` breaks).

The collection-only step was dropped, not kept first: the testmon run imports
every test module, so a broken import fails it at collection with the same exit
code. `AI_AGENTS_PYTEST_FULL_SUITE_LOCALLY=1` still runs the whole suite with no
selection. The hook runs every partition even when one fails and returns the
worst exit code (a signal-killed child counts as 1), so each partition records
its tests; stopping at the first failure left the others unrecorded and the next
push re-ran about 170 tests. The 2026-10-08 paragraph above and the collection
text below are history unless they say otherwise.

Amended 2026-10-13 (issue #6200, delegated owner decision): the pytest step is
bounded to the 300s target, in two parts. First, the default path has a 180s
budget, down from 780s; 780s stays with the
`AI_AGENTS_PYTEST_FULL_SUITE_LOCALLY=1` opt-in. A selection that does not finish
in 180s stops and fails the push with a message that names the opt-in. Second,
when `.testmondata` is missing and the seed fetch failed, the selection is the
whole suite and the hook does not start it. It collects the suite instead, which
still blocks a broken import, prints how many tests it did not run, and says CI
runs them. This reverses the 2026-10-09 acceptance of a local cold build. See
"Bounding the pytest step" below.

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

### The asymmetry that made it avoidable (as it was before #6239)

Amended 2026-10-08 (PR #6239): `scripts/test_selection/` is deleted and every
pytest matrix leg runs its full partition on every event. The probe below
records the asymmetry as it was.

`scripts/test_selection/select_tests.py` fell back to the whole suite on
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
someone measures it. Issue #5318 asked for that measurement and was closed
2026-10-02; this record holds none, so the figure is still unmeasured and has
no open owner.

What is enforced is the **declared** worst case, which is what a container
actually has to survive. `tests/ci/test_lefthook_declared_budget.py` sums each
hook's caps through lefthook's own scheduling semantics (top level piped, so
entries sum; a parallel group costs its slowest member; a piped group sums) and
holds the total down two ways. A ceiling in the test module runs anywhere and
needs no git. The ratchet proper recomputes the same sum from `lefthook.yml` as
committed on the base ref and requires the current total not to rise against it.

Both, because the ceiling alone was published here as a ratchet and is not one:
the number sits beside the assertion that reads it, so one edit raises a cap and
the ceiling together and both tests still pass. Review on PR #5319 found that.
The base-ref comparison has a baseline the branch cannot edit, which is the
property "may only fall" was claiming. Its normal enforcement point is CI, not
pre-push, which is the reverse of what an earlier revision of this paragraph
said. `pytest.yml` checks out with `fetch-depth: 0`, so PR CI has the base ref
and executes the comparison; pre-push runs only the tests testmon selects,
so it executes this test only when testmon finds the test's dependencies
changed. So a cap-only edit is caught in CI and not reliably locally. Where no base ref is reachable the comparison
skips and the ceiling is the only guard; git being absent is a different thing
and fails rather than skipping, because a gate that cannot tell "no base ref"
from "no git" disables itself and calls it an environment.

That number was 4170s for pre-push, 69.5 minutes, against real pushes of
142.39s. Caps resized from in-hook measurement bring it to 3450s. It
reached 2850s before review put `workflow-local-run` back at main's 30m:
that cut had no measurement behind it, and rule 7 is this record's own.

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

`git_hook_policy` answers the second question in two layers. `_run_command`
clamps its child's deadline to 150s when `_is_remote_container()` is true, and
`main` arms a watchdog at 165s covering the whole process. The second layer is
what makes the guarantee hold: the clamp bounds children, and review on PR
#5319 found three places the work is not a child, so a hang in selection or
setup passed every deadline and still ended in the reclaim. 15s of headroom so
an inner deadline fires first and the reader gets the specific message, the
same ordering ADR-086 item 9 requires between inner budgets and outer caps.
Workstations and CI are untouched. `tests/ci/test_lefthook_container_bound.py`
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
declared sum, workstation        3450s   57.5 min   (was 4170s)
largest single child, container    150s    2.5 min   (was 1800s)
```

No single pre-push **subprocess** can run longer than 150s inside a container.
That is the enforced property, and it is narrower than the per-job bound an
earlier revision of this paragraph claimed. `pre-pr-validation` does not route
through `_run_command` and carries its own 240s cap; every job whose work is a
single subprocess is bounded by the clamp.

Two jobs are not single-subprocess, so the per-subprocess clamp does not bound
them by itself, and each now carries a deadline for the whole job.
`run_pytest` clamps its aggregate, so the pytest step is held to 150s in a
container whichever path it takes. `scan_pushed_heads` clamps one budget across
every pushed ref and every target batch within a ref, where before each batch
got a fresh allowance and N refs cost up to N times 150s.

Rule 8 is closed for pre-push. It took four review rounds on PR #5319 to get
there, and the shape repeated each time: a clamp on one child was read as a
bound on a job that runs many. The record claimed the per-job bound before
either aggregate existed, which is why the correction is written here rather
than the claim quietly restated.

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
   remotely.** Ratchets, branch-scope and push-ref policy, and the tests
   pytest-testmon selects for the branch (best effort; CI runs the rest). The test is not "is this check valuable" but "does
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
   nothing, and not with a raised target. The whole-suite run became a
   whole-suite collection on 2026-10-08 and, on 2026-10-09, the testmon-selected
   run. State only the classes you probed, and probe them under production
   configuration. Collection was probed to block on a broken import and on a
   syntax error and to miss a missing fixture, two same-named test functions in
   one module, and a same-basename module collision. The testmon run keeps the
   first two catches because it collects the whole tree before it selects, and
   it adds the assertions of every test whose dependencies changed. Its probed
   miss is code a test reaches only through a subprocess.

   The same-basename collision was once published here as a catch. It is a
   collection error under pytest's default `prepend` import mode and not under
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

- `_resolve_pytest_commands` routes the default path through
  `_testmon_stand_in`, which returns the four suite partitions under
  `--testmon`. `AI_AGENTS_PYTEST_FULL_SUITE_LOCALLY=1` restores whole-suite
  execution without selection and rejects any other value rather than quietly
  doing less. (Revised 2026-10-09: this bullet first described a collection
  stand-in with a 300s budget sized from the loaded 34.6s figure; both are
  gone, and `TEST_COLLECTION_TIMEOUT_SECONDS` was deleted.)
- `run_pytest` refuses an empty command list: a push must never pass by running
  zero tests.
- `.github/workflows/pytest.yml` gained the Markdown roots its own tests read,
  so the delegation in rule 4 has somewhere to land at PR time.
- Amended 2026-10-08 (PR #6239): the collection stand-in was the only default
  path, because the import-graph selector was retired.
- Amended 2026-10-09: the default path is the testmon selection. The pre-push
  step runs with `COVERAGE_CORE=ctrace`, and `PYTEST_DIST_MODE` is `worksteal`
  (owner decision; see SPEC-6211) for CI and the hook alike.

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
manual check that the tree matched HEAD. Recorded for issue #5318, closed
2026-10-02 without a fix to that command recorded here.

## Known non-conformances

Rule 3 assigns end-to-end smokes, workflow runs, and full-scope static analysis
to CI. Five pre-push jobs match and stay:

| Job | Declared cap | Why it stays |
|---|---|---|
| `hook-anchoring-e2e` | 20m | ADR-071 placed it here deliberately; glob-gated to hook paths |
| `plugin-load-e2e` | 20m | ADR-071, same |
| `workflow-local-run` | 30m | glob-gated to `.github/workflows/**`; DEGRADED to a warning in a container, which has no actionlint, so its container cost is 0.42s measured in-hook and its cost on a developer machine is unmeasured. Cut to 10m on this branch and restored in review: rule 7 sizes a cap from a measured worst case, and the only path a container can time is the one the cap does not protect |
| `python-type-check` | 2m | scoped to changed files; measured 2.73s in-hook |
| `security-scan` | 15m | ADR-054 sets an enforced 900s budget for it; not glob-gated |

Four are glob-gated, so they cost nothing on the change class this record
measured, and that was verified rather than assumed: on the second push of this
branch all four printed `(skip) no matching push files`. Attempts to measure
them firing were inconclusive, because each scopes its work to
`origin/main...HEAD` and short-circuits when the branch does not touch its
inputs. So the honest position is that these four remain **unmeasured while
firing**, which is a gap in what their workstation caps are sized from, not in
the container bound. In a container each is one `git_hook_policy` process and
the watchdog stops it, so none of them can outlive the container. An earlier
revision of this paragraph said they could, contradicting the guarantee stated
two paragraphs down; caught in review on PR #5319. The measurement is still
owed. Issue #5318, which asked for it, was closed 2026-10-02; this record holds
no such measurement and no open issue owns it.

The two e2e smokes at 20m each set the expensive group's declared cost, so they
alone account for 1200s of the 3450s workstation total. Cutting those caps
needs a measurement, not a guess. In a container they are clamped to 150s
regardless, which is why the container bound does not wait on that
measurement.

ADR-054's 900s budget for `security-scan` and the 300s pre-push target measure
different things, so both stand. 900s is the per-job kill ceiling: the longest
a single job may run before it is killed. 300s is the whole-hook target: what a
push should cost end to end. One job can therefore run longer than 300s without reaching
its ceiling. ADR-054 carries the same reading in its 2026-09-29 amendment.
Reconciled under issue #5318, item 5 (issue closed 2026-10-02).

Measured in `.project-toolkit/metrics/gate-latency-v0.7.0.md` (PR #5813, one
4-CPU container, n=2 per pre-push class): `security-scan` 9.96s worst, whole
pre-push hooks 124s to 128s worst. That sample is small and carries no load
average, so it supports "not warranted on the measured classes", not a general
bound.

A hook-level deadline (issue #5318, item 4, closed 2026-10-02) is not adopted on these numbers.
The worst measured push was 128s, 43 percent of 300s. The `workflows` class,
which fires `workflow-local-run` at a 30m cap, is outside that conclusion: it
is unmeasured because it needs `act` and a container runtime, which the
measuring environment lacks. Revisit the deadline when that job is measured or
when any measured push passes 150s.

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
push that never lands. Collection now covers the defect class the local suite run
most reliably caught, at a fraction of the cost, and every pytest matrix leg in
CI runs its full partition on every event.
Import-graph selection (issue #5050) also existed when this record was written.
PR #6239 deleted it.

Why the selector existed, and why it can go. Issue #5050 added it because the
full suite cost 878 s per push, and earlier path filters had produced false
greens (#4345, #4408). That per-push cost no longer bites: pre-push runs only
the tests testmon selects. Every pytest matrix leg runs
its full partition on every event, and the selector narrowed only 5 of 30
PR runs (30 of the 32 pull_request runs among the 80 most recent
completed `pytest.yml` runs, 2026-10-08). It saved an inferred 40 to 60 s of a roughly 480 s median,
inferred from job medians and not measured end to end. Test selection is
Context, not Core (owner decision 2026-10-07), so the repository buys
(pytest-split) rather than builds.

Limits of that evidence, stated so a later reader can weigh them. pytest-testmon
2.2.0 was rejected as a CI gate on one confirmed miss: it did not select the
tests that catch a broken subprocess-run script, on this repository with its
default coverage core. That rejection is scoped to that version and setup and
still stands for CI. On 2026-10-09 the owner adopted it for pre-push only,
where a miss costs one CI round trip because CI runs everything. The
5 of 30 rate covers pull_request runs only; push and merge_group timing was not
sampled. The CI speed target in #6239 is measured on the pull request's own runs
before merge.

Revert path: the change is one pull request of about 20 files. To go back to
collection only, delete `scripts/validation/testmon_seed*.py`, the
`testmon-seed` job in `pytest.yml`, `tests/validation/testmon_seed_helpers.py`
and the `test_testmon_seed*`, `test_pre_push_testmon*` and
`test_testmon_seed_job*` tests, remove `--testmon` from
`_testmon_commands`, and restore the collection command from git history.

Risk of the change: a defect that only an executed test catches surfaces in CI
rather than locally. Blast radius is one CI round trip per such defect, against
a status quo where the push does not complete.

## Rationale

### Alternatives Considered

| Alternative | Pros | Cons | Why Not Chosen |
|-------------|------|------|----------------|
| Raise the container's patience | No repository change | Not a repository setting | Rejected: accepts an eleven-minute local gate and asks the environment to tolerate it |
| Narrow the local selector to a per-path allowlist | Keeps local execution for real Python changes | An allowlist does not bound cost for a large Python change, where the graph maps everything and the subset is still large | Rejected as the primary fix. The fail-open objection an earlier revision gave was wrong: CI already maintains exactly such an allowlist and `runtime_read_patterns.txt` is nearly a copy of it. Making the two agree is worth doing and is issue #5318. Moot since #6239 retired the selector |
| Drop `python-tests` from pre-push entirely | Cheapest possible hook | A broken import would reach CI and burn a whole matrix | Rejected: gives up the defect class that most deserves a local gate |
| Keep execution, drop the mutation, safe-push and pr-autofix partitions locally | Saves the measured 212s those three cost | Leaves the 258s bulk partition | Rejected as insufficient, though CI does run those three as separate matrix legs, so they were already duplicated |
| A hard hook deadline that defers remaining gates to CI on expiry | Bounds the push directly | Untried here; needs a resume story | Not adopted for the whole hook. Weighed under issue #5318, item 4: the container-reclaim asymmetry is real, but #5813 measured whole pre-push hooks at 124s to 128s against the 300s target on the measured classes. `workflow-local-run` is unmeasured. Revisit when it is measured or a measured push passes 150s. Issue #6200 adopted the narrow form for the pytest step alone: a 180s step budget plus a cold-start deferral (see "Bounding the pytest step") |
| Size threshold on the selected subset (issue #6200, option 1) | Avoids starting a run that cannot finish | The selection size is known before the run only when testmon has no database; throughput varies 9x between selections (808 tests in 49.9s against 49,492 in 339.5s), so no test count maps to a time | Adopted at the one size that is known: the whole suite, when testmon has no database |
| Lower the step budget alone (issue #6200, option 2) | One constant; catches every overrun | Inferred, not measured: a cold run killed at the budget records no database, so the next push repeats it and the push stays blocked until a seed exists | Adopted for the selection, together with the cold deferral |
| Collect instead of execute on the fallback | 14s against 382s, still blocks import and syntax defects, CI executes the same commit | Gives up local assertion results; since #6239 that covers every push, not only the fallback class | Chosen 2026-10-08, superseded 2026-10-09 by the testmon row, and re-adopted 2026-10-13 for the no-database case only (issue #6200) |
| Run the tests pytest-testmon selects in pre-push (buy, not build) | Impacted tests run locally so CI failures are rare; a repeat run with few changes took 4 to 36s in the replay trial; imports are still checked because testmon collects the whole tree | The cold run builds the database over the whole suite: 575 s at 4 workers, 1.9x the 300s target (the CI seed was the mitigation; since 2026-10-13 a missing seed means collection, not a build); selection misses code run only through a subprocess; local `.testmondata` state; a lock change forces a full run | **Chosen** 2026-10-09 (owner decision). The cold-run cost listed here was accepted then and removed 2026-10-13 by issue #6200 |

### Seed and fallback

Measured 2026-10-09 and 2026-10-10 on the owner's workstation; the raw lines are
in `.project-toolkit/analysis/testmon-prepush-measurements.md`, and every figure
is one run. Through `lefthook run pre-push --job python-tests` at the cap of 4
workers: 575 s with no database, and 7.8 s with a warm one. The cold run is 1.9x
the 300 s pre-push target. The warm path satisfies rule 2: it costs seconds and
saves a CI round trip. The cold path is an accepted breach of rules 2 and 5. The
seed is the mitigation. Issue #6200 changed what happens where no seed can be
fetched: the breach no longer stands, because the cold run is not started (see
"Bounding the pytest step").

A CI job seeds the database. The `testmon-seed` job in `pytest.yml` runs on
`push` to `main` only, runs the hook's own command with the hook's partitions,
markers, worker cap and `COVERAGE_CORE=ctrace`, and uploads `.testmondata` as
`testmon-db-<key>` with 7 day retention. It has its own 3300 s run budget through
`AI_AGENTS_TESTMON_SEED_BUDGET_SECONDS`, read only when the seed marker is set,
because the hook's 780 s suite budget would kill a 30 minute run. It uploads only
when the hook exits 0, so a failed partition, a budget kill or a signal never
leaves a partial database behind. The build script exits with the hook's failure
code, so a failing run turns the seed job red instead of hiding behind a warning;
the job is outside `test-result` needs, so that red never reaches `Run Python
Tests`. The key is a SHA-256 over `uv.lock` and
`pyproject.toml`, computed by `scripts/validation/testmon_seed.py`. The job was
specified to use `hashFiles`; the Actions runtime owns that function and its
byte recipe cannot be checked from a checkout, and one differing byte would
silently disable the seed, so the workflow and the hook share one Python function
instead. The job is outside `test-result` needs, so a slow, failed or skipped seed
cannot change `Run Python Tests`. Its 60 minute timeout is an exception to the 10
minute cap issue #4854 set, recorded in
`tests/workflows/test_pytest_job_timeout.py`. Run 38015601869 on main spent 1390 s
across its six 4-vCPU legs without testmon, and ctrace adds about 1.4x, so the
estimate is about 30 minutes. That estimate is inferred, not measured on a runner;
the first main push after merge gives the figure. One database cannot be split
across jobs because testmon keys it by path.

When no `.testmondata` exists the hook runs a read-only `gh api` fetch under one
30 s deadline. It lists `pytest.yml` runs with `event=push` on `main`, then
accepts a run only if the run object itself says: event `push`, head branch
`main`, head repository `rjmurillo/ai-agents`, conclusion `success`, path
`.github/workflows/pytest.yml`, and a full 40 character head SHA that
`git merge-base --is-ancestor` finds in local `origin/main`. A missing
`origin/main` means no network call and no seed, so the hook collects the suite,
and an unknown commit skips that run. It takes the newest accepted run with an
unexpired artifact named exactly for this checkout's key. The zip streams into a fresh private temporary
directory with a 256 MB cap enforced while reading. The hook reads one member by
the exact name `.testmondata`, and any other member name is ignored. The
database must start with the SQLite magic bytes, and the hook stages it through a
file opened with O_CREAT|O_EXCL|O_NOFOLLOW before renaming it into place. Pull
request and fork runs are never read. Any failure (no `gh`, not logged in,
offline, no `origin/main`, no match, timeout, oversize, bad zip) prints one line
and the hook collects the suite instead of building the database.

Who can produce a seed: anything that pushes to `main`, including an
administrator who bypasses review, and any code that runs inside the
`testmon-seed` job. The hook trusts that origin and nothing else. A poisoned
database can do two things. It can suppress local selection, so a push skips
tests it should have run, which CI still runs. Or it can exercise SQLite's
parser, which has no code-execution path from a data file. testmon 2.2.0 reads
the file with SQLite queries and has no pickle, marshal or exec path. CI runs
everything either way, so the worst case is a false local pass that CI catches.

The database is portable between checkout paths. A test builds one in a runner
path, copies the tree to a different path, and runs testmon: 0 tests selected,
and a one-file edit selects exactly the tests that import it
(`tests/validation/test_testmon_database_portable.py`). The same check on this
repository, with a second checkout and a separate virtualenv, selected 0 tests
across all four partitions in 7 s (one run). testmon also rejects the database
when the Python or package versions differ, which is the conservative failure.

### Bounding the pytest step

Issue #6200, decided 2026-10-13 by the agent that fixed it, under the owner's
delegation of 2026-10-11 for that issue. The delegation reached the agent in its
task text, not in a repository file or an issue comment, so no URL records it.
As relayed: where the issue leaves a design choice to the owner, pick the option
the issue or its comments recommend; if none, pick the option with the best
evidence and smallest blast radius. The issue recommends none of its three
options. The owner can reverse the call; the revert path is at the end of this
section. The issue was filed 2026-10-07 against the import-graph
selector, which picked 835 to 1310 test files for a Markdown-only change and ran
them for 212s to over 260s against a 780s inner budget and a 15m lefthook cap.
#6239 deleted that selector and #6261 replaced it with testmon, so the subset
sizes in the issue are gone. The missing bound was not: the step could still run
780s inside a 15m cap.

Measured 2026-10-13 on a 48-thread workstation shared with other sessions (load
average 4.36, 7.01 and 8.52 at the first run's start; later runs were not
checked), scaled worker cap, current main. Raw lines are in
`.project-toolkit/analysis/testmon-prepush-measurements.md`. Every figure is one
run with no variance estimate, and no host with fewer than 48 threads was
measured.

| Case | Tests | Wall |
|---|---|---|
| Warm database, nothing changed | 0 selected | 4.4s |
| Seeded, 73 files behind main | 808 run | 49.9s |
| Seeded fresh worktree, in-hook beside the other jobs | not counted | 31.1s |
| No database, run in sequence | 49,666 passed, 2 failed | 462s (bulk 339.5s, mutation 96.6s) |
| No database, collect only | 49,808 collected | 20.5s |

Older evidence, not re-measured: the 2026-10-08 replay trial (a 13,735-test bulk
slice on a loaded host with the default `sysmon` core) selected 1 to 877 tests
in 4.9s to 35.6s for six main commits, and two further replayed commits changed
`uv.lock` and re-ran every test.

A whole push measured 196s in-hook (192.7s with a warm database), with
`push-ref-policy` excluded because its security-marker check blocks a branch
that has no `/review` marker. The stages before the expensive group took about
26s, derived from the lefthook summary (193s wall minus `pre-pr-validation` at
166s to 170s), and `pre-pr-validation` was the longest job in that group, not
pytest. Earlier measured pushes took 124s to 128s (see Known non-conformances).

Options from the issue and the call:

- **Size threshold.** Not adopted as a test count. The cold bulk run ran 146
  tests per second and the seeded run 16. The data fit a fixed cost plus a
  per-test cost that varies by test, and neither magnitude was isolated. Two
  points fit no N that converts to a time. The one size known before a run starts is the whole suite, which is what
  testmon selects when it has no database. The threshold applies there only.
- **Time budget.** Adopted for the selection: 180s. The 26s of stages before the
  group plus 180s is 206s, under the 300s target with 94s of margin. That sum
  is arithmetic from one in-hook run. Pytest running to 180s beside
  `pre-pr-validation` was not measured, and the seed fetch (30s cap) spends the
  same deadline, so a fetched run has about 150s. Inferred, not measured: a
  budget alone cannot serve the cold case, because a killed run records no
  database, so the next push repeats it.
- **Both.** Chosen. The issue's "below, at, above the threshold" tests became
  database finished, database interrupted (`user_version` 0 or not SQLite), and
  database missing, because the only size known before a run is the whole suite.
  A smaller local subset after collection (a smoke run) was not weighed: it would
  need its own selection rule, which testmon already provides when a database
  exists. With no database and no seed the hook collects the suite
  instead of running it (20.5s). Collection imports every test module, so a
  broken import or a syntax error still blocks the push. The hook prints how
  many tests it did not run and says CI runs them on the pull request and in the
  merge queue. Every pytest leg of `pytest.yml` runs in full on those events and
  `Run Python Tests` is a required context
  (`scripts/ci/ruleset_required_contexts.py`), so a deferred test still runs
  before merge. A branch pushed with no pull request has no CI run yet.

Why an overrun fails the push instead of deferring: the issue specifies it, and
a run killed at the budget cannot say which tests it did not reach, so there is
nothing to list and nothing to promise CI will run. Tests that failed before the
kill are real failures. The message keys on a child having been killed, or a
partition refused for lack of time, not on the clock, and it tells the developer that a dependency-file change needs the
opt-in on each push.

Visibility: `lefthook.yml` sets `output: false`, and a passing pre-push run
printed nothing in the 2026-10-13 runs, including the testmon banner. A cold
deferral exits 0, so its "Not run locally" notice reaches the developer only when
the run is repeated with output enabled (`LEFTHOOK_OUTPUT=summary,success,failure`
was the setting used). Failing runs did print under `output: false` in the same
session (the dash-prohibition and security-marker failures in the measurements
file). Changing `output` is outside this change.

The declared bound is the inner budget. `lefthook.yml` keeps `timeout: 15m` on
`python-tests` because the opt-in needs it; `AI_AGENTS_PYTEST_FULL_SUITE_LOCALLY=1`
runs the whole suite with no selection, ignores the deferral, and keeps the 780s
budget. The `testmon-seed` CI job sets `AI_AGENTS_TESTMON_NO_SEED` and still
builds the database from nothing under its own 3300s budget.

Reversal, stated plainly: on 2026-10-09 the owner accepted a local cold build as
a breach of rules 2 and 5 and accepted that a container could not finish it.
This amendment removes that breach. Accepted gaps, none measured beyond what is
cited above:

- A developer with no seed never builds a local database and gets collection on
  every push until a seed exists, and a passing push shows no sign of it.
- The first run after seeding a worktree failed once with the xdist
  "Different tests were collected" error of issue #6477. It passed on the second
  run. This amendment neither causes nor fixes it.
- A `uv.lock` or `pyproject.toml` change with a database already present
  re-selects the whole suite. The run passes 180s and fails the push, and the
  next push repeats it, because the opt-in does not refresh `.testmondata`. The
  opt-in is the way through, at 780s outside a container and 150s inside one,
  where it cannot finish. Two of eight replayed main commits changed `uv.lock`,
  so this is not rare. No test of the lock-change cost exists.
- 180s is sized on a 48-thread host. A 4 to 8 thread machine runs 4 workers and
  may pass 180s on selections that took 50s here.
- The "did not finish" line is local stdout, so the new re-evaluation trigger
  below has no collector, like the seed trigger beside it.

Revert: restore `TEST_SUITE_TIMEOUT_SECONDS` as the default budget in
`_suite_budget_seconds` (and inline `_seed_budget_seconds`), and delete
`PRE_PUSH_SELECTION_TIMEOUT_SECONDS`, `_PYTEST_NO_TESTS_COLLECTED`,
`_should_defer_cold_selection`, `_collect_instead`, `_tail_of_output`,
`_report_selection_overrun`, `_PytestOutcome` (return plain exit codes from
`_run_pytest_lanes` and inline `_run_selected_partitions` back into `run_pytest`),
`scripts/validation/pytest_deferral.py` and its tests
(`tests/validation/test_pytest_deferral.py`,
`tests/validation/test_pre_push_cold_deferral.py`). Restore the build message in
`_seed_testmon_database` and the warm default in
`tests/validation/pre_push_testmon_helpers.py`, and revert the comment edits in
`lefthook.yml`, `.github/workflows/pytest.yml` and
`scripts/validation/testmon_seed.py`.

### Trade-offs

A failing assertion testmon does not select is discovered by CI rather than by
the push. Before #6239 this held for changes the import graph could not map.
Between #6239 and 2026-10-09 it held for every push. Now it holds
for the tests testmon does not select: code reached only through a subprocess.
A first push with no database and no seed collects the suite and runs no test
(issue #6200), so CI is the first run of every test on that push. The
`AI_AGENTS_PYTEST_FULL_SUITE_LOCALLY=1` opt-in still runs the full suite.

That trade rests on CI executing the commit, and the shape of that is worth
stating precisely because an earlier revision got it wrong. The `test` job in
`pytest.yml` has no `needs:` and no job-level `if:` (its comment cites ADR-101
requirement 1), so the full partition matrix runs on every event, including
pull requests whose diff matches no path filter. `check-paths` still computes
`python-changed` and forces it true for `merge_group` through its
`FORCE_RUN_EVENTS: merge_group` setting, but that output no longer gates the
partitions. An earlier revision of this paragraph said the matrix ran
unconditionally only in the merge queue and at PR time only when the diff
matched the filter; that described the filtered workflow retired by PR #6239.
`Run Python Tests` is a required context
(`scripts/ci/ruleset_required_contexts.py`), and the same name is carried by the
skip-through job, so a required green check does not by itself mean tests ran.

Since PR #6239 no leg narrows what it runs. Every pytest matrix leg runs its
full partition on every event through `scripts/ci/run_pytest_partition.py`
(the `test` job has no job-level `if:` or `needs:`, `pytest.yml:262-265`). Four
pinned files run in `split-1` pin steps. `scripts/ci/path_policy.yml` still
drives the `check-paths` gate for `security` and `test-windows-pwsh`.

## Consequences

### Positive

- A pre-push on a Markdown change selects few or no tests under testmon, so it
  costs seconds of pytest once `.testmondata` exists. The first push without a
  seed does not run tests at all: it collects the suite (see Negative).
- Placement is a decision with a stated target, so the next check that wants to
  be local has a rule to argue against rather than a precedent to follow.
- The gap between what CI skips and what the hook runs is closed for the common
  change class.
- Hook output on the collection path dropped from 31,765 lines to 878, which is
  a token cost as well as a wall-clock one. The three-`-q` collection command
  that produced it was deleted 2026-10-09; testmon runs print pytest's normal
  header and summary.
- Measured end to end on a real push while pre-push only collected: 142.39s against 679s recorded for a
  comparable push, a 4.8x reduction, with `python-tests` falling from 498.52s
  to 15.10s.

### Negative

- Local feedback is best effort. A test testmon does not select, because it
  reaches code only through a subprocess, surfaces in CI. Before #6239 this
  held only for the fallback class; between #6239 and 2026-10-09 it held for
  every assertion.
- Consequences of the testmon default, stated plainly:
  - Tests that reach code only through a subprocess are never selected when
    that code changes.
  - A branch far from main re-selects many tests, and a lock change re-selects
    all of them. A branch that changes `uv.lock` or `pyproject.toml` has no seed
    for its key until it merges. With a local database already present the full
    re-selection runs, passes the 180 s budget, and fails the push with a
    message naming the opt-in. With no database the hook collects instead.
  - No network, no `gh`, or no `gh` authentication means no seed, so the push
    collects the suite and runs no test.
  - In a managed container the 150 s clamp applies to the step as a whole.
    Collection is expected to fit inside it (20.5 s on a 48-thread host);
    nobody has measured it in a container.
  - The seed artifact expires after 7 days. If main has no push for 7 days, the
    next push without a local database collects the suite.
  - Nothing builds a local database except a seed. A developer who stays offline
    never gets selection and gets collection on every push.
  - The seed uploads only from a passing main run, so a main push with any
    failing test produces no seed.
  - The seed job costs about 30 runner-minutes on every main push. That is
    inferred from run 38015601869 and stays inferred until the first main run
    measures it.
- `AI_AGENTS_PYTEST_FULL_SUITE_LOCALLY` is one more configuration axis, and an
  escape hatch nobody exercises rots. Its wiring is covered by a test.
- The duplication between `pre-pr-validation` and the fast stage stays, and
  costs roughly 40s per push, because the cheap way to remove it was unsound.
- The workstation declared sum is still 57.5 minutes against a 300s target, and
  the ratchet stops it rising rather than bringing it down. Closing that needs
  the unmeasured jobs measured. Issue #5318 asked for that and is closed, so no
  open issue carries it. On a workstation a hung e2e smoke
  can still run for 20 minutes, which is slow rather than destructive.
- **The failure this record exists to stop is closed for pre-push, and the
  route to closing it is the negative worth keeping.** In a container no single
  subprocess exceeds 150s, and the two jobs that run several subprocesses now
  hold their own aggregate deadlines, so no pre-push job can outlive the
  container. An earlier revision of this section asserted that bound before
  either aggregate existed, on the strength of the per-child clamp.

  Four review rounds were spent on the same confusion: a clamp on one child
  read as a bound on a job that runs many. `run_pytest` was fixed first,
  `scan_pushed_heads` last, and in between this paragraph twice described a gap
  the previous commit had closed. The lesson is not about clamps. A safety
  claim that is one inference away from what the code enforces will be made
  again, and the only thing that caught it each time was a reviewer reading the
  loop rather than the constant.

### Neutral

- The cap on `python-tests` fell from 30m to 15m. It is the ceiling for the
  opt-in, whose inner budget is 780s. The default path's inner budget is 180s
  (issue #6200). In a managed container `run_pytest` clamps the budget to 150s
  for the step as a whole. The cold deferral is expected to fit inside it;
  nobody has measured a collection inside a container.
- Lefthook remains the local scheduler (ADR-086); protected CI remains the
  authoritative backstop.

## Re-evaluation Triggers

Revisit this record when any of these becomes true. Owner: the repository
maintainer; mechanism: a comment on issue #5315.

- A real push measures the pre-push hook above 300s.
- Pushes fail the 180s selection budget more than 3 times in a month, counted
  from the "did not finish" line the hook prints. That moves the budget or the
  deferral rule.
- The seed is missing or failed on more than 3 cold pushes in a month, counted
  from the one-line fallback message the hook prints.
- A coverage or Python upgrade changes the ctrace or sysmon behavior, which
  `COVERAGE_CORE=ctrace` assumes.
- The first main run of `testmon-seed` is measured against the 30 minute
  estimate and the 60 minute cap.
- A defect reaches CI that testmon did not select and an executed local run
  would have caught more than once. That counts against best-effort selection.
- A new pre-push job is proposed.
- `pytest.yml` stops being a required context, or its merge-queue force-run is
  removed. Rule 4's premise dies with either.
- A defect reaches `main` that an executed local suite would have caught.

## Impact on Dependent Components

| Component | Dependency Type | Required Update | Risk |
|-----------|----------------|-----------------|------|
| `scripts/validation/git_hook_policy.py` | Direct | Default path runs the four suite partitions under `--testmon` with `COVERAGE_CORE=ctrace`; the collection stand-in and its 300s budget are deleted | Medium |
| `.github/workflows/pytest.yml` | Direct | Paths filter widened to the Markdown roots its own tests read; every pytest matrix leg runs its full partition since PR #6239 | Medium |
| `tests/validation/test_pytest_import_selection.py` (deleted by #6239), `tests/validation/test_pre_push_collection_only.py`, `tests/validation/test_collection_probes.py`, `tests/validation/test_collection_contract_surfaces.py` (all deleted 2026-10-09) | Direct | Old tests asserted pre-push collects only; `tests/validation/test_pre_push_testmon.py` asserts the testmon contract | Low |
| `scripts/ci/path_policy.{py,yml}` | Direct | Decides whether `security` and `test-windows-pwsh` run, through the `check-paths` gate. Head-editable. `/scripts/ci/` already owns it (`.github/CODEOWNERS:61`) | High |
| The pytest-split durations cache and `scripts/ci/run_pytest_partition.py` membership | Direct | The map lives in the main-scope cache, saved only on a push to main (`tests/ci/test_pytest_split_durations_save.py`). A pull request can write only its own `refs/pull/N/merge` scope, and only that pull request's reruns read it, so the worst it can do is skew its own balance. The invariant that makes the cache safe: pytest-split assigns every collected test to exactly one group, so a hostile or empty map ends red (exit 5 or 3) or unbalanced, never green with tests skipped (`tests/ci/test_pytest_split_pool.py`, `tests/ci/test_pytest_split_hostile_durations.py`). A cold or evicted cache (GitHub evicts caches idle for 7 days) makes the legs split evenly by test count with a `::warning`; that is a latency risk, not a correctness risk, and the blocking leg gate (480 s, in the `coverage` job that `Run Python Tests` requires) catches a leg that gets too slow. `run_pytest_partition.py` itself can still change the pool ignores, which is why it is Medium and owned by `/scripts/ci/`. The committed `tests/.test_durations` and its CODEOWNERS rule are removed | Medium |
| `tests/test_safe_push_pr_branch.py`, `tests/validation/test_pytest_parallelism_policy.py` | Direct | Multi-command budget and worker-flag contracts opt into local execution | Low |
| ADR-090 | Indirect | Its 30-minute lease TTL is calibrated against "the known 20 to 30 minute pre-push gate"; that input changed | Low |
| `.claude/rules/session-logs.md` MUST-2 | Indirect | Describes the episode ratchet as running inside `python-tests`, which is now true only when testmon selects that test or on the full-suite path | Low |

## Implementation Notes

```bash
# Whole-suite execution, as pre-push ran it before this record
AI_AGENTS_PYTEST_FULL_SUITE_LOCALLY=1 AI_AGENTS_PYTEST_WORKER_CAP=4 \
  uv run --frozen python scripts/validation/git_hook_policy.py pytest

# What pre-push runs now for every push: the tests testmon selects (2026-10-09)
AI_AGENTS_PYTEST_WORKER_CAP=4 \
  uv run --frozen python scripts/validation/git_hook_policy.py pytest
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
  900s per-job kill ceiling for `security-scan`. It is compatible with this
  record's 300s whole-hook target (see Known non-conformances).
- ADR-049: pre-PR validation gates.
- ADR-101: enforcement planes. Complementary: that record asks whether a gate's
  verdict can be trusted, this one asks where a gate should run.
- ADR-073: frontmatter status enum and the `implemented` field's definition.
- ADR-004: superseded by ADR-086.

## References

- Issue #5315: the incident and the measurements.
- Issue #5317: the duplication this record declined to remove unsoundly.
- Issue #5318 (closed 2026-10-02; selector part moot after #6239): the tail, the
  pre-commit measurement, and the selector/CI-filter reconciliation. The
  measurements it asked for are not recorded here.
- Issue #4710: local hook and validation latency.
- Issue #5066: the fast-fail staging this record builds on.
- `scripts/validation/testmon_seed.py` and the `testmon-seed` job in
  `.github/workflows/pytest.yml`: the seed fetch and the main-push build.
- Issue #5050: import-graph test selection and its non-Python fail-safe.
  Retired by PR #6239.
- PR #6239: deleted the test selector; pre-push collected only until 2026-10-09,
  when it began running the tests testmon selects.
- `.serena/memories/ci/ci-pre-push-wall-clock-is-python-tests.md`
- `.claude/rules/ci-scripts.md` MUST-14, MUST-16, MUST-19, MUST-21.
