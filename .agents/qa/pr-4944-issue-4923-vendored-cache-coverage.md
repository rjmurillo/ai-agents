---
qaVerdict: PASS
qaSessionLog: .agents/sessions/2026-08-13-session-14696-b6330b9ad-complete-4944-vendored-pycache-coverage.json
qaCommit: 5d6c4fc4dd2cd0693862b09824181f6385937650
---

# PR 4944 vendored cache exclusion coverage

## Result

PASS. The shared vendored copy helper now has direct regression coverage for
every configured cache exclusion.

## Evidence

- Vendored fixture suites passed 20 tests with 1 real-CLI test skipped.
- The helper test covers `__pycache__`, `*.pyc`, `*.pyo`, `.pytest_cache`,
  `.ruff_cache`, and `.mypy_cache`.
- The helper test proves tracked Python files still copy.
- Ruff passed on the changed Python file.
- GPT-5.6 Sol found no actionable issue in the focused branch diff.

## Scope

The change adds one regression test. Runtime and fixture implementation code
are unchanged from merged PR #4935.
