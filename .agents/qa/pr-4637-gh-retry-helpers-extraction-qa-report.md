---
qaVerdict: PASS
qaSessionLog: .agents/sessions/2026-08-11-session-3310a37d-pr-4637-qa.json
qaCommit: 77f1a929823a5860904f4857627a2ea3e316bd1e
---

# QA Report: GH Retry Helpers Extraction (PR #4637)

## Scope

- PR: #4637
- Branch: `fix/4597-3275-split-and-smoke`
- QA commit: `77f1a929823a5860904f4857627a2ea3e316bd1e`
- Session log: `.agents/sessions/2026-08-11-session-3310a37d-pr-4637-qa.json`
- Refresh reason: required `Validate PR` failed after the merge-to-main CI fix because the
  previous QA report was still bound to commit `80236b38509475b55a2308ae1f91b68cf8ee968f`, and the
  final pre-push pass also needed a one-line mypy-safe return cast in
  `scripts/ci/build_ai_review_context.py`.

## Code paths checked

- `scripts/ci/build_ai_review_context.py`
- `scripts/gh_retry_helpers.py`
- `tests/test_build_ai_review_context.py`
- `tests/test_build_ai_review_context_split.py`
- `scripts/ci/subprocess_encoding_count_baseline.txt`
- `scripts/ci/taste_count_baseline.txt`

## Validation evidence

| Command | Result |
|---|---|
| `uv run --frozen pytest tests/test_build_ai_review_context_split.py` | PASS, 11 passed |
| `uv run --frozen pytest tests/test_build_ai_review_context.py tests/ci/test_ci_scripts_are_wired.py tests/ci/test_failure_classification.py` | PASS |
| `uv run --frozen mypy scripts/ci/build_ai_review_context.py` | PASS |
| `uv run --frozen python scripts/ci/subprocess_encoding_count_ratchet.py --base-ref origin/main` | PASS, `count == baseline 238` |
| `uv run --frozen python scripts/ci/taste_count_ratchet.py --base-ref origin/main` | PASS, `count == baseline 583` |
| `uv run --frozen python scripts/ci/merge_tree_ratchet_check.py --base-ref origin/main` | PASS |
| `uv run --frozen pytest tests/ci/test_count_ratchet_against_real_git.py -k taste_count_baseline` | PASS, `1 passed` |

## Assessment

1. The blocking split request on `scripts/ci/build_ai_review_context.py` is already satisfied on the
   validated commit: GH retry helpers live in `scripts/gh_retry_helpers.py`, and the entrypoint stays
   under the taste-lint file-size cap.
2. Merging current `origin/main` was required to pick up the lowered subprocess-encoding baseline that
   the `Run Python Tests` gate compares against.
3. The follow-up test change in `tests/test_build_ai_review_context_split.py` now fails closed on
   unexpected subprocess launches instead of forwarding `subprocess.run(**kwargs)` through the scanner's
   over-approximation path.
4. The refresh also restores the taste-count baseline to the current `origin/main` ceiling and marks
   the legacy `tests/test_build_ai_review_context.py` harness with a scoped `file-size` explanation so
   the ratchet reflects actual net debt instead of stale report drift.

## Verdict

PASS. The validated PR head `77f1a929823a5860904f4857627a2ea3e316bd1e` preserves the split, fixes the CI
ratchet regressions, satisfies the changed-file mypy gate, and is now backed by current QA evidence.
