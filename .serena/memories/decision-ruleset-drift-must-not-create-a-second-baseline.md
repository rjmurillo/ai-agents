# Ruleset drift detection must not create a second baseline

## Question

Where should the scheduled detector read the pinned required contexts?

## Conventional answer

Issue #4909's generated PRD proposed
`scripts/ci/ruleset_required_contexts_baseline.txt`, separate from
`REQUIRED_CONTEXTS` in `tests/ci/test_merge_group_readiness.py`.

## First-principles position

A second baseline recreates the failure this detector exists to catch. The two
local mirrors can disagree while each test passes against its own copy. The
detector must read the same contract as the merge-group readiness gate.

## Evidence

- Live ruleset 11104075 and the pinned contract both contained 16 contexts on
  2026-08-11.
- PR #4869 had already accumulated three stale local assertions from copied
  snapshots.
- `tests/ci/test_ruleset_context_drift.py` proves a wrong pinned set returns
  exit 1 and names both sides of the divergence.

## Decision

`scripts/ci/ruleset_required_contexts.py` owns `REQUIRED_CONTEXTS`.
`tests/ci/test_merge_group_readiness.py` and
`scripts/ci/ruleset_context_drift.py` both import it. No text baseline exists.
