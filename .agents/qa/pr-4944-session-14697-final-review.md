---
qaVerdict: PASS
qaSessionLog: .agents/sessions/2026-08-13-session-14697-b6330b9ad-resolve-final-4944-review-findings.json
qaCommit: 028fabd8ee0d04b3e4d8b87a042b304c427109b2
---

# PR 4944 Session 14697 Final Review QA

## Scope

Validated the initial post-merge evidence commit through focused tests and
evidence-boundary checks. Behavioral coverage targets recursive vendored
runtime-cache exclusion. Product code, tests, and the runtime helper are
unchanged from `origin/main`.

## Test Strategy

- Behavior: vendored installation excludes recursive runtime caches and keeps
  required package files.
- Negative cases: nested cache directories and `.pyc` or `.pyo` files must not
  enter vendored output.
- Minimum proof: focused integration and E2E suites, scoped Ruff, whitespace
  diff validation, empty helper diff, session validation, and explicit artifact
  Markdown lint.

## Evidence

- Focused integration and E2E command: 20 passed and 1 expected real-CLI
  test skipped in 1.52 seconds.
- Ruff: all checks passed for `tests/integration/test_vendored_install.py`.
- Diff check: `git diff --check` passed with no output.
- Helper boundary: `git diff origin/main...HEAD -- tests/lib/vendored_copy.py`
  was empty.
- Session creation validation and branch session policy passed.
- Automatic Markdown lint selected 0 of 4 ignored artifact targets and was
  recorded as NOT LINTED. Explicit no-ignore lint read 4 files with 0 issues.

## Worktree

The worktree was clean at `9093705a61a8c030d039cb29ee56605c133abcd3`.
No test command changed the worktree.

## Result

Promised: Focused validation and a session 14697-bound QA report.
Delivered: All focused checks passed, with 20 tests passed, 1 expected E2E
skip, and this uniquely bound report.
Gap: None for the requested focused validation scope.
Result: PASS

PASS. Focused validation passed on commit
`9093705a61a8c030d039cb29ee56605c133abcd3`.

## Re-verification after merging origin/main

`origin/main` was merged at `028fabd8e` to clear a `merge-tree-ratchet` external
error (`ruff count ratchet: EXTERNAL ERROR - counter returned None`, the stale-base
signature). That merge made this report stale against files it never covered, so
the binding moved to the merge commit and every evidence row was re-run there.

Each row reproduced with the same numbers:

- Focused integration and E2E: 20 passed, 1 expected skip, 2.62 seconds.
- Ruff on `tests/integration/test_vendored_install.py`: all checks passed.
- Helper boundary: `git diff origin/main...HEAD -- tests/lib/vendored_copy.py`
  returned zero lines.

The branch-owned files that changed between the two bindings are the session
14697 log and its episode, both from the work-log timestamp fix, and this report.
None of the three is an input to the rows above.
