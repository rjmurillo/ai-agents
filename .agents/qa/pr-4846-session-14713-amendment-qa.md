---
qaVerdict: PASS
qaSessionLog: .agents/sessions/2026-08-15-session-14713-bbf65f8b4-continue-4846-vendor-provenance-amendment.json
qaCommit: b7f4caae2d5445af9c1d168bccb21237bc74d5f3
---

# QA report: PR #4846 ADR-096 amendment

PASS for commit `b7f4caae2d5445af9c1d168bccb21237bc74d5f3` on branch
`fix/vendor-provenance-bootstrap-v2`.

## What was validated

The amendment preserves repository-wide gitlink rejection, records hosted
runner tools as platform trust roots, and detects dependencies after compact
shell operators.

## Evidence

- `uv run pytest -q tests/ci/test_validate_vendor_provenance.py`: 228 passed.
- `uv run pytest -q tests/workflows/test_workflow_jobs_check_out_repo.py`:
  189 passed.
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

## Scope

This report covers the ADR amendment and its two regression tests. PR-level
remote checks and current-head review remain part of the PR completion gate.
