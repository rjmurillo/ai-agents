---
type: task
id: TASK-025
title: Author and commit the v0.7.0 control-plane disposition ledger
status: todo
priority: P0
complexity: S
estimate: 3h
related:
  - DESIGN-021
blocked_by:
  - TASK-024
created: 2026-09-11
updated: 2026-09-11
author: spec-generator
tags:
  - control-plane
  - disposition
---

# TASK-025: Author and commit the v0.7.0 control-plane disposition ledger

## Objective

Write `.agents/metrics/control-plane-dispositions-v0.7.0.md`, classifying
every epic-named candidate plus the duplicate-gate finding, satisfying
REQ-022's seven acceptance criteria.

## In/Out of Scope

In scope: the ledger document itself, citing REQ-021's committed baseline.

Out of scope: any DELETE/MERGE mechanism work (REQ-022 AC-05); a validator
script for the ledger (DESIGN-021's deliberate choice).

## Acceptance Criteria

- [ ] TASK-025-AC1: One row for each of: #5394, #5395, #5396, #5404,
      #5420/#5421, #5436, #5241, and redundant hooks/review-axes/
      validators/workflows/mirrors the baseline surfaces.
- [ ] TASK-025-AC2: The duplicate-gate row is present, classified `KEEP`.
      Citations: `pre_pr_sequence.py:543-556`, `lefthook.yml:590`, and
      `test_pre_pr_sequence_registry.py:133-266`.
- [ ] TASK-025-AC3: Every `KEEP` row's five required fields are non-empty
      (spot-checked at PR review, per DESIGN-021).
- [ ] TASK-025-AC4: ADR-100 item 5 recorded as `DELETE` (the construct
      #5241 describes is absent from `qa_report.py`) and item 6 recorded
      as `EXPERIMENT` (owned by #5238/#5239), each with a one-line
      reason.
- [ ] TASK-025-AC5: No new GitHub child issue created as a byproduct of
      writing this ledger.
- [ ] TASK-025-AC6: `uv run python scripts/validation/pre_pr.py` passes.

## Files Affected

| File | Action | Description |
|---|---|---|
| `.agents/metrics/control-plane-dispositions-v0.7.0.md` | create | disposition ledger |

## Implementation Notes

1. Read REQ-021's committed baseline doc first; every numeric evidence
   citation in this ledger should point at that document rather than
   re-deriving a number.
2. Write the duplicate-gate KEEP row first: it is the worked example this
   cohort already has full evidence for, and it anchors the row format
   for the rest.
3. For each remaining epic-named candidate, read its issue (or ADR-100 for
   item 5) before writing the row; do not classify from the epic body's
   one-line description alone, the same discipline this cohort's own
   research applied to the duplicate-gate finding.
4. Resolve REQ-022 OQ1 (row order) and OQ2 (redundancy scope) per the
   assumptions recorded there, revisiting only if TASK-024's baseline
   surfaces a redundancy this spec did not anticipate.

## Testing Requirements

No automated tests (markdown document). `uv run python
scripts/validation/pre_pr.py` as the standard pre-PR gate. Manual
completeness check per DESIGN-021's Testing Strategy before marking this
task done.
