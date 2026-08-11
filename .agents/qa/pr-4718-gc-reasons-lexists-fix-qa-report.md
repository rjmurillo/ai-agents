---
qaVerdict: PASS
qaSessionLog: .agents/sessions/2026-08-10-session-10035-bfffb0de4-create-report-4718-worktree-changes.json
qaCommit: 3722ace753ca0a78690a67265aac7b173d6fd037
---

# QA Report: _path_confirmed_absent fix (PR #4718)

## Summary

Validates the new `_path_confirmed_absent` helper in `scripts/maintenance/_gc_reasons.py` and its regression tests in `tests/test_gc_stale_probes.py::TestPathConfirmedAbsent`. The fix replaces a bare `os.path.lexists()` call that conflated "permission denied" with "absent", printing destructive removal advice for occupied-but-unreadable paths.

## Test Results

| Metric | Value |
|--------|-------|
| Tests run | 274 |
| Passed | 274 |
| Failed | 0 |
| Duration | 9.61s |

Status: [PASS]

## Ruff

`ruff check` on both files: all checks passed, zero findings.

Status: [PASS]

## Ratchet

`subprocess_encoding_count_ratchet.py` reports OK at baseline 238.

Status: [PASS]

## Correctness Assessment

The `_path_confirmed_absent` function calls `os.lstat(path)`:

- `FileNotFoundError` raised - returns `True` (confirmed absent).
- Any other `OSError` (e.g. `PermissionError`) - returns `False` (not confirmed absent).
- Successful stat (path exists) - returns `False`.

`stale_keep_reason` assigns `KEEP_STALE` (which includes `git worktree remove` advice) only when `_path_confirmed_absent` returns `True`. Otherwise it assigns `KEEP_STALE_OCCUPIED` (no removal command printed). This is the correct polarity and fully addresses the Copilot review comment about `os.path.lexists()` masking `PermissionError` as absence.

The four new test cases in `TestPathConfirmedAbsent` cover: existing path, genuinely missing path, real permission-denied path (with skip on root/Windows), and mocked `OSError` via patched `os.lstat`. The orchestrator confirmed mutation-proofing (reverting to old logic causes the two OSError tests to fail).

## Residual Risks (non-blocking)

1. The permission-denied test (`test_a_permission_denied_path_is_not_confirmed_absent`) is skipped when running as root or on Windows. CI runners that execute as root will not exercise this path with a real filesystem barrier. The mocked variant (`test_a_stat_failure_is_not_confirmed_absent`) covers the logic unconditionally.
2. `os.lstat` can raise non-OSError exceptions (e.g. `TypeError` on non-string input), but callers always pass `worktree.path` which is always a string, so this is not a practical concern.

## Verdict

```
Promised: Fix _path_confirmed_absent to distinguish FileNotFoundError from other OSError; regression tests; ratchet baseline update 253->238
Delivered: _path_confirmed_absent helper with correct logic; 4 new tests in TestPathConfirmedAbsent; baseline at 238
Gap: None
Result: PASS
```

**Status**: PASS
**Confidence**: High
**Rationale**: All 274 tests pass, linting clean, ratchet OK, logic is sound and directly addresses the review comment.
