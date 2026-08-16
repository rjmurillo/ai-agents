---
qaVerdict: PASS
qaSessionLog: .agents/sessions/2026-08-15-session-14713-bbf65f8b4-continue-4846-vendor-provenance-amendment.json
qaCommit: 4d6513c1a0733cd8e6fbb1d69f93b752d7dca2e8
---

# QA report: PR #4846 ADR-096 amendment

PASS for commit `4d6513c1a0733cd8e6fbb1d69f93b752d7dca2e8` on branch
`fix/vendor-provenance-bootstrap-v2`.

## What was validated

The amendment preserves repository-wide gitlink rejection, records hosted
runner tools as platform trust roots, and detects dependencies after compact
shell operators.

## Evidence

- `uv run pytest -q tests/ci/test_validate_vendor_provenance.py`: 232 passed.
- `uv run pytest -q tests/workflows/test_workflow_jobs_check_out_repo.py`:
  198 passed.
- Ruff passed for both modified test files.
- Actionlint passed for `.github/workflows/vendor-provenance.yml`.
- `scripts/validate_workflows.py` passed with existing line-count warnings.
- Taste count ratchet passed at baseline 583.
- ADR change detector exited 0 and reported ADR-096 modified.
- ADR review policy gate exited 0 after six amendment ACCEPT votes.
- Literal-path markdownlint checked both ADR files with zero issues.
- Node.js is pinned to reviewed release `24.19.0`, and the version assertion
  passes in the 228-test provenance suite.
- `git read-tree` dry runs do not mark an index populated. `--index-output`
  records only its actual output index.
- Cancelled predecessor runs skip both check-run creation and final head-state
  publication, so replacements own the current verdict.
- Head-state writes reject a lower run ID after a newer generation claims the
  same PR head.
- `uv run pytest -q tests/test_lefthook_integration.py -k
  placeholder_identity`: 7 passed. Commits already reachable from authenticated
  origin tips are excluded, local fake refs are ignored, and new placeholder
  identities remain blocked.
- Merge queue runs fetch both immutable SHAs before materialization.
- `|&`, multiline control flow, and heredoc text cannot hide an unmet
  repository dependency.
- A run-token pending status is attempted before the immutable fetch. API
  failure continues to the retried dual-channel startup.
- Bootstrap pending status is pull-request-only, so merge-group runs cannot
  leave a same-named status pending.
- Only authenticated remote tips already present in the local object database
  are excluded from identity scanning.
- Trusted update authorization requires immutable author and sender user ID
  `6811113`; mutable login names are not used.
- Bootstrap pending publication uses three bounded attempts before the retried
  dual-channel startup.
- The privileged workflow does not subscribe to `merge_group`; ADR-096
  requires a separate base-owned merge queue design.
- Markdownlint policy rejects config symlinks before any stat or read.
- Brace groups, subshells, functions, and backslash-newline continuations
  cannot hide repository dependencies.
- Every checkout-index materialization uses `--no-filter`, so candidate
  `.gitattributes` cannot invoke smudge filters or transform hashed bytes.

## Scope

This report covers the ADR amendment and final review regressions. PR-level
remote checks and current-head review remain part of the PR completion gate.
