---
qaVerdict: PASS
qaSessionLog: .agents/sessions/2026-08-10-session-14653-pr-4828-vendor-provenance-qa.json
qaCommit: 05f3d4230acc58a3597a20b6150d691d51f40736
---

# PR #4828 Vendor Provenance Review Fixes QA

## Scope

PR #4828 changes these files:

- `.github/workflows/vendor-provenance.yml`
- `scripts/ci/validate_vendor_provenance.py`
- `tests/ci/test_validate_vendor_provenance.py`

## Evidence

- Reverted `909c82fe8a309218887a65a21e981ad1f4882c5b` with commit `d02c8eb099fd1b248c948836e3d598fa922443ee`, then merged fresh `origin/main` with commit `5c8f5117b46f6370bf57888cc0aabff5873c6e4d`.
- Scope policy measured 3 files after the revert and main merge.
- GitHub PR files API returned exactly the three files listed above.
- Commit `b203a9e8c8f77f14171949207c78943f519ac99a` fixes PyYAML production execution by installing uv and running the validator with `uv run --frozen python`.
- Commit `15a6e00a8947a4ece7ab42702fb5c18bf1820ce8` replaces `git archive` with `materialize_tree`, so candidate `.gitattributes export-ignore` cannot hide files from validation.
- Commit `9caf8bd5267d590866e69819627a5dac35425f33` adds `_validate_manifest_tree`, which compares every `INTEGRITY.json` file hash, symlink target, executable mode, missing entry, and extra entry against the reconstructed vendor tree. Before this commit only the cli2 entrypoint hash was checked, so a candidate could swap a different dependency and still pass.
- Commit `3fd93cbdf1cad38d4cfb26596b85961893df2362` adds `TestCandidateMaterialization::test_export_ignored_vendor_file_reaches_the_gate`, a regression test that marks a vendor file `export-ignore` in the candidate, witnesses that `git archive` drops it, and asserts `materialize_tree` still produces it.
- Commit `05f3d4230acc58a3597a20b6150d691d51f40736` records the emitted required status check context (`Validate Vendor Provenance`, the job `name:`) in the workflow header and pins it to the job name with `TestWorkflowContract::test_required_check_context_matches_job_name`. The rollout instruction previously named the workflow `name:`, which GitHub never emits as a context.
- Commit `cd8f258a0b780c960c864872715881767bf585ef` merges `origin/main` at `dc41edcb201baa0bb1da2b94e5ff87b0cff2e921` so the ruff count baseline matches current main (30 to 27); the required `Run Python Tests` job compares the baseline against freshly fetched main.

## Tests Run

- `uv run --frozen python -m pytest tests/ci/test_validate_vendor_provenance.py -q`, 50 passed.
- `uv run --frozen python -m pytest tests/ci/test_validate_vendor_provenance.py tests/ci/test_merge_tree_materialization.py tests/test_pr_autofix_late_live_state_gate.py -q`, 86 passed.
- `uv run --frozen mypy scripts/ci/validate_vendor_provenance.py`, success.
- `uv run --frozen ruff check scripts/ci/validate_vendor_provenance.py tests/ci/test_validate_vendor_provenance.py`, passed.
- `uv run --frozen python -m py_compile scripts/ci/validate_vendor_provenance.py`, passed.
- `git diff --check`, passed.
- `uv run --frozen python scripts/validation/pre_pr.py`, 50 passed, 0 failed.

## Result

QA passed for the vendor provenance review fixes at local commit `05f3d4230acc58a3597a20b6150d691d51f40736`.
