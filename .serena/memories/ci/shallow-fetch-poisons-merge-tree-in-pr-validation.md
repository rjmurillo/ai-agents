# Shallow fetch poisons merge-tree in pr-validation

Issue #4572 measured a CI deadlock in `PR Validation / Validate PR`:
`Run merge-tree ratchet` failed with
`fatal: refusing to merge unrelated histories` after `.git/shallow` existed in
the job checkout.

Two routes create the same graft:

1. `actions/checkout` without `fetch-depth: 0` in the bot-skip leg.
2. Any earlier `git fetch --depth=1` in the same job before the merge-tree step.

A later plain `git fetch origin "$BASE_REF"` does not repair a shallow graft.
The fix keeps both checkout legs at full history and removes depth-limited
fetches before `Run merge-tree ratchet` in
`.github/workflows/pr-validation.yml`.

Regression guard: `tests/ci/test_pr_validation_workflow.py` asserts every
checkout in `validate-pr` uses `fetch-depth: 0`, no active `git fetch --depth`
appears before `Run merge-tree ratchet`, and the merge-tree step's own fetch
stays full-depth.
