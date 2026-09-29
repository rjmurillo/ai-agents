---
type: design
id: DESIGN-043
title: Routing benchmark runner, plan, backends, and results
status: implemented
priority: P1
related:
  - REQ-045
  - TASK-054
created: 2026-09-29
updated: 2026-09-29
author: spec-generator
tags:
  - eval
  - routing-benchmark
---

# DESIGN-043: Routing benchmark runner, plan, backends, and results

## Requirements Addressed

REQ-045 criteria 1 to 13.

## Files

| File | Role |
|---|---|
| `scripts/eval/_routing_config.py` | Config parser and the A-F strategy invariants. |
| `scripts/eval/_routing_plan.py` | Zero-spend plan, eligibility, and matched-pair classification. |
| `scripts/eval/_routing_dag.py` | Invocation DAG per topology. |
| `scripts/eval/_routing_result.py` | Result records and requested-versus-observed verdicts. |
| `scripts/eval/_routing_backend.py` | `Backend` protocol and the deterministic `ScriptedBackend`. |
| `scripts/eval/_routing_run.py` | `run_planned`, violation detection, and `compare_pair`. |
| `scripts/eval/_routing_live.py` | Live gate and `LiveBackend`. |
| `scripts/eval/eval_routing_benchmark.py` | CLI. |
| `scripts/eval/examples/routing-benchmark-config.json` | Example config for arms A to F. |

## Decisions

Eligibility comes only from `build_report(records)["arm_eligibility"]`. The
plan never derives a class itself. Only ELIGIBLE_MATCHED and
ELIGIBLE_UNMATCHED rows are planned.

A pair is matched when both harnesses are ELIGIBLE_MATCHED and their semantic
contracts are equal. The contract covers scenario state, task text, grader,
difficulty, routes, work packages, concurrency, correction budget, reviewer,
fresh-context boundary, and handoff artifact.

Run status keeps four outcomes apart: ACCEPTED, TASK_FAILED, HARNESS_FAILED,
and CONTRACT_VIOLATION. A harness failure skips grading. Unknown telemetry
stays `None`.

An observed model or effort is HONORED only with backend evidence that equals
the request. A client echo or a missing value is UNVERIFIED.

The live gate raises before a backend exists. It needs `--live` and a
credential for every planned harness. Credential names come from
`HARNESS_AUTH_ENV` in `scripts/eval/_runtime_harness.py`.

## Exit codes

0 planned or live run done. 1 nothing plannable. 2 invalid input. 3 live harness
failure. 4 live run without credentials.
