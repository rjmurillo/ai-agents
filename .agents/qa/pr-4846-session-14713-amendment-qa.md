---
qaVerdict: PASS
qaSessionLog: .agents/sessions/2026-08-15-session-14713-bbf65f8b4-continue-4846-vendor-provenance-amendment.json
qaCommit: 1f3a6222bfb45332757ad1bad2e5a5a4a0f46bd9
---

# QA report: PR #4846 ADR-096 amendment

PASS for commit `1f3a6222bfb45332757ad1bad2e5a5a4a0f46bd9` on branch
`fix/vendor-provenance-bootstrap-v2`.

## What was validated

The amendment preserves repository-wide gitlink rejection, records hosted
runner tools as platform trust roots, and detects dependencies after compact
shell operators.

## Evidence

- `uv run pytest -q tests/ci/test_validate_vendor_provenance.py`: 228 passed.
- `uv run pytest -q tests/workflows/test_workflow_jobs_check_out_repo.py`:
  185 passed.
- Ruff passed for both modified test files.
- Actionlint passed for `.github/workflows/vendor-provenance.yml`.
- `scripts/validate_workflows.py` passed with existing line-count warnings.
- Taste count ratchet passed at baseline 583.
- ADR change detector exited 0 and reported ADR-096 modified.
- ADR review policy gate exited 0 after six amendment ACCEPT votes.
- Literal-path markdownlint checked both ADR files with zero issues.
- Node.js is pinned to reviewed release `24.19.0`, and the version assertion
  passes in the 228-test provenance suite.

## Scope

This report covers the ADR amendment and its two regression tests. PR-level
remote checks and current-head review remain part of the PR completion gate.
