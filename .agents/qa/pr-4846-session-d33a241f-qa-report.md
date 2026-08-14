---
qaVerdict: PASS
qaSessionLog: .agents/sessions/2026-08-11-session-14653-b0d6e4079-fix-4846-vendor-provenance-review.json
qaCommit: 36e52fe607250cf8fb66035eeb5b1ac5e683b0b9
---

# QA Report: PR #4846 vendor provenance autofix (updated)

## Summary

Validated the branch at commit `36e52fe607250cf8fb66035eeb5b1ac5e683b0b9`
(qaCommit, above). The previous report's PASS evidence was stale: it named
`qaCommit: 1556cdbd99...` but its prose and test run described commit
`63a2f9fd4...`, several commits earlier, so the recorded results did not
establish the verdict for the SHA the frontmatter claimed. This report
re-runs every check against the actual `qaCommit` SHA and lists every
content commit since the last commit both prose and frontmatter agreed on
(`3d96506c5`, "refactor(ci): move gitlink and check-run logic to Python
per ADR-006").

## Test Results

| Command | Result |
|---------|--------|
| `uv run pytest tests/ci/test_validate_vendor_provenance.py -q` | 198 passed |
| `uv run pytest tests/workflows/test_workflow_jobs_check_out_repo.py -q` | 145 passed |
| `uv run ruff check scripts/ci/validate_vendor_provenance.py tests/ci/test_validate_vendor_provenance.py tests/workflows/test_workflow_jobs_check_out_repo.py` | All checks passed |
| `actionlint .github/workflows/vendor-provenance.yml` | No findings |
| YAML syntax validation | Passed |

## Changes Since Previous QA Report

Content commits landed between `3d96506c5` (last commit the prior report's
prose and frontmatter agreed on) and `36e52fe60` (this report's `qaCommit`):

1. `57cd644f6` fix(ci): sort test imports (ruff I001)
2. `d1f7d44a5` fix(security): use NUL-delimited git ls-tree for gitlink rejection
3. `81fac520c` fix(ci): add encoding='utf-8' to subprocess text capture
4. `e2929a7b2` fix(ci): fetch full history for immutable SHAs
5. `22610337d` fix(ci): add errors='replace' to subprocess encoding
6. `8f60289a9` fix(ci): use gh api directly for check-run publication
7. `09a7f9c0f` fix(ci): shrink check-run step to pass ADR-006 ratchet
8. `1a5fefb6a` fix(ci): remove gh api fallback to comply with ADR-006
9. `1556cdbd9` fix(ci): add explicit permissions block to provenance job
10. `36e52fe60` fix(ci): parse checkout-index in order, not as a substring

## Correctness Assessment

The workflow uses immutable event SHAs and base-owned validation code.
Gitlink bypass is caught at the git tree object level (NUL-delimited
`git ls-tree`, commit 2) before filesystem materialization. Subprocess
text capture is explicit about encoding and decode-error handling
(commits 3, 5), and the base/candidate fetch pulls full history so
immutable-SHA lookups do not fail against a shallow clone (commit 4).
Check-run publication runs through `gh api` directly (commit 6), shrunk
to pass the ADR-006 step-size ratchet (commit 7) with the earlier
inline-YAML fallback removed (commit 8) and an explicit job
`permissions` block added (commit 9), so branch protection gates on the
PR head commit without relying on default token scopes. The
workflow-job checkout-dependency test itself no longer trusts a
substring match: it now tokenizes each run-block line in execution order
and skips printing/comment lines before treating a `git checkout-index`
mention as a real checkout (commit 10), closing the false-positive this
report's predecessor was flagged for.

## Verdict

**Status**: PASS
