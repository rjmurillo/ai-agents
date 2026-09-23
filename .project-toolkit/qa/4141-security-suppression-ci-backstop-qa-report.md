# QA Report: PR #4141 - Security Suppression CI Backstop (issue #4061)

## Objective

Verify that the new `security-suppressions-diff` subcommand and CI steps correctly
block net-new security suppressions introduced via non-hook paths (web-UI edits,
bot commits, `--no-verify` pushes).

- **Issues**: #4061
- **Scope**: `scripts/validation/git_hook_policy.py`, `.github/workflows/pytest.yml`,
  `tests/validation/test_git_hook_policy_causal_restore.py`
- **Acceptance criteria**: The new CI step blocks new `nosec`/`noqa: S*` suppressions
  and permits clean diffs, moves, and non-security noqa.

## Approach

- Added `TestSuppressionDiff` class (9 tests) and helper `_run_suppression_diff`.
- Added `_commit_text_for_base` to distinguish "file not in base" (new file, rc=0)
  from "invalid ref" (external error, rc=3); 4 additional tests + 2/2 mutants killed.
- Verified both directions: gate blocks what it must block; gate permits what it must permit.

## Results

### Summary

| Metric | Value | Target | Status |
|--------|-------|--------|--------|
| TestSuppressionDiff tests | 13/13 passed | 0 failures | PASS |
| Full suppression test set | 71/71 passed | 0 failures | PASS |
| Mutation harness (rc=3 path) | 2/2 killed | all killed | PASS |
| Ruff count ratchet vs main | OK (count == baseline 331) | no regression | PASS |
| Taste count ratchet vs main | OK (count == baseline 611) | no regression | PASS |
| Conflicts vs origin/main | none | no conflicts | PASS |

### Evidence

| Command | Result |
|---------|--------|
| `uv run --frozen python -m pytest tests/validation/test_git_hook_policy_causal_restore.py -q -k "suppress or Suppress or commit_text_for_base"` | 71 passed in 1.82s |
| `uv run --frozen ruff check scripts/validation/git_hook_policy.py` | All checks passed |
| `uv run --frozen ruff check tests/validation/test_git_hook_policy_causal_restore.py` | All checks passed |
| `uv run --frozen python scripts/ci/ruff_count_ratchet.py --base-ref origin/main` | ruff count ratchet: OK (count == baseline 331) |
| `uv run --frozen python scripts/ci/taste_count_ratchet.py --base-ref origin/main` | taste count ratchet: OK (count == baseline 611) |
| `git merge-tree --write-tree --name-only origin/main HEAD` | no output (no conflicts) |

### Mutation harness for `_commit_text_for_base` (2/2 killed)

| Mutant | Test that kills it | Status |
|--------|-------------------|--------|
| `return ''` instead of `return None` | `test_commit_text_for_base_returns_none_on_git_error` | KILLED |
| never match "does not exist in" | `test_commit_text_for_base_returns_empty_for_new_file` | KILLED |

### Two-directional gate verification

| Case | Expected | Actual |
|------|----------|--------|
| New `# nosec` in diff | rc=1 (blocked) | rc=1 |
| New `# noqa: S101` in diff | rc=1 (blocked) | rc=1 |
| Non-security `# noqa: E402` | rc=0 (permitted) | rc=0 |
| Pure rename of file with suppression | rc=0 (permitted) | rc=0 |
| Clean diff with no suppressions | rc=0 (permitted) | rc=0 |
| Non-.py extension in diff | rc=0 (permitted) | rc=0 |
| Invalid base_ref for notebook | rc=3 (external error) | rc=3 |
| New notebook (absent from base) | rc=0 (permitted) | rc=0 |

## Review thread resolutions

| Thread | Finding | Resolution |
|--------|---------|------------|
| PRRT_kwDOQoWRls6VjbJl | `_commit_text_or_empty` swallows git errors, returns rc=1 instead of rc=3 | Added `_commit_text_for_base`; 4 tests; 2/2 mutants killed |
| PRRT_kwDOQoWRls6VnSDl | paths-filter is Python-only; YAML/JS/PS1 noqa bypasses CI backstop | Added non-Python security suffixes to paths-filter |
