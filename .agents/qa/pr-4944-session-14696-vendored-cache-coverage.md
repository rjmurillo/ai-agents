---
qaVerdict: PASS
qaSessionLog: .agents/sessions/2026-08-13-session-14696-b6330b9ad-complete-4944-vendored-pycache-coverage.json
qaCommit: 18bb32f6330635631d004489ed8624a6cb7c6b32
---

# PR 4944 session 14696 vendored cache coverage

## Result

PASS. Focused validation passed on the post-merge HEAD.

## Test Strategy

- Behavior: vendored builds exclude configured runtime caches while preserving required files.
- Negative cases: cache directories and compiled cache files must not enter vendored output.
- Minimum proof: focused integration and E2E suites, scoped Ruff, and `git diff --check`.

## Evidence

- Integration: 12 passed in 2.36 seconds.
- E2E: 8 passed and the expected real-CLI test skipped in 0.78 seconds.
- Ruff: all checks passed for `tests/integration/test_vendored_install.py`.
- Diff check: `git diff --check` passed with no output.

## Completeness

Promised: Post-merge focused validation and a unique session 14696 QA binding.
Delivered: Four required checks passed; this report binds session 14696 to the full HEAD commit.
Gap: None.
Result: PASS
