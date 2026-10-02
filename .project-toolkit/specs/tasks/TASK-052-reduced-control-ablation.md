---
type: task
id: TASK-052
title: Build the reduced-control ablation runner and its five-task corpus
status: draft
priority: P1
related:
  - REQ-043
  - DESIGN-041
created: 2026-09-28
updated: 2026-09-28
author: plan
tags:
  - eval
  - metrics
  - v0.7.0
---

# TASK-052: Build the reduced-control ablation runner and its five-task corpus

## Milestones

1. **Comparison fix (AC-10).** `_require_configs_match_except_control` skips
   `context_bytes`. Update REQ-042, DESIGN-040, and the README line. Test: a
   pair differing only in `control` and `context_bytes` compares; a pair
   differing in `model` still refuses.
2. **Pure core (AC-1, AC-5 to AC-7, AC-9).** `_control_ablation.py`: loader,
   control resolver, record builder. Unit tests per refusal and per record
   field, including negative and edge cases.
3. **Workspace grader (AC-4, AC-5).** `_control_ablation_grade.py`: seed,
   commit, run commands, changed paths, unittest summary parse. Tests use a
   real temporary git repository and real `python3` commands.
4. **CLI (AC-2, AC-3, AC-8, AC-11).** `eval_control_ablation.py` with
   `--tasks`, `--controls`, `--repeats`, `--model`, `--workspace-root`,
   `--output-dir`, `--max-runs`, `--timeout`, `--dry-run`. Tests inject a fake
   runner that writes files and emits canned stream-json.
5. **Corpus.** Five tasks, one per #5768 case, with `known_good` and
   `known_bad`. A test runs the dry run over the checked-in file.
6. **Docs.** README section under "Durable Outcome Report".
7. **Live run (separate PR).** 5 tasks x 2 controls x 3 repeats = 30 runs.
   Record the comparison in the ledger's gate 5 to 7 rows.

## Risks

| Risk | Mitigation |
|---|---|
| Auth unavailable in the isolated profile | Live run waits on the operator; build and dry run need none |
| Graders that always pass | AC-2 dry run with known-bad controls |
| Scope creep into #5424 | Out of scope list in REQ-043 |

## Size

M. human: ~1 week / AI: ~3 hours.
