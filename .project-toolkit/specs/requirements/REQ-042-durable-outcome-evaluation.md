---
type: requirement
id: REQ-042
title: Measure durable accepted outcomes and human correction cost
status: implemented
priority: P1
category: functional
source: issue-5768
related:
  - DESIGN-040
  - TASK-051
  - REQ-024
created: 2026-09-27
updated: 2026-09-27
author: spec
tags:
  - eval
  - metrics
  - v0.7.0
---

# REQ-042: Measure durable accepted outcomes and human correction cost

## Step 0 First Principles

### Q1 Demand Reality

Issue #5768, filed by rjmurillo under epic #5456. Gate 5 of the v0.7.0
disposition ledger needs a reduced-control comparison on identical tasks
(`.project-toolkit/metrics/control-plane-dispositions-v0.7.0.md:953`).
Issue #5424 needs a result record contract before its runner can emit rows.

### Q2 Status Quo

Eval scripts report pass rates, token cost, and bootstrap intervals per
variant. Nothing records what happened after the agent claimed completion.
A run that passes its first check but breaks on follow-up validation counts
as a success. Release notes fall back to token volume or pass rate.

### Q3 Desperate Specificity

The #5424 routing benchmark runner. It has no record contract that separates
immediate acceptance from durable outcome, so any row it emits today would
reward activity instead of accepted results.

### Q4 Narrowest Wedge

One pure core module with a strict record parser, a fail-closed classifier,
a distribution report, and a matched comparison. One thin CLI. Fixtures that
prove discrimination. One consolidation of the duplicate percentile helper.
About six hours.

### Q5 Observation

Measured on `main` at `d8c6176d2` on 2026-09-27: `scripts/eval/` has no
module that reads follow-up validation, rework time, or rollback events.
`_percentile` is defined twice, at `_model_sweep_core.py:43` and
`_report_aggregator.py:270`. #5424 and #5425 are open with no code.

### Q6 Future-fit

At 10x tasks the record stays one JSONL row per task run. The report is
linear in rows. The contract grows by adding optional evidence fields, and
the parser refuses unknown keys so drift is loud.

## Prior Art / Constraints

- Memory search (`search_memory.py`, four queries: durable outcome
  evaluation, cost per accepted task, human correction rework, routing
  benchmark result schema) returned no direct prior art.
- `_harness_capability.py:52` `CapabilityStatus` is the fail-closed pattern
  to mirror: evidence sets a positive status, absence resolves to
  `UNVERIFIED`.
- #5424 and #5425 contracts do not exist yet, so reuse is impossible. This
  requirement defines the record #5424 emits, which prevents a second one.
- #5400 has no implementation. The record carries `context_bytes` so a later
  #5400 measurement fills it without a schema change.
- Retrospective `2026-09-04-issue-5423-not-run-carried-forward-as-pass.md`:
  a missing result must never read as a pass.

## Problem statement

Eval output rewards activity. No record distinguishes a result that passed
its first check from one that stayed correct after integration, and no
report prices the accepted durable task.

## User stories

- As the release owner, I read cost per accepted durable task and residual
  risk as the headline, so v0.7.0 claims rest on accepted outcomes.
- As the #5424 runner author, I emit one strict record per task run, so the
  benchmark shares one contract with this report.
- As a reviewer, I see per-task results and zero-success tasks, so a few
  strong runs cannot hide widespread failure.

## Ontology

- **OutcomeRecord**: one task run under one RunConfig. Holds five sections:
  capability, execution, durable, economics, risk.
- **RunConfig**: model, harness, harness_version, context_bytes,
  retry_budget, reviewer, control. Two records are matched when every field
  except `control` is equal. `context_bytes` may also differ, but only when
  `control` differs, because the control determines the bytes loaded.
- **Evidence**: `PASS`, `FAIL`, or `UNVERIFIED`. Missing evidence is
  `UNVERIFIED`, never `PASS`.
- **Verdict**: `ACCEPTED_DURABLE`, `ACCEPTED_NOT_DURABLE`, `REJECTED`, or
  `UNVERIFIED`, derived by the classifier.
- **ConfigurationReport**: per-task verdicts plus distribution statistics and
  the headline for one control configuration.
- **Comparison**: two matched ConfigurationReports over the same task set.

Decision rules: deterministic evidence first. A model judge may downgrade
acceptance, never upgrade a deterministic `FAIL` or `UNVERIFIED`.

## Data model

See DESIGN-040 for field-level types. Invariants:

1. Every numeric count and cost is a finite, non-negative number.
2. Unknown keys are refused, so the contract cannot drift silently.
3. `task_id` plus `repeat` is unique per configuration.

## Integrations

- #5424 runner writes OutcomeRecord JSONL. Not built yet.
- Follow-up validation data comes from whoever runs the follow-up check.
  The CLI reads files only; it calls no model and no network.

## Failure modes

| Mode | Behavior |
|---|---|
| Malformed record | CLI exits 2 and names the line |
| Evidence missing | Record verdict `UNVERIFIED`; report status `UNVERIFIED` |
| Zero accepted durable tasks | Cost per accepted durable task is `null`, not zero |
| Unmatched comparison | CLI exits 2 and names the differing field |
| Task sets differ | CLI exits 2 and names the missing task ids |

## Security

No network, no model calls, no secrets. Input is local JSONL read with
`json.loads`. Paths come from argv and are opened read-only.

## Observability

The report itself is the metric. Headline: cost per accepted durable task,
human correction minutes per accepted durable task, and residual risk count.

## Acceptance criteria

1. The system shall parse an OutcomeRecord with capability, execution,
   durable, economics, and risk sections, and refuse unknown keys.
2. When deterministic acceptance is `FAIL`, the classifier shall return
   `REJECTED` whatever the judge verdict says.
3. When any required evidence is `UNVERIFIED`, the classifier shall return
   `UNVERIFIED` and the report status shall be `UNVERIFIED`.
4. When immediate acceptance passes but follow-up validation fails, residual
   defects are above zero, or a rollback occurred, the classifier shall
   return `ACCEPTED_NOT_DURABLE`.
5. The report shall list per-task verdicts, zero-success tasks, and
   all-success tasks, plus p10, p50, and p90 of cost and correction time.
6. The report headline shall be cost per accepted durable task, correction
   minutes per accepted durable task, and residual risk count, and shall be
   `null` when no task is accepted durable.
7. When two configurations differ in any RunConfig field other than
   `control`, differ in `context_bytes` while sharing a `control`, cover
   different task sets, or run a task a different number of times, the
   comparison shall refuse.
8. The comparison shall return `BETTER` only when the candidate has at least
   as many accepted durable tasks, no higher cost per accepted durable task,
   and no task that drops from one or more durable accepts to zero.
9. A known-good fixture shall classify as `ACCEPTED_DURABLE` and a
   plausible-known-bad fixture shall classify as `ACCEPTED_NOT_DURABLE`.
10. Fixtures shall cover the five issue cases: ambiguous requirement,
    interrupted resume with stale state, plausible-wrong change caught by a
    reviewer, consequential action without approval, and a hidden regression
    found by follow-up validation.
11. The two `_percentile` copies shall merge into one public helper that the
    new module also uses.

## Out of scope

- Live paid runs and the reduced-control experiment itself. #5426 owns them.
- The #5425 scenario corpus and the #5424 runner.
- A human hourly rate. Correction time stays in minutes.
- Production observability.

## Deferred

- Running the matched experiment on real tasks: owner #5426.
- Filling `context_bytes` from a #5400 measurement: owner #5400.

## Open questions

None blocking. The #5424 author may add optional evidence fields.

## CVA summary

Common: every task run yields the same five sections and one verdict.
Varies: the control configuration and the evidence source. Relationship:
matched comparison varies only `control`.

## Buy-vs-build decision

Context, not core. Alternatives: an external eval framework (adds a
dependency and a second record format), extend `_report_aggregator.py`
(its `RunRecord` has no durable section and is tied to the plan runner).
Recommendation: build a small stdlib module. Rationale: no new dependency,
one contract for #5424.

## Complexity classification

Tier 3 (about six hours, seven entities). Domain: Complicated. Method:
test-first vertical slices.
