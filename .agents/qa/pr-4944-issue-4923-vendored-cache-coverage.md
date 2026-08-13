---
qaVerdict: PASS
qaSessionLog: .agents/sessions/2026-08-12-session-14695-b6330b9ad-ship-missing-vendored-cache-exclusion.json
qaCommit: c8336cc377a0579bb85e2024f7d6ab2bb4d37c07
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
- The helper test covers nested package caches at the reported failure depth.
- The active review findings were resolved and session evidence validated.
- Ruff passed on the changed Python file.
- GPT-5.6 Sol found no actionable issue in the focused branch diff.

## Scope

The change adds one regression test. Runtime and fixture implementation code
are unchanged from merged PR #4935.
