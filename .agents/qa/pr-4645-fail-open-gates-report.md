---
qaVerdict: PASS
qaSessionLog: .agents/sessions/2026-08-04-session-9102-fail-open-audit.json
qaCommit: 160b145de26026b849097f721da8fb3765a272c3
---

# PR #4645 fail-open gate closure validation

## Scope

Validation of the two fail-open fixes that remain in this PR's diff after the
base refresh at `919b4846796d3748bcfb163cb24db2967f2acf44`, bound to the
evidence commit `160b145de26026b849097f721da8fb3765a272c3`:

- `scripts/ci/check_codeql_sarif.py`
- `scripts/ci/spec_prepare_context.py`

The two other scripts named in the original description,
`scripts/ci/spec_extract_refs.py` and `scripts/ci/spec_load_content.py`,
landed on `main` in commit `4627d8482944dccad8e92e36f32dd9105ceec7ab`
("fix(ci): preserve extracted failure semantics", Issue #4068). They are byte
identical between `origin/main` and this branch, so they no longer appear in
the diff.

## Result

PASS.

## Behavior under test

`check_codeql_sarif.py` used to return 0 when the SARIF directory was absent or
held no `*.sarif` file, so a CodeQL run that produced nothing graded as clean.
It now returns 1 in that case, and also returns 1 when `load_documents` parses
fewer files than `find_sarif_files` discovered, which is the unparseable-SARIF
case. The caller in `.github/workflows/codeql-analysis.yml` line 239 runs only
when `check-paths.outputs.should-run-analysis == 'true'`, so an empty directory
there means the analysis failed rather than that nothing was scanned.

`spec_prepare_context.py` used to fall through to the literal
`"No spec content loaded"` context whenever `SPEC_FILE` was empty, missing, or
unreadable, which handed the AI reviewer an empty specification and let the
step exit 0. It now returns 2 for all three cases with a distinct
`::error::` message each. The caller in
`.github/workflows/ai-spec-validation.yml` line 142 runs only when
`spec-ref.outputs.has_specs == 'true'`, and the preceding
`spec_load_content.py` step is itself fail-closed on `main`, so an empty
`SPEC_FILE` at that point is a defect, not a supported no-spec PR.

## Evidence

All commands run in the worktree at the base refresh commit
`919b4846796d3748bcfb163cb24db2967f2acf44`, which is `origin/main` at
`e88f1d8d7a5c09fd6c55401e2961a19925073b7a` merged into the branch.

- `uv run --frozen pytest tests/ci/test_check_codeql_sarif.py tests/ci/test_spec_prepare_context.py -q`: 48 passed in 0.23s.
- `uv run --frozen pytest tests/ci/ -q`: 2285 passed, 9 skipped in 75.72s.
- `uv run --frozen ruff check scripts/ci/check_codeql_sarif.py scripts/ci/spec_prepare_context.py tests/ci/test_check_codeql_sarif.py tests/ci/test_spec_prepare_context.py`: all checks passed.
- `uv run --frozen python scripts/ci/ruff_ratchet.py`: passed for 4 changed Python files.
- `uv run --frozen python scripts/ci/ruff_count_ratchet.py --base-ref origin/main`: OK, 27 violations at or under baseline 30.
- `uv run --frozen python scripts/validation/git_hook_policy.py security-suppressions-diff --base-ref origin/main`: exit 0.
- `uv run --frozen python scripts/validation/validate_python_syntax.py`: exit 0.
- `uv run --frozen python scripts/validate_session_json.py .agents/sessions/2026-08-04-session-9102-fail-open-audit.json`: passed.

## CI failures this validation cleared

- Run Python Tests failed at the whole-tree ruff count ratchet with
  `BASELINE ABOVE BASE. This tree records 43, FETCH_HEAD records 30 (+13).`
  The branch carried a stale `scripts/ci/ruff_count_baseline.txt` from before
  `main` lowered the ceiling to 30. The base refresh took `main`'s value; the
  ratchet now reports `OK. 27 violations <= baseline 30`.
- Validate PR failed on two steps. The description named two files that are no
  longer in the diff, and `scripts/ci/check_pr_qa_report.py` found no QA report
  for a PR with code changes. This report and the description rewrite close
  both.

## Not verified

- No independent qa or critic agent reviewed this change. This is implementer
  self-validation.
- The fail-closed paths are proven by unit tests, not by an end-to-end
  CodeQL run with a corrupt SARIF artifact or an AI spec-validation run with an
  unreadable `SPEC_FILE`.
