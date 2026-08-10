---
qaVerdict: PASS
qaSessionLog: .agents/sessions/2026-08-10-session-4788-bacc8e40d-fix-historical-session-log-blocking.json
qaCommit: 5544bbf2f52609d846d33e7f1ef4f6391c932b71
---
# QA Report: issue 4788 session push blocker

## Verdict

PASS.

## Scope

Pre-commit policy plus two historical artifacts introduced by `a0090308df`:

- `scripts/validation/git_hook_policy.py`
- `scripts/validation/checks_tooling.py`
- `tests/test_lefthook_integration.py`
- `tests/test_validation_pre_pr.py`
- `.agents/sessions/2026-08-08-session-10018-b2f6a78e7-fix-issue-3912-authoritative-github.json`
- `.agents/qa/pr-4767-issue-3912-authoritative-pr-context-test-report.md`

The session log appended prose to `sessionEnd.qaValidation.Evidence`, so the
validator read the entire value as a path. The referenced QA report also lacked
the required YAML frontmatter. The session log recorded an unreachable
`endingCommit`.

Pre-commit `check_sessions()` fully validated every staged log, including
historical records, against current HEAD. The existing pre-push path already
distinguishes new logs from existing records. Pre-commit now follows the same
policy while preserving full validation for the current branch's committed
session log.

The first implementation still let a current branch log use creation mode
after its first commit, because it remained new relative to the branch merge
base. Creation mode now requires the log to be absent from HEAD. A committed
branch log gets full validation, and an indeterminate HEAD probe also gets full
validation.

Pre-PR Session End Validation repeated the full-validation bug. It now keeps
`--validation-head` for new branch logs and uses `--existing-log` for
historical records.

Pre-push also trusted lefthook `{push_files}`, which can contain upstream-only
history on a branch's first push. The job now consumes the ref updates on
stdin, derives the actual push range, and validates only session logs changed
by that range. A push-range resolution failure exits 2.

## Evidence

| Check | Result |
|-------|--------|
| Clean `origin/main` negative control | exit 1, QA report path not found |
| Repaired branch positive control | exit 0, session log valid |
| Repaired `qaValidation.Evidence` | bare report path |
| Repaired `qaCommit` and `endingCommit` | `a0090308df0e7eb7bfe99f1e73a5d5bea299a26b` |
| Commit reachability | `git cat-file -e a0090308df...` succeeds |
| Session-policy tests | 9 passed |
| Pre-PR session tests | 5 passed |
| Push-range tests | 19 passed |
| Ruff | all checks passed |
| Taste count ratchet | 582 violations, 1 below baseline 583 |
| Full pre-PR gate | all validations passed |
| Full pre-push Python suite | original run found one stale fixture; corrected control passes |
| Real first-push stdin control | selected only the two session logs changed by this branch |
| Off-HEAD push control | exit 2 |
| Dirty session file control | exit 2 |
| Malformed push input | exit 2 |
| NUL-safe path test | tab in filename preserved |
| Security review | three data-integrity findings fixed |
| Security re-review | NUL newness, symlink, and low-similarity replacement findings fixed |
| Final security re-review | branch-added D+A session replacement gets full validation |
| Episode validation | 4 distinct full-SHA commit events |
| Ship review | explicit CLI dispatch and historical episode metrics fixed |

The negative control used a detached clean-main worktree. The positive control
ran the same command against this branch:

```text
uv run --frozen python scripts/validation/git_hook_policy.py sessions \
  .agents/sessions/2026-08-08-session-10018-b2f6a78e7-fix-issue-3912-authoritative-github.json
```

The repair is byte-identical to the version already carried by PRs #4745,
#4668, and #4667.
