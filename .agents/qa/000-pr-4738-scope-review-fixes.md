---
qaVerdict: PASS
qaSessionLog: .agents/sessions/2026-08-10-session-10035-b22ab92ed-address-4738-scope-review-threads.json
qaCommit: b58d3c91fff9c30ddf6199c79af00bdb38674f06
---
# Test Report: PR #4738 scope base review fixes

## Scope

Fixed review threads on `fix/scope-gate-stacked-base`. The code now preserves
the original blocking result when stacked-base remeasurement raises
`ScopeDetectionError`, when the ancestry check times out, and when `git` cannot
start. The docstring citation and credibility tests match the current exception
contract.

## Validation

| Command | Result |
|---------|--------|
| `uv run --frozen pytest tests/test_scope_pr_base_real_git.py tests/test_scope_pr_base_credibility.py tests/test_detect_scope_explosion.py tests/ci/test_pr_validation_workflow.py -q` | 171 passed |
| `uv run --frozen pytest -m windows_path -q` | 1027 passed, 3 skipped, 24535 deselected |
| `uv run --frozen pytest tests/test_detect_scope_explosion.py::TestIsAncestor -q` | 4 passed |
| `uv run --frozen ruff check scripts/detect_scope_explosion.py scripts/scope_pr_base.py tests/test_scope_pr_base_credibility.py tests/test_detect_scope_explosion.py` | passed |

## Threads addressed

1. `scripts/detect_scope_explosion.py` catches `ScopeDetectionError` in
   `rescope_against_pr_base()` and returns `None` on remeasurement failure.
2. `scripts/scope_pr_base.py` and `tests/test_scope_pr_base_credibility.py`
   cite the current `ScopeDetectionError` branch instead of the removed
   `return []` contract.
3. `is_ancestor()` catches `subprocess.TimeoutExpired` and `OSError`, returning
   `False` so credibility refusal keeps the original block.

## Verdict

PASS. The stacked-base fallback now fails closed, the citation contract matches
current production code, and the targeted scope and Windows path suites pass
locally.
