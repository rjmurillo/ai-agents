# Execution Plan: Gate 3 latency measurement, epic #5456

## Metadata

| Field | Value |
|-------|-------|
| **Status** | In Progress |
| **Created** | 2026-09-16 |
| **Owner** | spec/plan/build (this session) |
| **Complexity** | Medium |
| **Spec** | REQ-027 |
| **Refs** | #5456 release gate 3, #5318 items 1 and 2 |

## Objectives

- [ ] Ship `scripts/metrics/gate_latency.py`: measurement only, exit code
      independent of every metric value, wired into no gate (REQ-027 AC-07,
      AC-13).
- [ ] Commit a measured per-job and whole-hook latency distribution for
      `pre-commit` and `pre-push` (REQ-027 AC-01 to AC-06, AC-11).
- [ ] Move epic #5456 release gate 3 from Unchecked to a recorded verdict
      backed by that measurement plus the job-set diff (REQ-027 AC-14).

## Milestones

### M1: Sampler and tests (independently shippable)

Exit criteria:

- `scripts/metrics/gate_latency.py` runs a whole hook N times through
  `lefthook run <hook> --no-tty --colors off --force --no-stage-fixed`, never
  `--job`, and parses lefthook's own summary into per-job samples.
- `tests/metrics/test_gate_latency.py` covers positive, negative, edge, and the
  CLI exit-code matrix, including the exit-0-for-any-metric-value matrix that
  makes the never-gates property verifiable.
- `uv run --frozen --extra dev ruff check` and the new test module pass.
- Proof of life on the cheapest hook: `--hook pre-merge-commit --repetitions 2`
  produces JSON with two repetitions and one parsed job.

### M2: Measurement captured (independently shippable, depends on M1)

Exit criteria:

- `.agents/metrics/gate-latency-v0.7.0.json` and `.md` committed, carrying
  `pre-commit` for at least two change classes, and `pre-push` for change
  classes that between them fire each of the five jobs #5318 item 1 names
  (`hook-anchoring-e2e`, `plugin-load-e2e`, `workflow-local-run`,
  `python-type-check`, `security-scan`). Any of the five that cannot run in this
  container is descoped by name in the artifact's exclusions, with its reason.
- Every percentile is emitted beside its `n`, the low-n note is present, and
  the markdown leads each scope with `worst observed of N runs` rather than a
  p95 headline (REQ-027 AC-05).
- The markdown states the one-machine, one-date scope and the host profile.

### M3: Gate 3 evidence recorded (depends on M2)

Exit criteria:

- The gate 3 row in `.agents/metrics/control-plane-dispositions-v0.7.0.md`
  carries the measured figures, the declared-versus-measured gap, and the
  job-set diff evidence, and does not claim the gate met on the diff alone
  (REQ-027 AC-15).
- The gate 4 row carries a named-exception argument for `gate_latency.py` on the
  same footing the sibling `control_plane_baseline.py` required, with the
  reference-absence check as its evidence (REQ-027 AC-16).
- The baseline's "no sampler exists" exclusion is answered in the ledger, with
  `.agents/metrics/control-plane-baseline-v0.7.0.json` left untouched, because
  every gate reads its "from" figure there.
- A comment on #5456 and a comment on #5318 carry the numbers.

## Tasks

| ID | Milestone | Task | Size | Done when |
|----|----|----|----|----|
| T1 | M1 | Parse lefthook's summary grammar into job name, seconds, status | S | A fixture of real captured output yields the expected samples, and a malformed summary yields zero samples without raising |
| T2 | M1 | Run one repetition: subprocess, wall clock, exit code, tree digest before and after | S | A repetition against `pre-merge-commit` records all four fields |
| T3 | M1 | Fold repetitions into nearest-rank p50/p95/min/max per job and for the hook | S | Hand-checked percentiles for a known sample list; n<20 sets `percentile_note` |
| T4 | M1 | Change-class table and `--file` wiring so glob-gated jobs fire | S | `--change-class python` passes the class file list to lefthook and records it |
| T5 | M1 | JSON and markdown writers reusing the symlink-refusing open, mode 0600 | S | A symlinked target is refused; output parses as JSON |
| T6 | M1 | Import declared budget from `lefthook_budget_model`, never recompute | S | Declared and measured appear side by side; no piped/parallel walk in this file |
| T7 | M1 | Test module: positive, negative, edge, CLI exit codes, never-gates matrix | M | Tests pass; a failing gate in a fixture still exits 0 |
| T8 | M2 | Capture `pre-commit` for two change classes | S | Artifacts written |
| T9 | M2 | Capture `pre-push` for the change classes covering #5318 item 1's five jobs, in the background, about 11 minutes per repetition | M | Artifacts written; tree-mutation flag inspected; any unmeasurable job descoped by name |
| T9b | M2 | Paired capture at baseline SHA `53ffe92c2` in an external worktree, same machine | M | Either a paired figure exists, or the attempt's failure and its reason are recorded (REQ-027 AC-15) |
| T10 | M3 | Ledger gate 3 row: measured figures, declared-versus-measured gap, job-set diff, and the paired result or its absence | S | Row carries a verdict with its evidence, and claims nothing the evidence does not carry |
| T10b | M3 | Ledger gate 4 row: named-exception argument for `gate_latency.py` | S | Row names the script, its never-gates property, and the reference-absence check |
| T11 | M3 | Issue comments on #5456 and #5318 | S | Both posted with figures, and no percentile quoted without its n |

## Dependency graph

```text
T1 ─┐
T2 ─┼─> T3 ─┐
T4 ─┤       ├─> T5 ─> T7 ─> (M1 done) ─> T8 ──┐
T6 ─┘       │                                 ├─> T10 ─> T11
            └────────────> T9 ─> T9b ─────────┘
                                   T10b ──────┘
```

T1, T2, T4 and T6 are independent and can be written in one pass. T6 feeds T5,
because the declared-versus-measured comparison is part of what T5 writes, so T5
is not done until T6 lands. T9 is the long pole and starts the moment M1 is
proven; T8 and T10b run alongside it. T10 waits on T9 and T9b, because the gate
3 row restates their figures.

## Risk register

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| A pre-push job mutates the working tree and later repetitions measure a different tree | Medium | High: silently invalid samples | `--no-stage-fixed`, plus a tree digest before and after every repetition recorded as `tree_mutated` |
| n is too small to support a p95 claim | High: a real pre-push run costs about 11 minutes | High: an unsupportable tail number becomes a planning figure | Emit `n` beside every percentile; `percentile_note` names p95 as an upper-order statistic below n=20; the markdown says so in prose |
| lefthook's summary grammar shifts on a version bump | Low | Medium: silent zero samples | `jobs_parsed` recorded per repetition; a grammar test pins the format against captured output |
| The sampler is mistaken for a gate and wired into `lefthook.yml` later | Medium | High: the epic's Abort-if clause 3 fires | AC-13 asserts the absence of references; the module docstring states the never-gates contract; the test matrix proves exit 0 for any value |
| A failing gate aborts the run and truncates the sample | Medium | Medium | Record the exit code, keep the parsed samples, continue the remaining repetitions |
| The container's 4 cores make these numbers unlike a workstation | Certain | Medium if misread | `HostProfile` in the artifact; one-machine scope stated in prose, matching MUST-16's own wording about its figures |
| The job-set diff is read as proof that latency did not regress | High, it is the intuitive reading | High: gate 3 marked met while a surviving job silently slowed | The diff bounds the declared ceiling only. 50 commits and 1,999 changed files separate the two SHAs and test files grew 1,031 to 1,174, so T9b takes the paired measurement, and if it cannot, T10 records a first reference rather than a met gate |
| `workflow-local-run` needs `act` and a container runtime this environment may not have | Medium | Low if named, High if silently skipped | T9 descopes any unrunnable job by name in the artifact's exclusions |

## Deferred items

- Acting on what the measurement shows: scoping `python-tests` to the push
  range, resizing any `timeout:`, reconciling ADR-054 with ADR-104. All are
  #5318's decisions, not this plan's.
- Any schedule or ratchet around re-measurement. A synchronization obligation is
  the failure this epic subtracts.
