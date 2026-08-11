---
qaVerdict: PASS
qaSessionLog: .agents/sessions/2026-08-11-session-14681.json
qaCommit: 8f18242df9c025af6e08e751a897dd93c9d093cd
---

# PR 4873 credentialed GitHub remote validation

## Result

PASS. The branch code is covered by the focused GitHub-core suite, generated
mirrors match their canonical source, and the sole CI failure was the absence
of this required QA evidence.

## CI root cause

`Validate PR` failed in `scripts/ci/check_pr_qa_report.py` with:

```text
No QA report found for code changes
```

The gate is correct because PR 4873 changes Python code. No compile, lint, or
test failure was present in the fetched CI logs.

## Scope validated

Commit `8f18242df9c025af6e08e751a897dd93c9d093cd` updates GitHub remote parsing in
the canonical library and its two generated mirrors. It accepts URI schemes
such as `git+ssh` and optional user information while retaining the exact
`github.com` host requirement. The focused suite covers the added credentialed
HTTPS and `git+ssh` cases alongside existing invalid-host cases.

## Evidence

- `uv run pytest -q tests/test_github_core.py`: 253 passed, with one existing
  pagination warning.
- `uv run python build/scripts/build_all.py --check`: exit 0; generated files
  remained unchanged.
- `git status --short --branch` after validation: clean dedicated PR worktree.

## Scope not covered

The full repository test suite was not run manually. Repository commit and
push hooks remain authoritative for the broader suite; this report records the
focused validation appropriate to the four-file parser change.
