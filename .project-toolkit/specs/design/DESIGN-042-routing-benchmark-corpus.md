---
type: design
id: DESIGN-042
title: Routing benchmark corpus, loader, and grader
status: implemented
priority: P1
related:
  - REQ-044
  - TASK-053
created: 2026-09-29
updated: 2026-09-29
author: spec-generator
tags:
  - eval
  - routing-benchmark
---

# DESIGN-042: Routing benchmark corpus, loader, and grader

## Requirements Addressed

REQ-044 criteria 1 to 9.

## Files

| File | Role |
|---|---|
| `evals/routing-benchmark/scenarios/<id>/` | One scenario: `scenario.json`, `initial/`, `hidden/`, `known_good/`, `known_bad/`. |
| `scripts/eval/_routing_scenario.py` | Strict parser and corpus loader. |
| `scripts/eval/_routing_grader.py` | Materialize, diff, grade, and control checks. |
| `scripts/eval/eval_routing_corpus.py` | CLI that loads the corpus and runs every control. |

## Decisions

Fixture files end in `.fixture`. Linters, type checkers, and pytest then
ignore fixture code. Materializing strips the suffix.

`hidden/` holds grader-only acceptance files. The grader overlays them on a
scratch copy, so a driver never sees them and the driver directory is not
modified.

A verdict is PASS only when no changed path is out of scope, every expected
path changed, and every validation command exits 0. Judge dimensions are
stored but never read by the grader.

Validation commands are argv lists that start with `python`. The grader runs
them without a shell, on the current interpreter, with an environment
allowlist and a timeout.

## Controls

For each scenario the CLI proves: known-good PASS, known-bad FAIL, untouched
baseline FAIL, and two fresh copies equal `initial/`. Category 4 also needs a
scope violation on known-bad. Category 5 also needs known-bad to pass the
visible check and print the expected finding marker.
