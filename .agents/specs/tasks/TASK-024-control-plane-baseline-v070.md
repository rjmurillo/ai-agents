---
type: task
id: TASK-024
title: Build and commit the control-plane baseline for v0.7.0
status: todo
priority: P0
complexity: L
estimate: 7h
related:
  - DESIGN-020
blocks:
  - TASK-025
created: 2026-09-11
updated: 2026-09-11
author: spec-generator
tags:
  - control-plane
  - baseline
  - measurement
---

# TASK-024: Build and commit the control-plane baseline for v0.7.0

## Objective

Implement `scripts/metrics/control_plane_baseline.py`, its test suite, and
the committed baseline doc pair, satisfying REQ-021's twelve acceptance
criteria and DESIGN-020's component architecture.

## In/Out of Scope

In scope: the CLI, its eight dimension modules, the JSON/markdown writers,
the test suite, and the committed baseline artifact at one pinned SHA.

Out of scope: anything REQ-021's Out of Scope section names (reduced-config
comparison, final release report, mechanism deletions, gate p50/p95
sampling, fan-out routing changes).

## Acceptance Criteria

- [ ] TASK-024-AC1: `scripts/metrics/control_plane_baseline.py` exists,
      exposes `--repo`, `--json`, `--markdown`, `--allow-dirty`, and
      implements the exit-code contract (0 success, 1 dirty tree or
      symlink refusal, 2 config error).
- [ ] TASK-024-AC2: Each of the eight dimension functions in
      `control_plane_baseline.py` (not a `dimensions/*.py` package; see
      DESIGN-020's Component Architecture revision) exists and returns its
      dataclass or `None`-with-reason independently testable.
- [ ] TASK-024-AC3: `always_loaded.py` imports `instruction_budget`'s token
      estimator; no second token-counting implementation exists in this
      script (REQ-021 AC-04, DR4).
- [ ] TASK-024-AC4: `gate_budget.py` imports (or, after extraction,
      imports from a shared module) the same summation function
      `tests/ci/test_lefthook_declared_budget.py` uses (REQ-021 AC-06,
      DR4). Resolve OQ3 first: confirm whether extraction is required.
- [ ] TASK-024-AC5: `tests/metrics/test_control_plane_baseline.py` covers
      positive, negative, edge, CLI exit-code, parity, reproducibility, and
      no-content-leak cases per DESIGN-020's Testing Strategy.
- [ ] TASK-024-AC6: A synthetic-value test matrix asserts exit 0 across
      metric values deliberately exceeding every release target (REQ-021
      AC-08); this is the test that makes DR1 verifiable, not aspirational.
- [ ] TASK-024-AC7: `.agents/metrics/control-plane-baseline-v0.7.0.md` and
      `.json` are committed at one pinned `main` SHA, with the exact
      command, every exclusion and its reason, and the release targets
      recorded (REQ-021 AC-12).
- [ ] TASK-024-AC8: `uv run pytest tests/metrics -x`, `uv run ruff check
      scripts/metrics tests/metrics`, and `uv run python
      scripts/validation/pre_pr.py` all pass before this task is marked
      done.

## Files Affected

**Revised at implementation time (design review, 2026-09-11)**: DESIGN-020's
Component Architecture dropped the `dimensions/` package for one module (see
that file's Component Architecture note). This table reflects the revision;
the eight dimension functions, `Baseline` dataclass, and the two report
writers all live in one file.

| File | Action | Description |
|---|---|---|
| `scripts/metrics/control_plane_baseline.py` | create | CLI entry point, eight dimension functions, `Baseline` dataclass, `write_json`/`write_markdown`, `_safe_open` |
| `tests/metrics/test_control_plane_baseline.py` | create | full test suite per DESIGN-020 |
| `scripts/ci/lefthook_budget_model.py` | move (from `tests/ci/`) | make the declared-budget summation importable from production code, not test code (REQ-021 OQ3, AC-04) |
| `tests/ci/test_lefthook_declared_budget.py` | modify | update import path after the move above |
| `tests/ci/test_lefthook_container_bound.py` | modify | update import path after the move above |
| `.agents/critique/ADR-104-debate-log.md` | modify | update the one path mention of the moved module |
| `.agents/metrics/control-plane-baseline-v0.7.0.md` | create | committed baseline, pinned SHA |
| `.agents/metrics/control-plane-baseline-v0.7.0.json` | create | machine-readable twin |

## Implementation Notes

1. Resolve OQ3 (gate-budget summation location) and the DESIGN-020 open
   question on `policy_owners`'s always-on parser before writing those two
   modules; both are small investigations (read the two source files), not
   design changes.
2. Build dimension modules independently and unit-test each before wiring
   the aggregator, so AC-07's degrade-to-null behavior is verified per
   dimension, not only at the CLI level.
3. Write the exit-code contract and its synthetic-value test matrix early;
   it is the single most important behavioral guarantee this task ships
   (DR1), and every other dimension's correctness is secondary to never
   letting this script gate.
4. Run the live smoke against this repository last, once all dimensions are
   wired, to catch a dropped key before committing the baseline doc.
5. Pin the baseline doc's commit SHA to the actual `HEAD` at commit time,
   not `cd0f9561d` if `main` has advanced; update REQ-021 AC-12's cited SHA
   in the PR description if it differs.

## Testing Requirements

Per DESIGN-020's Testing Strategy: positive, negative, edge, CLI exit-code,
parity (AC-06), reproducibility (AC-11), and no-content-leak (AC-09)
coverage, plus the live smoke against this repository (manual or slow-tier
CI, not blocking on every push). Minimum: `uv run pytest tests/metrics -x`
green, `uv run ruff check scripts/metrics tests/metrics` clean, `uv run
python scripts/validation/pre_pr.py` green before this task is marked done.
