---
qaVerdict: PASS
qaSessionLog: .agents/sessions/2026-08-18-session-99918-b3a3fed1d-fix-issue-5142-minimum_aggregators_examined-stale.json
qaCommit: f7e201b516f20380c995a065f6e97bfb8cbf8eff
---

# QA Report: MINIMUM_AGGREGATORS_EXAMINED stale constant (issue #5142)

## What was verified

`tests/workflows/test_aggregator_cancellation_guard.py::TestRepositoryWideSweep::test_every_pr_head_aggregator_is_guarded` was failing on `origin/main` itself with `sweep examined only 5 aggregator jobs, expected at least 7`. Root-caused by running the same classifier (`unguarded_pr_head_aggregators`) against `origin/main` at two points in history via `git show`: the commit before PR #5132 ("delete AI PR Quality Gate") examined 7 jobs (the 5 in `FIXED_AGGREGATORS` plus `ai-pr-quality-gate.yml::aggregate` and `ai-session-protocol.yml::aggregate`); `origin/main` at HEAD examines 5, because both of those workflow files were deleted in full by #5132 and #5135. No other workflow's job set changed between the two measurements. This confirms the drop is a legitimate consequence of intentional cleanup, not a classifier regression.

## Fix

One-line constant change (`MINIMUM_AGGREGATORS_EXAMINED = 7` to `5`) plus an updated comment recording why, in `tests/workflows/test_aggregator_cancellation_guard.py`.

## Evidence

```text
$ uv run --frozen python -m pytest tests/workflows/test_aggregator_cancellation_guard.py -v
34 passed in 0.87s
```

All 34 tests in the file pass, including the negative controls (`test_sweep_reports_an_unguarded_aggregator`, `test_sweep_catches_a_reusable_workflow_call_aggregator`) that prove the classifier itself still correctly detects an unguarded aggregator; only the pinned floor changed.

## Scope

Single-file test change. No production code, no workflow YAML, no security-relevant surface touched.
