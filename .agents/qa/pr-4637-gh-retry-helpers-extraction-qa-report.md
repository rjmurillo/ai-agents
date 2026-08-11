---
qaVerdict: PASS
qaSessionLog: .agents/sessions/2026-08-05-session-2.json
qaCommit: 80236b38509475b55a2308ae1f91b68cf8ee968f
---

# QA Report: GH Retry Helpers Extraction (PR #4637)

## Summary

Commit 80236b38 extracts GH CLI retry/invocation helpers from `scripts/ci/build_ai_review_context.py` into `scripts/gh_retry_helpers.py`. The main file drops from 729 to 496 lines, staying under the 500-line taste-lints cap. All extracted symbols are re-imported in the original module, preserving the public interface.

## Taste-Lints

```
[WARNING] authored file-size: scripts/ci/build_ai_review_context.py:496
  File approaching size limit (496/500 lines)

taste-lints: 2 files scanned, 0 error(s), 1 warning(s)
```

Result: [PASS] - 0 errors. Warning is non-blocking.

## Test Results

```
310 passed, 8 skipped in 5.26s
```

Test files executed:
- tests/test_build_ai_review_context_split.py
- tests/test_build_ai_review_context.py
- tests/ci/test_ci_scripts_are_wired.py
- tests/build_scripts/test_context_mode_enforcement.py

Result: [PASS]

## Ruff

```
All checks passed!
```

Result: [PASS]

## Correctness Assessment

1. **Behavior preservation**: The extraction is a pure move. All constants, dataclasses, exception classes, regex patterns, and functions (`_redact_secrets`, `_retry_delay`, `_invoke_gh_once`, `run_gh`, `_new_context_retry_deadline`, `_failure_text`, `_with_retry_exhausted`) retain identical logic. The main module re-imports every extracted name including the `_GH_RETRY_DEADLINE` ContextVar, so downstream code in the same file continues to work unchanged.

2. **Import mechanism**: The main file uses `from gh_retry_helpers import ...` (bare module name, not `scripts.gh_retry_helpers`). This works because the script prepends `scripts/` to `sys.path` via the existing `_REPO_ROOT / "scripts"` insertion at the top of `build_ai_review_context.py`. The new module itself also inserts `_REPO_ROOT` for its own `from scripts.redact_secrets import redact_ci_sink` dependency.

3. **No import cycles**: `gh_retry_helpers.py` depends only on `scripts.redact_secrets` (a leaf utility). `build_ai_review_context.py` imports from `gh_retry_helpers`. No cycle exists.

4. **Naming collisions**: The module name `gh_retry_helpers` is unique in the repo. No collision risk.

## Residual Observations (Non-Blocking)

- The main file is at 496/500 lines. Any future additions will require another extraction pass.
- Private names (prefixed `_`) are re-exported and used across module boundaries. Acceptable for an internal script, but not ideal for a library API.
- The `# noqa: F401` on the import block suppresses unused-import warnings for names that are consumed later in the file; this is correct but could confuse future linters if names are removed without updating the import list.

## Verdict

All gates pass. Extraction preserves behavior exactly with no regressions.
