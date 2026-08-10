---
qaVerdict: PASS
qaSessionLog: .agents/sessions/2026-08-09-session-10023.json
qaCommit: 4278245402cc30b83d291956d75ef96a46fbd094
---

# PR 4747 QA Report

## Verdict

PASS. Local validation passed for the PR 4747 hook policy fix.

## Evidence

- Negative control without source fix: `2 failed, 812 deselected`. Both changed-content tests returned 0 instead of 1.
- Restored source fix: `2 passed, 812 deselected`.
- Targeted session policy tests: `9 passed, 805 deselected`.
- Hook policy suites: `1154 passed` in `tests/test_lefthook_integration.py` and `tests/test_validate_session_json.py`.
- Ruff changed files: `All checks passed!`.
- Mypy changed files: `Success: no issues found in 1 source file` for each changed file.
- Security review: no findings on `scripts/validation/git_hook_policy.py` or `tests/test_lefthook_integration.py`.
- Commit check: normal commit succeeded through pre-commit and commit-msg hooks.

## Scope

Covers the PR 4747 fail-open session-log validation thread. Pre-commit now compares staged index bytes to upstream default. Pre-push now compares HEAD bytes to upstream default. Changed or absent upstream content validates instead of skipping.

## Re-validation After Base Merge

- Merged `origin/main` cleanly into this branch at `ef2ec00094d0622a35eee198d971f929c5d5a76a`.
- Re-ran validation on `8220935232a1b6476ff4a90b6a175f27d9625284` after the QA report refresh.
- `uv run --frozen pytest tests/test_mutation_workspace_signals.py::test_concurrent_runs_use_distinct_markers_and_worktrees tests/test_lefthook_integration.py tests/test_validate_session_json.py -q` collected 1155 items and passed all 1155 in 49.98 seconds.


## Re-validation After Second Base Merge (2026-08-10)

- Merged `origin/main` into `docs/walk-the-gate` at `4278245402cc30b83d291956d75ef96a46fbd094`.
- Resolved 6 byte-count conflicts in canonical-source-mirror, model-context-doctrine, and always-on-membership docs by re-measuring the merged state: 8 rules = 73,362 bytes (.github/instructions), 73,497 bytes (.claude/rules/), effective .py context = 99,113 bytes across 11 files.
- `uv run --frozen pytest tests/test_lefthook_integration.py tests/test_validate_session_json.py tests/test_pr_autofix_lease.py -q` collected 1287 items and passed all 1287 in 64.34 seconds.
- `ruff check` on all changed Python files: All checks passed.
