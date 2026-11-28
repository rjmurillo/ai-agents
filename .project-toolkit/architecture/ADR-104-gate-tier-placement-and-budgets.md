---
# taste-lint: ignore file-size, ten numbered rules cited by number from the debate log and from tests; splitting renumbers them and the linter's suggested split into helpers, types, and constants has no meaning for a decision record.
id: ADR-104
status: accepted
date: 2026-11-27
decision-makers: [rjmurillo]
supersedes: []
superseded-by: null
explainer: null
implemented: true
---

# ADR-104: Gate Tier Placement

## Status

Accepted 2026-11-25 by owner direction (issue #7636); amended 2026-11-26 and
2026-11-27 by owner direction. Original six-seat adr-review debate held 2026-08-25
(`.project-toolkit/critique/ADR-104-debate-log.md`); merged as PR #5319
(`107205cf7`, 2026-08-26), so `implemented` is true per ADR-073. Acceptance was
gated on an in-hook wall-clock measurement per `ci-scripts.md` MUST-16 (cleared
at 142.39s against 679s recorded for a comparable push).

Amended 2026-11-26 (owner direction following multi-worktree host-contention
diagnosis; six-seat debate log at
`.project-toolkit/critique/ADR-104-prepush-pytest-removal-debate-log.md`;
empirical report at `.project-toolkit/analysis/host-contention-2026-11-26.md`):
both `python-tests` and `zero-collection-tests` are removed from `lefthook.yml`
`pre-push`. CI `.github/workflows/pytest.yml` runs `zero-collection-guard`
(`:116-146`) and every pytest partition leg (`:318-380`) unconditionally on
`push` to `main`, `pull_request` to `main`, and `merge_group` to `main`, feeding
required branch-protection check `Run Python Tests` (`test-result`,
`:1048-1108`). Local on-demand execution (`uv run pytest`,
`uv run python scripts/validation/git_hook_policy.py pytest`,
`AI_AGENTS_PYTEST_FULL_SUITE_LOCALLY=1`, and
`uv run python scripts/validation/check_zero_collection_tests.py`) remains
intact, and `scripts/validation/checks_ci_parity.py`
(`validate_unused_dependencies`) now passes `--isolated` to `uv run` so
`pre_pr.py` never mutates a worktree `.venv` with the `eval` extra (`openai`).
See `## Amendment 2026-11-26` and `## Amendment 2026-11-27` below.

**Historical amendments (superseded for `pre-push` by 2026-11-26; kept for
on-demand `git_hook_policy.py pytest` context):**

- *2026-10-08 (PR #6239)*: deleted the import-graph test selector and switched
  pre-push to pytest collection only over `tests/`. In CI, every pytest matrix
  leg runs its full partition unconditionally (`pytest.yml:318-324` has no
  job-level `if:` or `needs:`); four pinned files (`_UNPARTITIONED_TESTS`) run
  in `split-1` pin steps; `security` and `test-windows-pwsh` stay gated by
  `check-paths` (`scripts/ci/path_policy.yml`).
- *2026-10-09 (issue #6239 follow-up; seeded/measured 2026-10-10)*: switched
  pre-push to `pytest --testmon` (pytest-testmon 2.2.0, MIT) with
  `--testmon-forceselect` (needed because partitions pass `-m "not integration"`),
  `COVERAGE_CORE=ctrace` (Python 3.14's default `sysmon` core under-recorded:
  9 vs 56 selected tests), and a CI `testmon-seed` DB fetch. Selection is best
  effort and misses subprocess-only code; all partitions ran even on failure so
  each recorded its tests.
- *2026-10-13 (issue #6200, delegated owner decision)*: bounded the default
  testmon step to 180s (keeping 780s under `AI_AGENTS_PYTEST_FULL_SUITE_LOCALLY=1`)
  and deferred missing-seed runs to whole-suite collection instead of a local
  cold build.

## Date

2026-08-25 (amended 2026-10-08, 2026-10-09, 2026-10-13, 2026-11-26)

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
and executes the comparison; pre-push no longer runs pytest (2026-11-26
amendment), so a cap-only edit is caught in CI rather than locally. Where no base ref is reachable the comparison
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
declared sum, workstation        3330s   55.5 min   (ceiling 3450s / 57.5 min; was 4170s)
largest single child, container   150s    2.5 min   (was 1800s)
```

No single pre-push **subprocess** can run longer than 150s inside a container.
That is the enforced property, and it is narrower than the per-job bound an
earlier revision of this paragraph claimed. `pre-pr-validation` does not route
through `_run_command` and carries its own 240s cap; every job whose work is a
single subprocess is bounded by the clamp.

Among multi-subprocess jobs, `scan_pushed_heads` (`security-scan`) is now the
sole pre-push job in that class (since `python-tests` was retired from pre-push
on 2026-11-26); it clamps one aggregate budget across every pushed ref and
every target batch within a ref, where before each batch got a fresh allowance
and N refs cost up to N times 150s. On-demand `run_pytest` (`git_hook_policy.py
pytest`) retains its aggregate deadline at 150s in a container across partitions.

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
   remotely.** Branch-scope and push-ref policy and fast static checks. Pytest
   execution and collection (amended 2026-11-26) and the whole-tree count
   ratchets, generated-tree check, and plugin scanner (a CI check, not
   required; amended 2026-11-27) belong in CI; developers run them on demand. The test is not "is this check
   valuable" but "does running it here cost seconds and save a CI round trip".

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
   check that catches a defect class you have measured it to catch, or retire it
   to CI when even that replacement saturates shared local hosts.** Not with a
   raised target. Historically, the whole-suite run became a whole-suite
   collection on 2026-10-08 and, on 2026-10-09, the testmon-selected run. State
   only the classes you probed, and probe them under production configuration.
   Collection was probed to block on a broken import and on a syntax error and
   to miss a missing fixture, two same-named test functions in one module, and a
   same-basename module collision. The testmon run kept the first two catches
   because it collected the whole tree before it selected, and added the
   assertions of every test whose dependencies changed; its probed miss was code
   a test reached only through a subprocess. On 2026-11-26, multi-worktree host
   telemetry showed that both testmon-selected pytest and whole-tree pytest
   collection still caused severe shared-host contention while duplicating
   unconditional required CI checks (`pytest.yml`), so both were retired from
   pre-push in favor of CI plus on-demand targeted local `uv run pytest`.

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
`tests/ci/test_lefthook_prepush_tiering.py` enforces the soundness condition:
issue #5317 later shipped sound deferral (`AI_AGENTS_PRE_PR_FAST_STAGE_RAN`)
strictly for unconditional (non-glob-gated) fast-stage jobs, while glob-gated
deferral remains forbidden.

### What ships with this record

- **Current (2026-11-26 amendment):** `python-tests` and `zero-collection-tests`
  are removed from `lefthook.yml` `pre-push`, leaving CI
  `.github/workflows/pytest.yml` as the authoritative gate for both pytest
  execution (`:318-380`) and `zero-collection-guard` (`:116-146`), aggregated by
  required context `Run Python Tests` (`test-result`, `:1048-1108`).
- **Current (2026-11-26 amendment):** `scripts/validation/checks_ci_parity.py`
  (`validate_unused_dependencies`) passes `--isolated` to
  `uv run --isolated --frozen --extra dev --extra eval python` (measured
  `2.21s-2.45s` warm across 3 runs) so `pre_pr.py` never mutates a worktree
  `.venv` with `--extra eval` (`openai`).
- **Current (2026-11-26 amendment):** `scripts/ci/lefthook_budget_model.py`
  removes `zero-collection-tests` from `CONTAINER_UNCLAMPED_JOBS` (13 clamped,
  14 unclamped = 27 pre-push jobs). Compute-lane declared worst case drops from
  18m to 14m; live declared pre-push budget stays `3330s` (55.5 min, within the
  `3450s` / 57.5 min baseline ceiling in `test_lefthook_declared_budget.py:81-96`)
  because `workflow-local-run` at 30m still dominates.
- **On-demand local wrapper (historical pre-push path, 2026-08-25 through
  2026-10-13):** `git_hook_policy.py pytest` (`_resolve_pytest_commands`,
  `_testmon_stand_in`, `run_pytest`) remains available on demand (not wired into
  `lefthook.yml`), keeping `COVERAGE_CORE=ctrace`, `PYTEST_DIST_MODE=worksteal`
  (SPEC-6211), non-empty command-list refusal, `AI_AGENTS_PYTEST_FULL_SUITE_LOCALLY=1`
  opt-in, and CI's `testmon-seed` job. `.github/workflows/pytest.yml` keeps the
  Markdown roots its own tests read (rule 4).

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

### Why Change Now (Historical 2026-08-25 / 2026-10-08 / 2026-10-09 Rationale)

In 2026-08-25, the suite grew to ~27,900 tests so local execution cost minutes
inside 4-CPU containers with reclamation deadlines. PR #6239 (2026-10-08)
retired issue #5050's import-graph selector (which had narrowed only 5 of 30
sampled PR runs for an inferred 40-60s savings), adopting owner guidance
(2026-10-07) that test selection is Context, not Core (buy `pytest-split` in CI
rather than build). On 2026-10-09, `pytest-testmon` 2.2.0 was adopted for
pre-push only (rejected for CI after a confirmed subprocess-execution miss),
then bounded on 2026-10-13 (issue #6200). On 2026-11-26, multi-worktree host
contention drove retirement of pre-push pytest altogether (see
`## Amendment 2026-11-26` below).

## Rationale

### Alternatives Considered

| Alternative | Pros | Cons | Why Not Chosen |
|---|---|---|---|
| Raise the container's patience | No repo change | Not a repo setting | Rejected: asks the environment to tolerate an 11-minute local gate |
| Narrow local selector to a per-path allowlist | Keeps local execution for Python changes | Unbounded on large Python diffs | Rejected; moot since PR #6239 retired the selector |
| Keep execution, drop mutation/safe-push/pr-autofix locally | Saves measured 212s | Leaves 258s bulk partition | Rejected as insufficient (CI already runs separate legs) |
| Whole-hook hard deadline deferring remaining gates | Bounds push directly | Untried; needs resume story | Not adopted whole-hook (#5813 measured 124-128s vs 300s target; `workflow-local-run` unmeasured). Narrow form adopted 2026-10-13 for pytest step only |
| Collect instead of execute on fallback / no-seed | 14-20.5s; blocks broken imports | No local assertions | Chosen 2026-10-08; superseded 2026-10-09 by testmon; retained 2026-10-13 for missing-seed fallback; **retired from pre-push 2026-11-26** |
| Run `pytest --testmon` in pre-push (buy, not build) | 4-36s warm replay; catches assertions locally | Cold build 575s; misses subprocess-only code; lockfile or `.venv` extra mismatch forces full run; whole-tree collection bursts across concurrent worktrees | Chosen 2026-10-09, bounded 180s on 2026-10-13 (#6200), **retired from pre-push 2026-11-26**; retained on demand via `git_hook_policy.py pytest` |
| **Fix `--isolated` alone (and clean `.venv`s), keep `python-tests` in pre-push, and re-measure** | Directly removes the `openai` `.venv` contamination that triggered 16/16 testmon fallbacks while preserving local testmon runs | Does not solve structural multi-worktree contention: suite grew ~3x (`27,900 -> 49,808 -> 81,060` items), so even clean whole-tree collection (`34.23s` warm / `87.48s` cold for `zero-collection-tests` alone) multiplied across 15-30 concurrent worktrees saturates a shared host; `uv.lock`/`pyproject.toml` changes (2/8 replayed commits) or cold seeds still trigger fleet-wide 180s overruns and `FULL_SUITE_LOCALLY=1` stampedes; duplicates unconditional required CI `pytest.yml` (Rule 4, Context-not-Core) | **Rejected 2026-11-26** by owner direction. Fix A (`--isolated`) still ships unconditionally because read-only `pre_pr.py` must never mutate a worktree `.venv` |
| **Drop `python-tests` and `zero-collection-tests` from pre-push; keep CI `pytest.yml` + on-demand local runs** | Eliminates local pytest/collection CPU bursts on shared hosts, honors Rule 4 and Context-not-Core, and keeps fast targeted `uv run pytest <paths>` | Untested assertions, broken test imports, or zero-collecting test files surface in CI (`pull_request`/`merge_group`/`push` to `main`) unless caught by targeted local runs | Originally rejected 2026-08-25; **Chosen 2026-11-26** by owner direction |

### Historical On-Demand Testmon Design (2026-10-09 Seed & 2026-10-13 Step Bound)

The following mechanisms were added for pre-push `python-tests` and remain
active **only** for on-demand `git_hook_policy.py pytest` and CI's
`testmon-seed` job (raw measurements in
`.project-toolkit/analysis/testmon-prepush-measurements.md`):

- **CI seed & provenance (2026-10-09)**: `testmon-seed` (`.github/workflows/pytest.yml:984-1040`,
  outside `test-result` `needs:`, 60m timeout exception in
  `tests/workflows/test_pytest_job_timeout.py`, ~30 runner-minute estimate) runs
  on `push` to `main` under a 3300s `AI_AGENTS_TESTMON_SEED_BUDGET_SECONDS` cap
  with `COVERAGE_CORE=ctrace` and uploads `testmon-db-<sha256(uv.lock, pyproject.toml)>`
  (7-day retention) only on exit 0. On-demand `git_hook_policy.py pytest`
  fetches via read-only `gh api` under a 30s cap, validating event `push`,
  branch `main`, repo `rjmurillo/ai-agents`, conclusion `success`, workflow
  path, `git merge-base --is-ancestor` against `origin/main`, 256 MB zip cap,
  single `.testmondata` member, SQLite magic bytes, and atomic staging via
  `O_CREAT|O_EXCL|O_NOFOLLOW`. Any fetch failure falls back to collection.
  Database portability across checkout paths is pinned by
  `tests/validation/test_testmon_database_portable.py`; testmon conservatively
  rejects mismatched Python/package versions.
- **Seed trust**: anything that pushes to `main` can produce a seed, including
  an administrator who bypasses review and any code that runs inside the
  `testmon-seed` job. A poisoned database can suppress local selection, so an
  on-demand run skips tests it should run; CI still runs them. It can also
  exercise SQLite's parser, which has no code-execution path from a data file.
  testmon reads it with SQLite queries and has no pickle, marshal, or exec path.
  The worst case is a false local pass that CI catches.
- **Step budget & cold deferral (2026-10-13, issue #6200)**: On-demand default
  runs enforce a 180s selection budget (`780s` with
  `AI_AGENTS_PYTEST_FULL_SUITE_LOCALLY=1`; 150s inside containers) and defer to
  whole-suite collection (measured 20.5s across 49,808 tests in 2026-10-13)
  when `.testmondata` is missing/interrupted and no seed is fetched. Overruns
  exit non-zero rather than silently deferring. (Historical note: `lefthook.yml`
  previously carried `timeout: 15m` on `python-tests` and `output: false`
  during the 2026-10-13 trial, later changed to `output:` (`- failure`) at
  `lefthook.yml:8-9`.)

## Amendment 2026-11-26: Remove Pre-Push Pytest and Isolate Deptry

Decided 2026-11-26 by owner direction following host-contention diagnosis on
the owner's shared 48-vCPU Linux host running concurrent worktree agent
sessions. Full telemetry tables, `.venv` audit counts, and measurement details
are recorded in `.project-toolkit/analysis/host-contention-2026-11-26.md`.

### Causal Diagnosis (Poisoned Incident vs. Structural Contention)

1. **Poisoned-venv incident amplifier (Fix A root cause)**: The figures in
   this item are incident-window numbers, measured while 44 of 121 `.venv`s
   were poisoned. They size the incident Fix A ends, not the steady state. In a 715s capture
   window (144 samples), host CPU averaged 90.4% busy (`load1` median 117.2,
   max 208.7), with `hook:python-tests` consuming 19.99 CPUs (41.6% of all 48
   vCPUs; peak 34 pytest controllers, 106 xdist workers), 108 180s budget
   overruns in 6h (36x the `> 3/month` trigger), 59 signal kills, 59 load-retry
   storms, 51 `headroom_timeout_run_anyway` events (fail-open headroom
   remediation is tracked separately in parallel work), and 35 sessions passing
   `AI_AGENTS_PYTEST_FULL_SUITE_LOCALLY=1`. Only 14 of 102 lefthook pytest
   invocations ran with `--testmon`. Auditing 121 worktree `.venv`s showed the
   trigger: `validate_unused_dependencies` in
   `scripts/validation/checks_ci_parity.py` ran
   `uv run --frozen --extra dev --extra eval python scripts/validation/check_unused_dependencies.py`
   without `--isolated`, mutating `.venv` in place to install `openai-3.51.0`
   (44/121 worktrees contaminated; 38 on 2026-11-26). Because CI's
   `testmon-seed` builds `.testmondata` without `--extra eval`, 16/16 worktrees
   with both `openai` and `.testmondata` hit a package mismatch
   (`venv-only=['openai 3.51']`) and discarded selection to run all 81,060 tests.
2. **Why Fix B (removing pre-push `python-tests` and `zero-collection-tests`)
   stands independently of Fix A**: Even after `--isolated` eliminates `.venv`
   poisoning, the suite has grown ~3x (`27,900 -> 49,808 -> 81,060` items).
   Running `check_zero_collection_tests.py` alone on an idle 48-vCPU host
   (`load1 = 1.94`, 2,697 test files) costs `34.23s` warm (`32.78s` user) and
   `87.48s` cold `.venv`; `zero-collection-tests` is whole-tree by contract
   (`rule-ci-scripts.md` forbids glob/diff-scoping it). Across 15-30 concurrent
   agent worktrees, healthy collection bursts plus lockfile-change full-suite
   invalidations (`uv.lock`/`pyproject.toml` changed in 2/8 replayed commits)
   can contend for host CPU while duplicating required CI
   `pytest.yml` (Rule 4; Context, not Core). Evidence basis: the per-run cost
   is measured; the concurrency multiplier is an estimate. No load window was
   measured after Fix A. Fix B rests on owner direction plus that estimate,
   and the Re-evaluation Triggers below say what would reopen it.
3. **Why Fix A (`--isolated`) remains mandatory after Fix B**: `pre_pr.py` is a
   read-only validator and must never mutate a worktree's `.venv` with optional
   `eval` packages; keeping `.venv` clean reduces installed attack surface and
   preserves valid testmon matching for on-demand `git_hook_policy.py pytest`.

### Binding Changes

1. Remove `python-tests` and `zero-collection-tests` from `lefthook.yml`
   `pre-push` and remove `"zero-collection-tests"` from
   `CONTAINER_UNCLAMPED_JOBS` in `scripts/ci/lefthook_budget_model.py`
   (13 clamped, 14 unclamped = 27 pre-push jobs; compute lane `18m -> 14m`;
   live declared budget stays `3330s` / 55.5 min within the `3450s` ceiling).
2. Add `--isolated` to `validate_unused_dependencies` in
   `scripts/validation/checks_ci_parity.py` (`uv run --isolated --frozen
   --extra dev --extra eval python`). Measured warm wall-clock cost across 3
   runs on 2026-11-26: `2.26s`, `2.45s`, `2.21s` (`Installed 123 packages in
   82-112ms`, exit 0, `openai` absent from `.venv` after full `pre_pr.py`).
   Offline with no cached `eval` wheels fails closed (non-zero -> `False`).
3. Preserve on-demand local commands (`uv run pytest`,
   `git_hook_policy.py pytest`, `AI_AGENTS_PYTEST_FULL_SUITE_LOCALLY=1`,
   `check_zero_collection_tests.py`) and CI's `testmon-seed` job intact. The
   change updates comments and one diagnostic in `scripts/validation/git_hook_policy.py`.
   Its execution behavior is unchanged. It does not touch `host_headroom.py` or
   `pre_pr_headroom.py` (avoiding conflicts with parallel PRs).

### Revert Path

Removing the two pre-push jobs is reversible with the file list below.
Adding `--isolated` is one-way by design. To restore local pre-push pytest/collection: re-add `python-tests` and
`zero-collection-tests` (and stage/compute-lane comments) in `lefthook.yml`,
re-add `"zero-collection-tests"` to `CONTAINER_UNCLAMPED_JOBS` in
`scripts/ci/lefthook_budget_model.py`, restore pre-push wiring assertions in
`tests/test_lefthook_integration.py`, `tests/ci/test_lefthook_container_bound.py`,
`tests/ci/test_lefthook_prepush_fast_fail.py`,
`tests/ci/test_zero_collection_guard_wiring.py`,
`tests/validation/test_pre_pr_covers_pre_push_jobs.py`,
`tests/validation/test_pre_pr_covers_workflow_validators.py`, and
`tests/validation/test_pre_push_headroom_wiring.py`, and revert docs/templates
(`CONTRIBUTING.md`, `tests/AGENTS.md`, `templates/rules/session-logs.md` +
rendered mirrors, `templates/skills/ai-agents-config-catalog.SKILL.md.tmpl` +
rendered mirror, `docs/runbooks/local-hook-failure.md`,
`.claude/skills/ai-agents-validation-and-qa/references/rule-ci-scripts.md`).
**Never revert `--isolated`** on `validate_unused_dependencies` or in
`CONTRIBUTING.md` / `.github/dependency-hygiene/policy.toml`: removing it
reintroduces `.venv` contamination with `openai`.

### Trade-offs and Enforcement-Plane Boundaries

Pre-push runs no pytest suite and no whole-tree pytest collection. Fast local
feedback remains active via pre-commit `python-check` (advisory ruff),
pre-push `python-type-check` (mypy) and `python-lint-advisory`, and
`pre-pr-validation` (including `validate_python_syntax` and
`Rule Lossless Fixtures`), plus contributor-run targeted `uv run pytest <paths>`.
Untested assertions, broken test imports, or zero-collecting test files now
surface in CI (`pull_request`, `merge_group`, `push` to `main`) at a cost of
one CI round trip; a branch pushed with no open PR gets no `pytest.yml` run
until a PR opens.

CI backstop scope and pre-existing ADR-101 limits (stated plainly):

- In `.github/workflows/pytest.yml` (`:28-37`, no path filter), both
  `zero-collection-guard` (`:116-146`) and the 8-leg `test` matrix (`:318-380`,
  full partitions via `run_pytest_partition.py`, 4 pinned files in `split-1`)
  have no `needs:` and no job-level `if:`. `test-result` (`Run Python Tests`,
  `:1048-1108`) is a required ruleset context (`ruleset_required_contexts.py:16`)
  that fails closed unless all 7 upstream jobs (`test`, `coverage`,
  `zero-collection-guard`, `line-endings-guard`, `context-output-guard`,
  `count-ratchet-guard`, `mutation-harness-guard`) succeed.
- `security` (`Python Security Checks`: `pip-audit` + ruff security rules,
  `pytest.yml:1109-1113`) and `test-windows-pwsh` remain path-filtered via
  `check-paths` (`scripts/ci/path_policy.yml`) and sit outside `test-result`
  and `REQUIRED_CONTEXTS`.
- Per ADR-101 (`:155,196-198`), local pre-push is P0 (actor-controlled, never a
  security boundary), so removing local pytest adds no new bypass. As a
  pre-existing P1/P2 limit, `pytest.yml` and `scripts/ci/` are head-editable on
  same-repo `pull_request` runs and `scripts/validation/ruleset_params_baseline.json`
  records `require_code_owner_review: false`, `required_approving_review_count: 0`,
  `strict_required_status_checks_policy: false`, and admin bypass (`actor_id: 5`);
  tamper detection therefore rests on P2 required contexts plus
  `enforcement-closure.yml`.

## Consequences

### Positive

- Local pushes no longer spawn pytest controllers or xdist worker pools
  (41.6% of host CPU during the 2026-11-26 incident; peak 34
  controllers, 106 workers) or ~34s warm `zero-collection-tests` scans.
- `validate_unused_dependencies` runs under `uv run --isolated` (`2.21s-2.45s`
  warm), ending `.venv` contamination with `openai` and preserving testmon
  matching for on-demand `git_hook_policy.py pytest`.
- Compute-lane declared worst case dropped `18m -> 14m` on 2026-11-26; the
  2026-11-27 amendment removed the lane (`plugin-scanner`, `count-ratchets`).
  Container per-job ceiling stays `240s` (`pre-pr-validation`).
- Historical baseline before 2026-11-26: collection-only cut a comparable
  4-CPU push from 679s to 142.39s (`python-tests` 498.52s to 15.10s).

### Negative

- Broken imports in untouched test modules, zero-collecting test files, and
  untested failing assertions surface in CI rather than at `git push` (one CI
  round trip), and branches without an open PR run no `pytest.yml`.
- On-demand `git_hook_policy.py pytest` and `AI_AGENTS_PYTEST_FULL_SUITE_LOCALLY`
  are no longer exercised on default pushes; unit tests pin their contracts
  (`test_pre_push_testmon.py`, `test_pre_push_headroom_wiring.py`).
- Live workstation declared pre-push budget remains `3330s` (55.5 min; ceiling
  `3450s` / 57.5 min) against the 300s target because `workflow-local-run`
  (30m) and the two CLI e2e smokes (20m) dominate the outer parallel group.
- Issue #5317 later shipped sound deferral (`AI_AGENTS_PRE_PR_FAST_STAGE_RAN`)
  for 5 unconditional fast-stage jobs; remaining glob-gated duplication stays.
- **Container-reclaim protection remains closed for pre-push:** no single
  subprocess exceeds 150s in a container, and `scan_pushed_heads` (plus
  on-demand `run_pytest`) holds aggregate deadlines.
- **Plugin scanner score is not blocking (2026-11-27):** a CI check, not a
  required context; see `## Amendment 2026-11-27` Consequences.

### Neutral

- On-demand `git_hook_policy.py pytest` retains its internal budgets (180s
  default, 780s full-suite opt-in, 150s container clamp, 900s headroom cap).
- Lefthook remains the local scheduler (ADR-086); CI `pytest.yml` (`Run Python
  Tests`) remains the authoritative test gate.

## Re-evaluation Triggers

Revisit this record when any trigger fires. Owner: repository maintainer;
mechanism: issue #5315 (or dedicated follow-up issue for `testmon-seed`).

- A real push measures pre-push above 300s after `python-tests` and
  `zero-collection-tests` are removed.
- More than 3 `pull_request` runs in one week fail `zero-collection-guard`
  or fail pytest collection in a `test` matrix leg. Source: the Actions run
  history for `pytest.yml`, read at the 2026-12-26 review.
- Any proposal seeks to re-introduce pytest execution or collection into
  `pre-commit` or `pre-push`, or add a new pre-push job.
- `Run Python Tests` or `zero-collection-guard` stops being an unconditional
  required context or loses merge-queue execution (invalidating Rule 4).
- A defect reaches `main` that a local pytest gate would have caught and CI
  missed.
- **Time-boxed `testmon-seed` review (by 2026-12-26, 30 days post-merge):**
  because local on-demand runs have no telemetry collector, open/review a
  dedicated tracking issue by 2026-12-26 to retire CI's ~30-runner-minute
  `testmon-seed` job and `git_hook_policy.py pytest` unless active on-demand
  usage is confirmed.

## Impact on Dependent Components

| Component | Dependency Type | Required Update | Risk |
|---|---|---|---|
| `lefthook.yml` | Direct | `python-tests` and `zero-collection-tests` removed from `pre-push` (2026-11-26) | Low |
| `scripts/validation/checks_ci_parity.py` | Direct | `validate_unused_dependencies` passes `--isolated` to `uv run` | Low |
| `scripts/ci/lefthook_budget_model.py` | Direct | `zero-collection-tests` removed from `CONTAINER_UNCLAMPED_JOBS` (13 clamped, 14 unclamped = 27) | Low |
| `scripts/validation/git_hook_policy.py` | Direct | Comments and diagnostic only; execution unchanged for on-demand `pytest` and CI `testmon-seed` | Low |
| `.github/workflows/pytest.yml` | Direct | Unconditional `zero-collection-guard` (`:116-146`) and 8-leg `test` (`:318-380`) feed required `Run Python Tests` (`:1048-1108`) | Medium |
| Pre-push & isolation test suite (`test_lefthook_integration.py`, `test_lefthook_prepush_fast_fail.py`, `test_zero_collection_guard_wiring.py`, `test_pre_pr_covers_pre_push_jobs.py`, `test_pre_pr_covers_workflow_validators.py`, `test_pre_push_headroom_wiring.py`, `test_validate_unused_dependencies_isolation.py`) | Direct | Pin absence of `python-tests`/`zero-collection-tests` from pre-push, preserve CI wiring proofs, and pin `--isolated` | Low |
| `scripts/ci/path_policy.{py,yml}` | Direct | Gates `security` and `test-windows-pwsh` via `check-paths`; head-editable; owned by `/scripts/ci/` (`.github/CODEOWNERS:78`) | High |
| `pytest-split` durations cache & `scripts/ci/run_pytest_partition.py` | Direct | Main-scope durations cache (`test_pytest_split_durations_save.py`); pytest-split assigns every collected test to one group so hostile/empty maps fail red or unbalance, never skip (`test_pytest_split_pool.py`, `test_pytest_split_hostile_durations.py`); blocking 480s leg gate in `coverage` catches slow legs; owned by `/scripts/ci/` | Medium |
| `tests/test_safe_push_pr_branch.py`, `tests/validation/test_pytest_parallelism_policy.py` | Direct | On-demand budget and worker-flag contracts for `git_hook_policy.py pytest` | Low |
| ADR-090 | Indirect | 30-minute lease TTL calibrated for former 20-30m pre-push; pre-push no longer runs pytest | Low |
| Contributor & agent docs (`CONTRIBUTING.md`, `.github/dependency-hygiene/policy.toml`, `tests/AGENTS.md`, `templates/rules/session-logs.md`, `templates/skills/ai-agents-config-catalog.SKILL.md.tmpl`, `docs/runbooks/local-hook-failure.md`, `.claude/skills/ai-agents-validation-and-qa/references/rule-ci-scripts.md`) | Indirect | Updated to reflect CI `Run Python Tests`, on-demand local pytest, and `--isolated` deptry | Low |
| `lefthook.yml` (2026-11-27) | Direct | `plugin-scanner` and `count-ratchets` removed from `pre-push`; 25 leaf jobs remain (12 clamped, 13 unclamped); declared total unchanged at 3330s | Low |
| `scripts/validation/pre_pr_sequence.py`, `scripts/validation/evidence.py` (2026-11-27) | Direct | `_Gate.ci_owned_by` and `REASON_CI_OWNED` (`policy.ci_owned`); Count Ratchets and Generated Artifact Staleness skip inside the hook only | Low |
| CI ownership tests (2026-11-27: `tests/ci/test_lefthook_ratchet_wiring.py`, `tests/validation/test_pre_pr_ci_owned_gates.py`, `tests/validation/test_pre_pr_sequence_registry.py`, `tests/mutation/test_mutate_lefthook_ratchet_wiring.py`) | Direct | Pin that each `ci_owned_by` job is required and unconditional, runs the command the gate runs, and that the hook no longer carries the two jobs | Low |
| `.github/workflows/plugin-scanner.yml`, `scripts/validation/check_plugin_scanner_score.py` (2026-11-27) | Indirect | The workflow is the sole remaining scanner gate and is not a required context; the script becomes an on-demand twin, recorded in `_NO_CALLER` of `tests/ci/test_validation_scripts_are_reachable.py` | Medium |

## Amendment 2026-11-27: Retire CI-Owned Heavy Passes From Pre-Push

Decided 2026-11-27 by owner direction: "CI runs the tests. We do not force a
heavy pass locally. CI scales well beyond the host." Claims and evidence:
`.project-toolkit/critique/ADR-104-ci-owned-heavy-passes-claims-ledger.md`.

### Context

Why the passes were local: PR #5418 (2026-08-29) consolidated the count
ratchets into pre-push because a 0.21s ratchet failure surfaced 674s later in
CI (`scripts/validation/checks_ratchet.py` docstring). PR #6913 (2026-10-24)
added the scanner job when the score gate went to 80. Both bought an earlier
signal; neither was the only CI check. Measured standalone on the shared
48-vCPU host, 2026-11-27, load1 5 to 9:

| Pass | Where it ran | Wall | CPU (user + sys) |
|---|---|---|---|
| `count-ratchets` | pre-push job | 30.3s | 110.0s |
| `plugin-scanner` | pre-push job | 56.5s | 56.5s |
| `build_all.py --check` | `pre-pr-validation` gate | 13.2s | 13.2s |

The staleness run exited 2 on the uncommitted ADR index after running every
generator. Heavy-stage slots (`scripts/validation/host_headroom.py`) delay a
pass, not remove it: the first baseline push waited 420s for a slot.

### Decision

Criterion: a pass leaves the hook when a CI job runs the same command on every
PR. It stays when no CI job runs it before merge. Cost ranks the candidates;
it is not the test, so the 13.2s staleness gate leaves on the ruling.

1. Remove `plugin-scanner` and `count-ratchets` from `lefthook.yml`
   `pre-push`, and `plugin-scanner` from `CONTAINER_UNCLAMPED_JOBS`.
2. Add `_Gate.ci_owned_by` and `REASON_CI_OWNED = "policy.ci_owned"`. With
   `AI_AGENTS_PRE_PR_FAST_STAGE_RAN=1`, which the hook sets and nothing
   enforces, Count Ratchets and Generated Artifact Staleness record a SKIP
   naming the CI job, printed under `--compact`. The flag is a visibility aid,
   not a trust boundary. A direct `pre_pr.py` run executes both gates.
3. Keep the commands on demand (Implementation Notes).

### CI Jobs That Run The Removed Passes

| Pass | CI job | Triggers | Required context |
|---|---|---|---|
| `count-ratchets` (10 scripts in `checks_ratchet.RATCHETS`) | `pytest.yml` `count-ratchet-guard`, `test` primary leg (`ruff_ratchet.py`); `pr-validation.yml` `validate-pr` | PR and merge group on `main`; `pytest.yml` also push to `main` | Yes: "Check whole-tree count ratchets (blocking)", "Run Python Tests" (rollup needs `test`), "Validate PR" |
| Generated Artifact Staleness | `validate-generated-agents.yml` `build-all-staleness` | push, PR, merge group on `main` | Yes, via "Validate Generated Files" |
| `plugin-scanner` | `plugin-scanner.yml` `scan` | push and PR on `main`; no merge group | No: a check, not a gate |

No job above has a job-level `if:`. Among steps that run a ratchet script, the
one step-level condition is `matrix.primary` on `ruff_ratchet.py`
(`ALLOWED_STEP_IF`, `tests/ci/ratchet_test_helpers.py`). CI runs the same
scripts the local gate ran: each against the merge base, plus
`merge_tree_ratchet_check.py` against the base tip. A branch with no PR gets
no check.

### Why This Is Not The Rejected Deferral

The rejected deferral trusted that a sibling local job ran, and a glob skip
read as a pass. `ci_owned_by` defers to merge-time CI and shows a SKIP. Rule 6
holds because `tests/validation/test_pre_pr_ci_owned_gates.py` tests what the
deferral relies on: each named job exists with no job-level `if:`, feeds a
required context, and sits in a workflow with no `paths` filter; the staleness
job runs `build_all.py --check`; the Count Ratchets owners equal the required
jobs that run every `RATCHETS` script. Script identity is pinned, not base-ref
arguments. `TestOwnerProblemsNegativeControls` proves each failure is reported.
`plugin-scanner` has no `ci_owned_by` row, so these tests do not cover it.

### Kept, With The CI Gap Named

These match Known non-conformances, less `python-type-check` (2.73s,
changed files only, so not heavy), plus `pre-pr-validation`:

| Job | CI gap |
|---|---|
| `workflow-local-run` | Runs each changed workflow under `act`, including schedule-only and dispatch-only ones such as `agent-metrics.yml`. No PR-triggered workflow executes those; `pr-validation.yml` validates schema only. |
| `security-scan` | No workflow under `.github/workflows/` runs Semgrep; one file cites a rule id in a comment. |
| `hook-anchoring-e2e`, `plugin-load-e2e` | No workflow runs `test_cli_hook_e2e.py`, and `test_plugin_load_smoke.py` runs in CI only as `-m "smoke and codex"`: #7654 (`f8398e1b2d`, 2026-11-27) deleted the dispatch-only `smoke` job that ran both against the real Claude and Copilot CLIs. `plugin-cli-smoke.yml` legs cover Claude hook discovery, Codex, and Pi. |
| `pre-pr-validation` | No workflow runs `pre_pr.py`; its other gates are not mapped to CI one by one. |

### Measured Effect

One dry-run push per side (`git push --dry-run` runs the hook, sends nothing):
base `d31aa71e60` (2026-11-27), 1 file, load1 18.3, 245.9s wall, 509.4s CPU; this branch,
36 files, load1 4.8, 167.6s wall, 308.6s CPU. Load, range, and excluded jobs
differ (`security-scan` both sides: `semgrep-core` exits -11 under the host's
8 MiB stack, a pre-existing defect; `push-ref-policy` after, for the missing
review marker). The direction matches the standalone table; the magnitude at
equal load is unmeasured.

### Consequences

- Positive: a push stops paying about 180s of CPU. Wall saved is bounded by
  the slowest sibling in the parallel group, not the 100s standalone sum.
- Negative: the scanner scored 80 against a minimum of 80 on 2026-11-27, so
  the next drop merges unless someone reads the check. Its findings include
  security items (for example "No privileged untrusted checkout patterns");
  no other required check is verified to cover them. Requiring the context
  is a ruleset change for the owner.
- Negative: ratchet and staleness failures surface one CI round trip later.
  This change hit it: a 534-line test file passed the hook and only an
  on-demand `count-ratchets` run found it.
- Neutral: the declared total stays 3330s; the two removed jobs sat in a
  lane shorter than the 30m `workflow-local-run` beside them.

### Alternatives Considered

| Alternative | Why rejected |
|---|---|
| Keep the passes behind heavy-stage slots | Slots delay work; the baseline push waited 420s |
| Remove the five kept jobs too | Each is the only pre-merge run of its check |
| Glob-gate or cache `count-ratchets` | Whole-tree counts; a diff filter cannot decide them (`rule-ci-scripts.md`, "Path filters gate the diff, never the tree"), and a cache still runs locally |
| Require Plugin Scanner first | Ruleset change owned by the repository owner; recorded as a trigger |

### Re-evaluation Triggers (2026-11-27)

- By 2026-12-27 the repository owner decides whether to require "Plugin
  Scanner (score >= 80)" or restore the local job; sooner if a score below 80
  reaches `main`.
- An owner job gains a job-level `if:` or `paths` filter, or leaves
  `REQUIRED_CONTEXTS`: `test_pre_pr_ci_owned_gates.py` fails.
- This record is 1000 lines at most; the next amendment moves the 2026-11-26
  and 2026-11-27 amendments to a successor record first.

### Revert Path (2026-11-27)

Supersede this amendment with a new dated one; do not delete it. Revert
the squash-merge commit of the pull request that added this amendment (the
branch commits do not survive the squash), or by hand:
restore the two job blocks (not the whole file) from
`git show d31aa71e60:lefthook.yml` (2026-11-27); re-add `plugin-scanner` to
`CONTAINER_UNCLAMPED_JOBS` and restore its 12/13 comment; set Count Ratchets
to `already_run_by="count-ratchets"` and drop `ci_owned_by` from both gates;
drop the `_NO_CALLER` entry in `tests/ci/test_validation_scripts_are_reachable.py`;
restore the tests in the Impact table plus `test_pre_pr_compact.py`,
`test_pre_pr_evidence_states.py`, `test_lefthook_prepush_tiering.py`,
`test_lefthook_gate_config.py`, and `test_check_plugin_scanner_run.py`; restore
the comment and doc edits listed by `git show --stat` on that squash-merge
commit; revert rule 2.

## Implementation Notes

```bash
# Recommended local workflow before pushing: targeted tests for changed files
uv run --frozen pytest tests/<area>/test_<module>.py -q

# Clean already-contaminated worktree .venv (removes stray eval/openai packages)
uv sync --frozen --extra dev

# On-demand testmon-selected local run (not wired into pre-push)
uv run --frozen python scripts/validation/git_hook_policy.py pytest

# On-demand whole-suite local run across all 4 local partitions
AI_AGENTS_PYTEST_FULL_SUITE_LOCALLY=1 \
  uv run --frozen python scripts/validation/git_hook_policy.py pytest

# On-demand whole-tree zero-collection check (also runs unconditionally in CI)
uv run --frozen python scripts/validation/check_zero_collection_tests.py

# Isolated deptry check (as run by pre_pr.py; does not mutate .venv)
uv run --isolated --frozen --extra dev --extra eval \
  python scripts/validation/check_unused_dependencies.py
```

Every defect-class claim in rule 5 was probed against a throwaway tree, and the
two that failed are recorded as failing rather than dropped quietly.

## Related Decisions

- ADR-086: Lefthook owns local hook orchestration; this record bounds pre-push.
- ADR-071: placed CLI e2e smokes in pre-push (listed under Known non-conformances).
- ADR-054: 900s per-job kill ceiling for `security-scan` (compatible with 300s target).
- ADR-049: pre-PR validation gates.
- ADR-101: enforcement planes (complementary: trust vs. placement).
- ADR-073: frontmatter status enum and `implemented` definition.
- ADR-004: superseded by ADR-086.

## References

- `.project-toolkit/analysis/host-contention-2026-11-26.md`: 2026-11-26 host-contention telemetry, `.venv` poisoning audit, and `--isolated` measurements.
- `.project-toolkit/critique/ADR-104-prepush-pytest-removal-debate-log.md`: six-seat debate log for the 2026-11-26 amendment (prior debate log: `.project-toolkit/critique/ADR-104-debate-log.md`).
- `.project-toolkit/analysis/testmon-prepush-measurements.md`: 2026-10-09/10-13 testmon measurements.
- Issues #5315, #5317, #5318 (closed 2026-10-02), #4710, #5066, #5050 (retired by PR #6239), #6200, #7636.
- `scripts/validation/testmon_seed.py`, `.github/workflows/pytest.yml` (`testmon-seed`, `zero-collection-guard`, `test`, `test-result`), `scripts/validation/checks_ci_parity.py` (`validate_unused_dependencies`).
- `.serena/memories/ci/ci-pre-push-wall-clock-is-python-tests.md` and `.claude/skills/ai-agents-validation-and-qa/references/rule-ci-scripts.md` (MUST-14, MUST-16, MUST-19, MUST-21).
