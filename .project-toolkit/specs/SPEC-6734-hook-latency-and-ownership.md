# SPEC-6734: Local hook latency baseline and check ownership table

Issue: #6734. Owner decision (2026-10-20): option A, slices 1 and 2 only. Measure, then map ownership. No check moves between pre-commit, pre-push, and CI in this change.

## Step 0 First Principles

### Q1 Demand Reality

Richard Murillo filed #6734 and chose option A on 2026-10-20. Epic #5456 needs a local-hook p50/p95 baseline for its release gate. The coding agents that commit and push through `lefthook.yml` are the systems that wait on the hooks.

### Q2 Status Quo

A contributor commits and pushes, and every job in `lefthook.yml` runs. Nobody can say which boundary owns a check, or what a push costs at p95, because the only baseline (`.project-toolkit/metrics/gate-latency-v0.7.0.md`) has n=2 and no load reading. Reframing: skipped (owner froze the scope to measurement and a table).

### Q3 Desperate Specificity

The coding agent waiting on `lefthook run pre-push`. A pilot push on 2026-10-20 took 382.9s, past ADR-104's 300s pre-push target, and nobody knows which jobs could move without losing enforcement.

### Q4 Narrowest Wedge

One baseline run per hook and change class at a pinned SHA, plus one ownership table for all pre-commit and pre-push jobs. About 6 hours, most of it unattended measurement.

### Q5 Observation

Pilot runs on 2026-10-20 at d7ae505 (4-CPU container, load average under 1): pre-push python class 382.9s wall clock, with `pre-pr-validation` 267.0s, `zero-collection-tests` 123.7s, and `count-ratchets` 79.6s. Pre-commit markdown class 34.7s, with `agents-write-targets` at 28.7s. The v0.7.0 record shows 9.66s and 124.56s for comparable classes on 2026-09-16. The sampler parsed 0 jobs on the first pilot because `lefthook.yml` sets `output: false`.

### Q6 Future-fit

At ten times the jobs, a table nobody keeps current becomes wrong. So this change publishes a dated record tied to a SHA, not a live policy. Re-measuring is one command per class.

## Prior Art / Constraints

- REQ-027 built `scripts/metrics/gate_latency.py`. It measures whole hooks only (ci-scripts.md MUST-16) and never gates (DR1).
- `.project-toolkit/metrics/gate-latency-v0.7.0.md` is the earlier record: n=2 or 3, no load average.
- Load average capture was added after v0.7.0 (`gate_latency_probe._load_average`).
- ADR-104 records `LEFTHOOK_OUTPUT=summary,success,failure` as the way to see output under `output: false`.
- #6671 owns the pushed-ref correctness fix. #6708 owns the semgrep infrastructure failure. This change does not touch either.

## Problem statement

The hooks cost minutes per push, but no reproducible baseline with p95 exists, and no record says which boundary owns each check. Budgets and relocation decisions (slices 3 and 4) cannot be made without both.

## User stories

- As the repository owner, I can read p50 and p95 for each hook and change class at a named SHA, so I can set budgets from data.
- As a contributor proposing a slice 3 or 4 change, I can look up a job's owner boundary and CI counterpart before I move it.

## Ontology

- **Hook**: `pre-commit` or `pre-push` in `lefthook.yml`.
- **Job**: a leaf entry under a hook, including entries nested in groups.
- **Change class**: a fixed file list from `scripts/metrics/gate_latency_classes.py`. `markdown` is docs-only, `python` is code, and `workflows` is security-sensitive (action pinning, workflow validation).
- **Owner boundary**: `pre-commit`, `pre-push`, or `required CI`. Exactly one per job.
- **Repetition**: one whole-hook run. Repetition 0 after checkout is cold. Repetitions 1 to 20 are warm.

## Data model

Per run: the existing `GateLatencyReport` JSON (commit, host, load before and after each repetition, per-job samples). Per job: one ownership row (hook, job, scope, blocking or advisory, security relevance, CI counterpart, owner boundary, reason).

## Integrations

Lefthook 2.2.2 through `uv run --frozen`. The sampler reads `lefthook.yml` from the measured checkout. Network: `push-ref-staleness` and `security-scan` may reach the remote, which is a source of variance and is recorded as such.

## Failure modes

- A failing repetition is excluded from summaries (`truncated`), and the report says so. A class whose repetitions all fail is reported as failed, never as fast.
- Other work on the box inflates figures. Each repetition records load before and after it.
- Main moves during measurement. Measurement uses fixture branches at d7ae505 and a first-push ref line, so the outgoing range stays one commit.

## Security

No new security surface. The sampler change sets one environment variable on a subprocess it already runs. The remote URL is redacted by the existing `_redact_url_userinfo`. No hook, workflow, or security check changes.

## Observability

The baseline is the metric. Proof it works: every passing repetition reports `jobs_parsed` greater than 0.

## Acceptance criteria

1. When `gate_latency_sampler` runs a hook, it shall set `LEFTHOOK_OUTPUT` to a value that includes `summary` for that subprocess, overriding any inherited value.
2. When a hook repetition passes under `output: false`, the sampler shall report `jobs_parsed` greater than 0.
3. The baseline shall cover pre-commit and pre-push for the `markdown`, `python`, and `workflows` classes. Each runs at d7ae505 plus one fixture commit touching that class's file, with 1 cold and 20 warm repetitions.
4. The baseline shall report, per hook and class, n, p50, p95, max, and the cold repetition, plus the five most expensive jobs by warm p50.
5. Each repetition shall record the 1-minute load average before and after it.
6. The ownership table shall list every leaf job of `pre-commit` and `pre-push`. Its count shall equal the leaf count in `lefthook.yml` at d7ae505.
7. Each ownership row shall name exactly one owner boundary. Each job retained at more than one boundary shall state why.
8. The change shall not modify `lefthook.yml` or any file under `.github/workflows/`.
9. The baseline shall propose budgets derived from the measured p95. It shall not enforce them.
   Outcome note: met for pre-commit (60s, 1.7x the measured p95). Not met as written for pre-push: the same 1.7x rule would give about 634s, too loose to catch a regression, and a ceiling at the p95 itself would sit below runs already observed. The record proposes a max-based 400s tripwire instead and states that basis in its row.

## Out of scope

- Moving any check between boundaries (slices 3 and 4).
- Changing `output: false` in `lefthook.yml`.
- Fixing #6671 or #6708.
- A validator that keeps the ownership table in sync with `lefthook.yml`. That would be a new governance layer, which #6734 forbids.

## Deferred

- Slice 3 (scope the unscoped pre-push jobs to the outgoing range). Owner: Richard Murillo.
- Slice 4 (relocate to required CI). Needs per-item owner approval.

## Open questions

- Which CI contexts are required checks? The live ruleset was not read from this session. The table uses the nine contexts pinned in `scripts/ci/ruleset_required_contexts.py` and says so. Owner: Richard Murillo.

## CVA summary

Common: every measurement uses the same sampler, SHA, host, and ref-line shape. Varies: hook and change class. Relationship: the class picks which glob-scoped jobs fire. Unscoped jobs run in every class.

## Buy-vs-build decision

N/A (measurement and documentation; reuses the REQ-027 sampler).

## Complexity classification

Tier 2. Problem domain: Complicated (analysis by measurement; no experiment on production behavior). Methodology: measure, then document.

## Plan

Tier 2, so the plan lives here rather than in a separate execution plan.

| Milestone | Task | Size | Done when | Covers |
|---|---|---|---|---|
| M1 instrument | Force `LEFTHOOK_OUTPUT` in the sampler, with positive, negative, edge, and premise tests | S | Tests pass, and fail with the override unwired | AC-1, AC-2 |
| M2 measure | Fixture branch per class at d7ae505; run each hook and class with 21 repetitions, one at a time | M | Six JSON and markdown reports, each with load per repetition | AC-3, AC-5 |
| M3 report | Summarize cold, warm p50 and p95, max, top jobs, and proposed budgets | S | Every figure traces to a committed per-run artifact | AC-4, AC-9 |
| M4 ownership | One row per leaf job with one owner boundary and reasons for jobs at two boundaries | M | Row count equals the `lefthook.yml` leaf count | AC-6, AC-7 |
| M5 ship | Pre-PR validation, PR, issue body update | S | CI green, AC-8 diff check clean | AC-8 |

Dependencies: M2 needs M1. M3 needs M2. M4 is independent and runs while M2 measures, with read-only work only, so it adds no load. M5 needs M3 and M4.

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| A job fails in the fixture runs, so repetitions are excluded | Medium | No figure for that class | Pilot each hook first; report a failed class as failed |
| Concurrent work on the box inflates timings | Medium | Wrong baseline | No heavy commands during M2; load recorded per repetition |
| `workflow-local-run` needs a container runtime the box lacks | Medium | Workflows class differs from a developer laptop | Record its status and duration as observed, and state the exclusion |
| Remote calls add network variance | Low | Wider p95 | Report max beside p95 and name the network-touching jobs |
