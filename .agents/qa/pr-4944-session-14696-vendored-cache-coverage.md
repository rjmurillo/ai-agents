---
qaVerdict: PASS
qaSessionLog: .agents/sessions/2026-08-13-session-14696-b6330b9ad-complete-4944-vendored-pycache-coverage.json
qaCommit: 9093705a61a8c030d039cb29ee56605c133abcd3
---

# PR 4944 session 14696 vendored cache coverage

## Result

PASS. Focused validation passed on the post-merge evidence commit.

## Test Strategy

- Behavior: vendored builds exclude configured runtime caches while preserving required files.
- Negative cases: cache directories and compiled cache files must not enter vendored output.
- Minimum proof: focused integration and E2E suites, scoped Ruff, and `git diff --check`.

## Evidence

- Focused integration and E2E command: 20 passed and 1 expected real-CLI
  test skipped in 1.52 seconds.
- Ruff: all checks passed for `tests/integration/test_vendored_install.py`.
- Diff check: `git diff --check` passed with no output.
- Helper boundary: `git diff origin/main...HEAD --
  tests/lib/vendored_copy.py` was empty.

## Completeness

Promised: Post-merge focused validation and a unique session 14696 QA binding.
Delivered: Focused pytest, Ruff, diff, and helper-boundary checks passed. This
report binds session 14696 to the tested evidence commit.
Gap: None.
Result: PASS
