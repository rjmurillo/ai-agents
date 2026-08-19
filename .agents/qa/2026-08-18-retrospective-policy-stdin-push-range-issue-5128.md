---
qaVerdict: PASS
qaSessionLog: .agents/sessions/2026-08-18-session-99918-b6aa4aa72-fix-issue-5128-retrospective-policy-stdin.json
qaCommit: 18ce2d5162e7b759b44db34126144e3f7d9fb47a
---

# QA Report: retrospective-policy stdin push-range fix (issue #5128)

## What was verified

`{push_files}` resolves empty on a branch's first push because lefthook's own diff-against-previous-remote-ref substitution has nothing to diff against, which silently defeated `check_retrospective_evidence`'s documentation-only bypass regardless of what the push actually contained. `_handle_retrospective` in `scripts/validation/git_hook_policy.py` now derives the real push range via `_push_range_changed_files`, the same stdin-based mechanism `observation-sync-advisory`, `hook-anchoring-e2e`, and `plugin-load-e2e` already use for this exact class of bug, falling back to `args.paths` for direct/manual invocation.

`retrospective-policy` also moved from the `parallel: true` fast-stage group into the `piped: true` stdin group in `lefthook.yml`, per `ci-scripts.md` MUST-21: a stdin consumer in a parallel group races the shared stream under Lefthook 2.1.10.

## Live confirmation

This branch's own first push attempt exercised exactly the scenario the fix targets: `{push_files}` empty on first push. The pre-push log for that attempt showed `✔️ retrospective-policy (0.28 seconds)` passing cleanly, in a run where `{push_files}` would have been empty under the pre-fix behavior. This is a real reproduction of the bug's trigger condition, not only a unit-test simulation.

## Evidence

```text
$ uv run --frozen python -m pytest tests/test_lefthook_integration.py tests/ci/test_lefthook_prepush_fast_fail.py tests/ci/test_lefthook_prepush_fast_fail_runtime.py tests/test_investigation_allowlist.py tests/workflows/test_aggregator_cancellation_guard.py -q
946 passed, 1 skipped in 34.88s
```

## Scope

`scripts/validation/git_hook_policy.py`, `lefthook.yml`, `tests/ci/test_lefthook_prepush_fast_fail.py`, `tests/test_lefthook_integration.py`. No production runtime code outside the CI/validation surface; no security-relevant change (adjusts which local pre-push jobs run and how they derive their input, not what they enforce).
