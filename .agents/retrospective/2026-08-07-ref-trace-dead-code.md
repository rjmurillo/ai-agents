# Ref Trace Dead Code Retrospective

## Failure mode

False completion markers. Tests asserted that synthetic ref-trace lines parsed, but did not prove production could emit those lines. The parser stayed covered after the guard began removing `GIT_TRACE_REFS`.

## Evidence

| Area | Severity | Evidence |
|------|----------|----------|
| Root `conftest.py` HEAD guard | Medium | Issue #4700. Commit 98bd00264 removes unreachable parser branches. |
| Test suite signal | Medium | `tests/test_pytest_head_guard.py` created transaction and `create_symref` lines directly. |
| Git compatibility note | Low | `tests/validation/test_git_hook_policy_causal_restore.py` had stale prose saying the guard exported `GIT_TRACE_REFS`. |

## Timeline

1. The head guard once parsed ref transaction trace lines.
2. The guard later blocked `GIT_TRACE_REFS` to avoid a git 2.43 branch point failure.
3. Synthetic tests kept feeding those blocked line shapes to the parser.
4. Coverage stayed green, but production reachability was gone.

## Root cause

The tests checked parser capability instead of runtime reachability. The contract under test was not the contract the fixture could execute.

## Remediation

- Removed the unreachable transaction and symref parser branches in commit 98bd00264.
- Removed synthetic-only cases that fed those branches.
- Kept reachable Trace2 `symbolic-ref` argv parsing and proved it with `test_trace_parses_actual_symbolic_ref_write`.
- Added `test_guard_fixture_fails_for_real_test_launched_head_movement` to prove real HEAD movement is still attributed by reflog action.
- Corrected the stale git 2.43 comment so future readers keep the trace block instead of reviving dead parser logic.
