---
qaVerdict: PASS
qaSessionLog: .agents/sessions/2026-08-13-session-14704-b664c5c25-autofix-4934-dorny-paths-filter-merge.json
qaCommit: 1946b0909fdcbb91adb947357f09d75e5bb6870b
---

# QA Report: PR 4934 dorny/paths-filter

## Scope

Validated the `dorny/paths-filter` v4.0.3 action update and its matcher model
pin at commit `1946b0909fdcbb91adb947357f09d75e5bb6870b`.

## Evidence

- `src/filter.ts` at
  `ceb8a2b8f2d89434be7ff52d3de7ec3738c5cc9d` still sets
  `MatchOptions.dot` to `true`.
- `uv run pytest tests/ci/test_pytest_paths_filter_covers_episodes.py -q`
  passed all 21 tests.
- `uv run ruff check tests/ci/test_pytest_paths_filter_covers_episodes.py`
  passed.
- Pre-push Python tests passed in 662.89 seconds.
- Safe push verified remote head
  `1946b0909fdcbb91adb947357f09d75e5bb6870b`.
- PR #4934 has zero review threads.

## Verdict

PASS. The model pin matches the action SHA. No QA finding remains.
