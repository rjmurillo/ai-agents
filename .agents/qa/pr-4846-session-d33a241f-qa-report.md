---
qaVerdict: PASS
qaSessionLog: .agents/sessions/2026-08-11-session-14653-b0d6e4079-fix-4846-vendor-provenance-review.json
qaCommit: 24e624fa271e16cb12c0d3cfdae9df53e171ba94
---

# QA Report: PR #4846 vendor provenance autofix

## Summary

Validated the final branch against current `main`. The gate requires a trusted pull request author and event sender. It reruns for opened, reopened, synchronized, and edited events. Candidate pin data uses literal parsing. Markdownlint configuration rejects aliases, anchors, tags, unsafe extension keys, and files over 256 KiB.

## Test Results

| Command | Result |
|---------|--------|
| `uv run pytest tests/ci/test_validate_vendor_provenance.py tests/workflows/test_workflow_jobs_check_out_repo.py -q` | 301 passed |
| `uv run ruff check scripts/ci/validate_vendor_provenance.py tests/ci/test_validate_vendor_provenance.py` | Passed |
| `uv run ruff format --check scripts/ci/validate_vendor_provenance.py tests/ci/test_validate_vendor_provenance.py` | Passed |
| `actionlint .github/workflows/vendor-provenance.yml` | Passed |
| `uv run python scripts/validation/validate_python_syntax.py .` | Passed |
| Trusted author and sender validator run against current `main` | Passed |
| Untrusted sender negative control | Rejected with exit 1 |

## Correctness Assessment

The workflow uses immutable event SHAs and base-owned validation code. A malicious contributor cannot authorize an update by pushing to a trusted author's branch. YAML expansion and extension loading are rejected before parsing. Vendor executables remain pinned without treating package runtime files as standalone tools.

## Verdict

Promised: address current review blockers, update the branch, and restore merge readiness.

Delivered: trusted dual-identity authorization, literal candidate pin parsing, bounded YAML loading, partial vendor tree rejection, current `main`, the setup-uv v10 pin, 301 passing tests, and real validator evidence.

Gap: None found in tested scope.

**Status**: PASS
