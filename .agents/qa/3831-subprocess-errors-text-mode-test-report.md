# Test Report: Issue #3831 subprocess errors= text-mode guard

## Objective

Verify the subprocess codec guard catches captured `subprocess.run` calls where `errors=` alone enables text mode.

- **Feature**: Fixes #3831
- **Scope**: `tests/test_new_pr.py::TestCapturedOutputPinsItsCodec`
- **Acceptance Criteria**: `errors=` alone is reported; `errors=` with `encoding=` stays quiet.

## Approach

- Added a failing guard regression test for `capture_output=True, errors='ignore'`.
- Added a non-regression test for `capture_output=True, encoding='utf-8', errors='ignore'`.
- Updated the AST walker so `errors` counts as a text-mode decoder keyword.

## Results

### Summary

| Metric | Value | Target | Status |
|--------|-------|--------|--------|
| Regression reproduction | 1 failing test before fix | Required | [PASS] |
| Targeted test pass rate | 9/9 | 100% | [PASS] |
| File test pass rate | 60/60 | 100% | [PASS] |
| Related guard pass rate | 13/13 | 100% | [PASS] |
| Ruff | 1/1 file clean | 100% | [PASS] |
| Full suite | Timed out after 600s at 30%, no failures observed | Complete | [SKIP] |

### Evidence

| Command | Result | Status |
|---------|--------|--------|
| `uv run pytest tests/test_new_pr.py -q -k 'errors_alone_run_is_reported or errors_with_encoding_is_not_an_encoding_offender'` before fix | 1 failed, 1 passed | [PASS] |
| `uv run pytest tests/test_new_pr.py -q -k 'CapturedOutputPinsItsCodec'` | 9 passed | [PASS] |
| `uv run pytest tests/test_new_pr.py -q` | 60 passed | [PASS] |
| `uv run pytest tests/integration/test_e2e_install.py -q -k 'SubprocessDecoding'` | 13 passed | [PASS] |
| `uv run ruff check tests/test_new_pr.py` | All checks passed | [PASS] |
| `uv run pytest tests/ -q` | Timed out after 600s at 30%; no failures before timeout | [SKIP] |

## Coverage Gaps

| Gap | Reason | Priority |
|-----|--------|----------|
| Full local suite did not complete | Repository suite has 16,052 tests and exceeded the 600s foreground command cap | P2 |

## Verdict

**Status**: PASS
**Confidence**: Medium
**Rationale**: The regression fails before the fix, passes after the fix, and the affected guard suites pass. Full local suite did not complete within 600s.
