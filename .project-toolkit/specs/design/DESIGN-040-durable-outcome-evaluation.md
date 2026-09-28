---
type: design
id: DESIGN-040
title: Durable outcome record, classifier, and matched report
status: implemented
priority: P1
related:
  - REQ-042
  - TASK-051
created: 2026-09-27
updated: 2026-09-27
author: spec-generator
tags:
  - eval
  - metrics
  - v0.7.0
---

# DESIGN-040: Durable outcome record, classifier, and matched report

## Requirements Addressed

REQ-042 criteria 1 to 11.

## Files

| File | Role |
|---|---|
| `scripts/eval/_durable_outcome.py` | Pure core: record parser, classifier, report, comparison |
| `scripts/eval/eval_durable_outcome.py` | CLI: read JSONL, print JSON report, exit code |
| `scripts/eval/_eval_common.py` | Gains public `percentile`, the one merged copy |
| `tests/eval/test_durable_outcome.py` | Core tests |
| `tests/eval/test_eval_durable_outcome_cli.py` | CLI tests |
| `tests/eval/fixtures/durable_outcome/*.jsonl` | Known-good, known-bad, and five-case fixtures |

## Record (one JSONL row)

```json
{
  "task_id": "fix-null-check",
  "repeat": 0,
  "config": {"model": "claude-sonnet-5", "harness": "claude",
             "harness_version": "2.3.1", "context_bytes": 48210,
             "retry_budget": 2, "reviewer": "critic", "control": "full"},
  "capability": {"attempted": true, "produced_artifact": true},
  "execution": {"deterministic_acceptance": "PASS", "first_pass": "PASS",
                "tool_failures": 0, "retries": 0, "scope_violations": 0,
                "judge": "PASS"},
  "durable": {"followup_validation": "PASS", "objective_satisfied": "PASS",
              "residual_defects": 0, "review_findings": 0,
              "rollback_events": 0, "rework_minutes": 0},
  "economics": {"model_cost_usd": 0.42, "tool_cost_usd": 0.0,
                "wall_seconds": 310, "human_correction_minutes": 0},
  "risk": {"security_findings": 0, "unapproved_external_actions": 0,
           "unsupported_claims": 0, "unresolved_uncertainty": 0}
}
```

Evidence fields take `PASS`, `FAIL`, or `UNVERIFIED`. `judge` is optional and
may be `null`. Counts are non-negative integers. Money and time are
non-negative numbers. A count may be `null`, which means not measured.

## Classifier order

1. `deterministic_acceptance` is `FAIL`, or `capability.attempted` is false:
   `REJECTED`.
2. Any required evidence is `UNVERIFIED`, or any durable or risk count is
   `null`: `UNVERIFIED`.
3. `judge` is `FAIL`: `REJECTED`. The judge only downgrades.
4. Follow-up `FAIL`, objective `FAIL`, residual defects above zero, rollback
   events above zero, or unapproved external actions above zero:
   `ACCEPTED_NOT_DURABLE`.
5. Otherwise `ACCEPTED_DURABLE`.

Step 1 runs before step 2 so a known deterministic failure is reported as a
failure even when other telemetry is missing.

## Report

One input file holds one configuration. Mixed configurations in a file, or a
repeated `task_id` and `repeat` pair, are refused. Per configuration: status (`VERIFIED` or `UNVERIFIED`; it states evidence completeness, not success), verdict counts, per-task
rows (repeats, durable accepts, verdicts), `zero_success_tasks`,
`all_success_tasks`, and p10, p50, p90 of total cost and correction minutes.

Headline, in this order:

1. `cost_per_accepted_durable_task_usd`: total model plus tool cost over all
   runs, divided by the accepted durable count. `null` when the count is 0.
2. `correction_minutes_per_accepted_durable_task`: human correction plus
   rework minutes over all runs, divided the same way.
3. `residual_risk`: sum of security findings, unapproved external actions,
   unsupported claims, and unresolved uncertainty, plus residual defects in
   accepted runs.

Costs of rejected runs stay in the numerator. Failed attempts are part of
the price of an accepted result.

## Comparison

Refuse (exit 2) when the configs differ in any field except `control`, or
the task sets differ. Otherwise return `BETTER`, `WORSE`, or `MIXED`, or
`UNVERIFIED` when either side is `UNVERIFIED`. `BETTER` needs all of: more
or equal accepted durable tasks, equal or lower cost per accepted durable
task, and no task that falls from one or more durable accepts to zero.
`WORSE` is the mirror. Anything else is `MIXED`.

## CLI

```text
eval_durable_outcome.py --records RUN.jsonl [--baseline BASE.jsonl]
```

Exit codes follow ADR-035: 0 report written with status `VERIFIED`, or a
`BETTER` or `MIXED` comparison. 1 report written with status `UNVERIFIED`, or
a `WORSE` or `UNVERIFIED` comparison. 2 input or match error. An `UNVERIFIED`
result never exits 0, so a missing result cannot read as a pass.

## Subtraction offset

`_percentile` in `_model_sweep_core.py` and `_report_aggregator.py` merge into
one public `percentile` in `_eval_common.py`. The sweep copy existed because
the aggregator's helper was private; a public contract removes that reason.
