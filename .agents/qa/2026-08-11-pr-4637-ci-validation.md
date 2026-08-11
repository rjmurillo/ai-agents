---
qaVerdict: PASS
qaSessionLog: .agents/sessions/2026-08-05-session-2.json
qaCommit: bba2a7b1e2599d342bf092e884fb076fe4520503
---

# QA Report: PR #4637 CI validation

## Binding

- PR: #4637
- Branch: `fix/4597-3275-split-and-smoke`
- PR head diagnosed: `0ded1670a456aa1781c386161007616dfd15bf6c`
- Diagnosed base: `d4cc52d5de0c11f7d36c99a246484f1f192ce584`
- Refreshed main: `5588065212312c04912c0a520e4fcb8f581037bf`
- Code-under-test commit: `bba2a7b1e2599d342bf092e884fb076fe4520503`

The report and session update are evidence-only changes. The QA commit above is
the last code-affecting commit and must remain an ancestor of the final PR head.

## Root-cause verification

| Check | Root cause | Resolution |
|---|---|---|
| Validate PR | The branch had code changes but no matching `*pr-4637*.md` QA report. | Added this report with strict session and commit binding. |
| Validate Spec Coverage | The branch had neither the taste-baseline evidence nor the issue's named failure-classification seam. | Lowered the baseline from 583 to 582 and extracted the typed failure-classification module. |
| Run Python Tests | The logged 464-byte instruction-corpus delta is not branch-owned at the bound base. | No claimed byte figures were edited. The branch changes none of the measured instruction inputs, and the focused corpus suites pass. |

The base version of `scripts/ci/build_ai_review_context.py` is 803 lines and the
branch version is 754 lines. The remaining size above the historical 500-line
issue context comes from the merged base, so this CI repair does not add an
unrelated second refactor.

## Evidence

| Command | Result |
|---|---|
| `uv run --frozen python scripts/ci/taste_count_ratchet.py --base-ref 5588065212312c04912c0a520e4fcb8f581037bf` | PASS; count equals lowered baseline 582 |
| `uv run --frozen python scripts/ci/ruff_count_ratchet.py --base-ref 5588065212312c04912c0a520e4fcb8f581037bf` | PASS; count equals baseline 27 |
| `uv run --frozen pytest tests/ci/test_taste_count_ratchet.py -q` | PASS; 28 tests covering success, failure, and edge behavior |
| `uv run --frozen pytest tests/ci/test_failure_classification.py tests/test_build_ai_review_context.py tests/test_build_ai_review_context_split.py -q` | PASS; 123 tests covering the named seam and integration behavior |
| `uv run --frozen pytest tests/test_build_ai_review_context.py tests/test_build_ai_review_context_split.py -q` | PASS; 99 tests |
| `uv run --frozen pytest tests/validation/test_always_on_corpus_claims.py tests/validation/test_instruction_budget.py -q` | PASS; 123 tests |
| `uv run --frozen pytest tests/ci/test_spec_extract_refs.py tests/ci/test_spec_load_content.py tests/ci/test_spec_prepare_context.py tests/test_check_spec_failures.py tests/test_generate_spec_report.py -q` | PASS; 74 tests |
| `uv run --frozen ruff check scripts/ai_review_outputs.py scripts/ci/build_ai_review_context.py tests/test_build_ai_review_context_split.py` | PASS |
| `uv run --frozen mypy scripts/ai_review_outputs.py scripts/ci/failure_classification.py scripts/ci/build_ai_review_context.py` | PASS |
| `git diff --quiet d4cc52d5de0c11f7d36c99a246484f1f192ce584..0ded1670a456aa1781c386161007616dfd15bf6c -- .claude/rules .github/instructions src/copilot-cli/instructions tests/validation/test_always_on_corpus_claims.py tests/validation/test_instruction_budget.py` | PASS; no branch-owned instruction-input changes |

## Pre-PR note

The first full pre-push run selected a moving `origin/main` and exposed three
unrelated repository-wide test failures. After merging refreshed main at
`5588065212312c04912c0a520e4fcb8f581037bf`, those three exact tests pass. The
taste baseline remains a net improvement over main, falling from 583 to 582.
