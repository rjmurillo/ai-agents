---
type: task
id: TASK-051
title: Build the durable outcome record, classifier, and matched report
status: implemented
priority: P1
related:
  - REQ-042
  - DESIGN-040
created: 2026-09-27
updated: 2026-09-27
author: plan
tags:
  - eval
  - metrics
  - v0.7.0
---

# TASK-051: Build the durable outcome record, classifier, and matched report

## Milestones

1. **Percentile merge.** Add public `percentile` to `_eval_common.py` with
   tests. Point `_model_sweep_core.py` and `_report_aggregator.py` at it and
   delete both private copies. Existing tests must still pass.
2. **Record parser.** Tests first for valid rows, unknown keys, bad enum,
   negative numbers, and null counts. Then `parse_record`.
3. **Classifier.** Tests first for each rule in DESIGN-040 order, including
   judge downgrade and judge no-upgrade. Then `classify`.
4. **Report.** Tests first for per-task rows, zero and all-success tasks,
   percentiles, null headline, and `UNVERIFIED` status. Then `build_report`.
5. **Comparison.** Tests first for unmatched config, differing task sets,
   `BETTER`, `WORSE`, `MIXED`, and the zero-drop rule that beats a better
   average. Then `compare`.
6. **Fixtures.** Known-good, plausible-known-bad, and the five issue cases.
7. **CLI.** Tests for exit codes 0, 1, and 2 and the JSON output. Then the
   CLI and a README section.

## Dependencies

Milestone 1 is independent. Milestones 2 to 5 are sequential. Milestone 6
feeds 3 to 5 tests. Milestone 7 needs 4 and 5.

## Risks

| Risk | Mitigation |
|---|---|
| Percentile merge changes sweep output | Same formula; existing sweep tests pin it |
| #5424 needs fields this lacks | Parser is strict; adding an optional field is a one-line change |
| Report read as a pass on missing data | Any `UNVERIFIED` row makes the report `UNVERIFIED` and exit 1 |

## Done

All REQ-042 criteria have a passing test. `pytest tests/eval` and `ruff`
are clean on the changed files.
