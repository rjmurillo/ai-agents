---
qaVerdict: PASS
qaSessionLog: .agents/sessions/2026-08-12-session-14693-b9b72ddc3-fix-issue-4923-vendored-pycache.json
qaCommit: d82552f886014a95abc25a02c251b99008d3b21e
---

# Issue 4923 vendored copy validation

## Result

PASS. Both vendored plugin fixtures now share one cache-free copy boundary.
Tracked plugin files still copy. Mutable Python and test-tool caches do not.

## Evidence

- Vendored fixture suites passed 18 tests with 1 real-CLI test skipped.
- Ruff passed on all three changed Python files.
- Thirty consecutive stress runs passed.
- The focused suites passed again after merging current `main`.
- Two GPT-5.6 Sol review rounds completed. The final review found no issues.

## Scope

The change affects test fixture construction only. Product plugin artifacts and
runtime behavior are unchanged.
