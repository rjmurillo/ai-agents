---
type: requirement
id: REQ-027
title: Measured local-gate latency distribution for release gate 3
status: draft
priority: P1
category: functional
source: EPIC-5456
related:
  - REQ-022
  - REQ-024
  - ADR-104
created: 2026-09-16
updated: 2026-09-16
author: spec
tags:
  - metrics
  - hooks
  - lefthook
  - measurement
---

# REQ-027: Measured local-gate latency distribution for release gate 3

## Step 0 First Principles

### Q1 Demand Reality

Three named requesters, each with a written ask in this repository:

1. Epic #5456 Baseline section, authored by the repository owner `rjmurillo`:
   "local pre-commit and pre-push p50/p95 latency by gate" is listed as a
   required baseline dimension. It was captured as an exclusion, not a
   measurement.
2. Issue #5318, same author, items 1 and 2: "measure each of the five when its
   glob fires, on a real push, per `ci-scripts.md` MUST-16" and "measure a
   representative pre-commit run and either keep the number or replace it."
3. ADR-104 re-evaluation trigger, same author: "A real push measures the
   pre-push hook above 300s." The trigger cannot fire because nothing measures
   it on a schedule.

### Q2 Status Quo

Today a contributor who wants the number does this, by hand:

1. Make a commit and run `git push`.
2. Watch lefthook print its own summary to the terminal.
3. Copy the per-job lines out of the scrollback into a Serena memory or an ADR.

That is exactly how `.serena/memories/ci/ci-pre-push-wall-clock-is-python-tests.md`
was produced on 2026-08-19 and how ADR-104's two figures (142.39s and 679s)
were produced. The record decays the moment the config changes: that memory now
carries the sentence "this has not been re-measured, so no replacement number is
given here" after PR #5418 changed `pre-pr-validation`.

### Q3 Desperate Specificity

The single most blocked artifact is release gate 3 of epic #5456, recorded in
`.project-toolkit/metrics/control-plane-dispositions-v0.7.0.md` as
"Unchecked | No p95 measurement was re-run this session;
`gate_budget.seconds_by_hook.pre-push` (3,450.0s) is the baseline figure, not
re-measured here." It is blocked on one missing thing: a sampler. Every other
unchecked gate on that epic is blocked by an open issue or by paid
authentication this environment does not have. Gate 3 is blocked by absent
tooling alone.

### Q4 Narrowest Wedge

One measurement-only script, `scripts/metrics/gate_latency.py`, that runs a real
lefthook hook N times, parses lefthook's own per-job summary, and emits per-job
and whole-hook p50/p95 as JSON and markdown. Roughly 6 hours of implementation
including tests and a committed measurement run.

### Q5 Observation

Direct signals, each a file in this tree:

- `.project-toolkit/metrics/control-plane-baseline-v0.7.0.json` records
  `gate_budget.seconds_by_hook` computed entirely from declared `timeout:`
  fields, and an exclusions entry stating "no sampler exists."
- The declared pre-push figure is 3,450s. The one measured push on record is
  679s. The declared model overstates the measured run by 5x, so the number the
  release gate currently reads is not the number a contributor waits through.
- ADR-104 sets a 300s pre-push target and states "Neither target is enforced at
  runtime" and "The 60s pre-commit figure in particular has no measurement
  behind it."

### Q6 Future-fit

At 10x the job count the sampler is worth more, not less: it is the only thing
that would tell the owner which of 700 jobs owns the wall clock. It carries no
ratchet, no baseline file another gate reads, and no allowlist, so it cannot
become a synchronization obligation. If lefthook's summary format changes, the
parser fails loudly in its own tests and the script is deleted or repaired in
one place.

## Step 0.5 Prior Art and Constraints

Searched: `.serena/memories/` (ci, knowledge), `.project-toolkit/plans/`, `scripts/`,
`tests/`. Four tool calls, three of which returned prior art.

**Found, and it changes the scope.**
`.serena/memories/ci/ci-pre-push-wall-clock-is-python-tests.md` already holds a
complete per-job pre-push breakdown from 2026-08-19 on a 4-CPU container: 679s
total for a one-markdown-file push, `python-tests` 498.52s of it. The gate does
not halt on this, for three reasons the memory itself states or implies:

1. n=1. A single sample yields no p50 and no p95.
2. Self-declared stale: "The `pre-pr-validation 110.12s` and `Total about 679s`
   figures above are now stale for the lefthook pre-push path specifically,
   since PR #5418 ... this has not been re-measured."
3. Pre-commit, 45 jobs, was never sampled representatively (#5318 item 2).

**Binding constraints carried forward from prior art.**

- `ci-scripts.md` MUST-16: a standalone run does not predict in-hook cost
  (6.83s standalone against 92.87s in a real push, same job, same day). Per-job
  figures MUST come from inside a whole-hook run. This forbids the obvious
  design of timing `lefthook run <hook> --job <name>` one job at a time.
- `ci-scripts.md` MUST-17: lefthook's summary reports a group's duration as the
  sum of its members regardless of scheduling, so scheduling MUST be read from
  `lefthook.yml`, never inferred from the summary's arithmetic.
- Epic #5456 gate 4 and Abort-if clause 3: no new registry, evaluator, ratchet,
  or governance layer. The sibling `control_plane_baseline.py` precedent (DR1)
  is the pattern to copy: measurement only, exit code independent of every
  metric value, wired into no gate.
- The measured contention ratios in the same memory (fast stage 2.67x, expensive
  jobs 1.05x) are that machine on that date and are not carried forward as
  planning numbers.

## Problem statement

Release gate 3 of epic #5456 reads a declared worst-case budget (3,450s
pre-push) as if it were a measured latency, because this repository has no
sampler; the one real measurement on record is a single hand-copied sample that
its own author has marked stale.

## User stories

1. As the release owner closing v0.7.0, I run one command and get a per-job and
   whole-hook latency distribution for `pre-commit` and `pre-push`, so gate 3
   is decided on a measurement instead of a declared timeout sum.
2. As a contributor sizing a `timeout:` in `lefthook.yml`, I read a committed
   in-hook p50/p95 for that job, so MUST-16 is satisfied without me staging a
   throwaway commit and reading scrollback.
3. As the author of ADR-104, I can tell whether the 300s pre-push target is met,
   exceeded, or meaningless for a given change class.

## Ontology

- `HookRun` (O2 aggregate root): one execution of one lefthook hook for one
  change class. Identity: (hook, change_class, repetition_index). Owns its
  `JobSample` set and its own end-to-end wall clock.
- `JobSample`: one job's duration as lefthook reported it inside a `HookRun`.
  Identity: (hook_run, job_name). Carries `status` (pass, fail, skip).
- `ChangeClass`: a named file list passed to lefthook via `--file`, chosen so a
  known set of glob-gated jobs fires. Identity: name.
- `LatencySummary`: the aggregate over repetitions. Identity: (hook,
  change_class, job_name or the reserved name `__hook__`). Carries n, p50, p95,
  min, max.
- `HostProfile`: the machine the samples describe. Identity: captured_at.
- Bounded-context boundary: this context owns measured latency only. Declared
  budget stays owned by `scripts/ci/lefthook_budget_model.py` and is imported,
  never recomputed.
- Decision rule: a `LatencySummary` with n < 20 reports p95 as an upper-order
  statistic and says so in the artifact.

## Data model

| Entity | Identity | Invariants | Lifecycle |
|---|---|---|---|
| `HookRun` | hook + change_class + repetition_index | wall_clock_seconds > 0; job samples unique by name | created per subprocess call, immutable after |
| `JobSample` | hook_run + job_name | duration_seconds >= 0; status in {pass, fail, skip} | parsed from summary, immutable |
| `ChangeClass` | name | file list non-empty; every path exists in the repo | declared in the script, selected by CLI |
| `LatencySummary` | hook + change_class + job_name | n >= 1; min <= p50 <= p95 <= max | computed after all repetitions |
| `HostProfile` | captured_at | cpu_count >= 1 | captured once per invocation |

## Integrations

- `lefthook` 2.1.12 subprocess, invoked as
  `lefthook run <hook> --no-tty --colors off --force --no-stage-fixed [--file P]...`.
  Failure modes: non-zero exit when a gate fails (expected and recorded, never
  fatal to the sampler); missing binary; a summary line the parser does not
  match. Idempotency: each repetition is independent; the sampler never retries
  a repetition, because a retry would silently resample a different machine
  state.
- `scripts/ci/lefthook_budget_model.load_config` for the declared figure and for
  the authoritative job list. Imported, not reimplemented (DR4).

## Failure modes

| Scenario | Mode | Early warning | Prevention |
|---|---|---|---|
| lefthook summary format changes | parser yields zero `JobSample`s | run reports 0 jobs parsed | a test pins the exact summary grammar against a captured fixture; the script records `jobs_parsed` in its output so a zero is visible in the artifact |
| a gate fails mid-run | hook exits non-zero, later jobs never run | fewer samples than jobs in config | record per-repetition `exit_code` and `jobs_parsed`; never abort the remaining repetitions; never treat a gate failure as a sampler failure |
| a job mutates the working tree | later repetitions measure a different tree | tree dirty after a repetition | pass `--no-stage-fixed`; capture `git status --porcelain` digest before and after each repetition and record whether it changed |
| n too small for p95 | a tail claim nobody can support | n < 20 | emit `n` beside every percentile and set a `percentile_note` field naming p95 as an upper-order statistic at low n |
| measurement taken on one machine read as universal | a planning number carried to another box | none | record `HostProfile` in the artifact and state the one-machine scope in the markdown, per MUST-16's own wording |
| the job-set diff is mistaken for a latency non-regression proof | gate 3 recorded as met while a surviving job silently slowed | none, a count diff cannot see it | AC-15: a paired measurement, or gate 3 recorded as a first reference with the paired comparison named as outstanding |
| a low-n p95 is quoted outside the artifact | an unsupportable tail figure becomes a planning number, as ADR-104's single samples did | the figure appearing in an issue comment without its n | AC-05: below n=20 the markdown and every quoted figure lead with `worst observed of N runs` |

## Security

Input validation: the change-class file list is a fixed table inside the script,
never user-supplied free text, so no path escapes into a shell. The script uses
`subprocess.run` with an argument list and `shell=False`. Output writing reuses
the sibling's `O_NOFOLLOW` symlink-refusing pattern (CWE-59) with mode 0600. No
secrets, no network, no PII: the artifact contains job names, durations, and a
CPU count. The one residual: running the sampler executes the repository's real
gates, which is the same code path a contributor's own push executes, so it
introduces no execution surface that a push does not already have.

## Observability

The metric that proves this works: `jobs_parsed` per repetition equals the
number of jobs the hook actually ran, and the sum of `JobSample` durations is
within the `HookRun` wall clock. Both are emitted in the artifact and both are
asserted in tests.

## Acceptance criteria

1. WHEN `gate_latency.py --hook pre-commit --repetitions N` is invoked, THE
   SYSTEM SHALL execute the real `pre-commit` hook N times as a single
   whole-hook lefthook invocation per repetition, and SHALL NOT invoke lefthook
   with `--job` to time a job in isolation.
2. WHEN a repetition completes, THE SYSTEM SHALL record one `JobSample` per job
   line in lefthook's summary, with the job name, its reported duration in
   seconds, and its pass, fail, or skip status.
3. WHEN a repetition completes, THE SYSTEM SHALL record the sampler's own
   end-to-end wall clock for that repetition separately from lefthook's
   self-reported total.
4. WHEN all repetitions complete, THE SYSTEM SHALL emit, per job and for the
   hook as a whole, n, p50, p95, min, and max, using nearest-rank percentiles.
5. WHERE n is below 20, THE SYSTEM SHALL emit a `percentile_note` field stating
   that p95 is an upper-order statistic rather than a tail estimate, AND the
   markdown artifact SHALL lead each scope with `worst observed of N runs`
   rather than with a figure labelled p95. A caveat beside a percentile label
   did not stop ADR-104's single-sample figures from being carried forward as
   planning numbers; the label itself is what gets quoted, so below the
   threshold the artifact does not offer one.
6. WHEN a hook run exits non-zero because a gate failed, THE SYSTEM SHALL record
   that exit code, keep the samples it parsed, continue the remaining
   repetitions, and still exit 0.
7. THE SYSTEM SHALL exit 0 for every metric value it can produce, reserving exit
   1 for a dirty tree without `--allow-dirty` and exit 2 for a missing repo, a
   missing or invalid `lefthook.yml`, or a missing lefthook binary.
8. WHEN `--change-class` names a declared class, THE SYSTEM SHALL pass that
   class's file list to lefthook via repeated `--file` arguments so glob-gated
   jobs fire, and SHALL record the class name and its file list in the output.
   The declared classes SHALL between them fire each of the five pre-push jobs
   #5318 item 1 names (`hook-anchoring-e2e`, `plugin-load-e2e`,
   `workflow-local-run`, `python-type-check`, `security-scan`), and any of the
   five that cannot be measured in the capture environment SHALL be descoped by
   name with its reason recorded in the artifact's `exclusions`, never left
   silently unmeasured.
9. THE SYSTEM SHALL import the declared budget and hook job structure from
   `scripts/ci/lefthook_budget_model.py` and SHALL NOT reimplement the
   piped-sum, parallel-max walk.
10. THE SYSTEM SHALL emit both a JSON artifact and a markdown artifact, writing
    each through a symlink-refusing open with mode 0600.
11. THE SYSTEM SHALL record a `HostProfile` containing at least CPU count and
    capture timestamp, and the markdown SHALL state that the figures describe
    one machine on one date.
12. WHEN the working tree digest differs before and after a repetition, THE
    SYSTEM SHALL record `tree_mutated: true` for that repetition.
13. THE SYSTEM SHALL NOT be referenced by `lefthook.yml`, by
    `scripts/validation/pre_pr*.py`, or by any file under `.github/workflows/`.
14. Release gate 3 of epic #5456 SHALL be updated in
    `.project-toolkit/metrics/control-plane-dispositions-v0.7.0.md` with the measured
    figures and with the structural evidence that the hook job set at HEAD is
    the baseline's set minus `retrospective-policy`, with no job added and no
    surviving job's `timeout:` raised.
15. THE SYSTEM SHALL NOT record gate 3 as met on the job-set diff alone. The
    diff bounds the declared ceiling, not measured latency: 50 commits and
    1,999 changed files separate `53ffe92c2` from `origin/main`, test files
    grew from 1,031 to 1,174, and `python-tests` owned 498.52s of the 679s
    sample on record, so a surviving job can have slowed with no job added.
    Either a paired measurement at `53ffe92c2` on the same machine SHALL be
    captured, or gate 3 SHALL be recorded as a first measured reference with
    the paired comparison named as the outstanding step and the reason it was
    not taken.
16. THE SYSTEM's own arrival SHALL be argued in the ledger's gate 4 row, on the
    same named-exception footing the sibling `control_plane_baseline.py`
    required, with the reference-absence check over `lefthook.yml`,
    `scripts/validation/pre_pr*.py`, and `.github/workflows/` recorded as its
    evidence.

## Out of scope

- Enforcing any latency budget. No ratchet, no threshold, no failing exit.
- Changing any `timeout:` in `lefthook.yml`, or acting on what the measurement
  shows. Acting is a separate decision for the owner under #5318 item 1.
- Reconciling ADR-054's 900s `security-scan` budget with ADR-104's 300s target
  (#5318 item 5).
- The local-selector-versus-CI-filter divergence (#5318 item 3) and the
  hook-level deadline (#5318 item 4).
- CI-side latency. This measures local gates only.

## Deferred

- Repeating the measurement on a workstation rather than a 4-CPU container.
  Owner: repository owner, who has the hardware this container is not.
- Wiring a scheduled re-measurement. Deferred deliberately: a schedule is a
  synchronization obligation, which the epic's Abort-if clause 3 treats as the
  failure being subtracted.

## Open questions

- None blocking. One recorded: whether `python-tests` should be scoped to the
  push range locally, as CI already scopes it. That is #5318's decision to make
  once the number exists, not this requirement's.

## CVA summary

- **Common**: every hook run produces a name-to-duration mapping, a wall clock,
  an exit code, and a tree digest, regardless of which hook or change class.
- **Varies**: the hook name, the change-class file list, the repetition count,
  and which jobs fire.
- **Relationships**: `LatencySummary` is a pure fold over `JobSample`s grouped by
  (hook, change_class, job_name); it holds no state the samples do not. The
  declared budget is a foreign aggregate, imported for comparison and never
  merged into the measured one.

## Buy-vs-build decision

- **Classification**: context, not core. Measuring one's own git hooks is
  plumbing.
- **Alternatives evaluated**: (1) lefthook's own summary read by hand, which is
  the status quo and produced the stale record this requirement replaces;
  (2) `hyperfine`, which benchmarks a whole command and cannot attribute time to
  a job inside a hook, and which would add a non-Python binary dependency
  against ADR-042; (3) extending `control_plane_baseline.py`, rejected because
  that script is 806 lines against a 500-line taste ceiling and is deliberately
  a whole-repo static snapshot with no subprocess execution; (4) pytest-benchmark,
  which measures Python callables, not shelled-out hook graphs.
- **Recommendation**: build, and keep it small.
- **Rationale**: the thing being measured is this repository's own lefthook
  config in this repository's own summary format. No external tool knows that
  grammar, and the whole implementation is a subprocess loop, a regex, and a
  percentile fold.

## Complexity classification

- Engineering tier: 2. One new script, one new test module, two committed
  artifacts, no new interface for anything else to depend on.
- Cynefin domain: Complicated. The mechanics are knowable and were verified
  empirically this session; nothing here is emergent.
- Derived methodology: spec, implement test-first, measure, record. No ADR, no
  prototype phase.
