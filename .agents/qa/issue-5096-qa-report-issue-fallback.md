---
qaVerdict: PASS
qaSessionLog: .agents/sessions/2026-08-15-session-14713-issue-5096-qa-report-issue-fallback.json
qaCommit: e93af5c82d39a52102ea9e07a9c4f6fc5f361b57
---

# Issue 5096 QA Report Issue Fallback QA

## Scope

`scripts/ci/check_pr_qa_report.py` resolved a QA report by globbing
`.agents/qa/*pr-{pr_number}*.md` only. A PR number does not exist until the PR
is opened, so the first push of every code PR failed the gate, and clearing it
cost a rename commit plus a second full push cycle at 10 to 20 minutes of
pre-push hooks. This validates the linked-issue fallback that removes that cost.

Files under test:

- `scripts/ci/check_pr_qa_report.py`
- `tests/ci/test_pr_validation_workflow.py`

This report is itself the end-to-end evidence: it is named for the issue, not
the PR, so the gate on this PR exercises the new path against the change that
introduces it.

## Acceptance Criteria

From issue #5096: the gate must accept a QA report that names a linked issue
when no PR-numbered report exists, keep preferring the PR-numbered report, and
apply the same downstream validation to whichever report it resolves.

## What Changed

`_pr_body` fetches the body with the same `gh api` shape and the same
`check=False` plus explicit `returncode` read as the existing `_pr_head_sha`.
`_linked_issues` extracts issue numbers with

```text
(?i)\b(?:close[sd]?|fixe?[sd]?|fix|resolve[sd]?|refs?)\s+#(\d+)
```

deduplicated and sorted numerically. `_find_issue_qa_report` globs
`.agents/qa/*issue-{n}*.md` per number in that order. `_resolve_qa_report`
sequences them: PR-numbered first, then the fallback, and it reports a failed
body fetch as EXTERNAL_ERROR (exit 3), consistent with how `_changed_files`
reports a broken `gh api` rather than reading it as a missing report.

`main` still routes the resolved report through `_validate_report`, so the
session-log binding and the post-QA staleness walk are unchanged.

## Test Evidence

Command: `uv run pytest tests/ci/test_pr_validation_workflow.py -q`

Result: 96 passed (70 before this change, 26 added).

Coverage added, positive:

- PR-named report preferred when both a PR-named and an issue-named report
  exist, asserted on `main() == 0`, on the emitted `qa_report=` name, and on
  the absence of any `.body` call in the recorded argument vectors.
- Issue-named report accepted when no PR-named report exists.
- Twelve keyword spellings resolve the report: `Fixes`, `fixes`, `Fixed`,
  `Fix`, `Closes`, `Closed`, `Close`, `Resolves`, `Resolved`, `Refs`, `Ref`,
  and a keyword inside a multi-line body.
- The lowest-numbered linked issue wins when two linked issues both have
  reports, pinning the sorted-and-deduplicated order.

Coverage added, negative and edge:

- Six bare-mention bodies (`#5096`, `See #5096 for context`, `Related to
  #5096`, `This prefix #5096 is not a keyword`, `Issue 5096 has no hash`, and
  an empty body) each return `main() == 1`.
- A linked issue with no matching report returns `main() == 1`.
- A failed body fetch returns `main() == 3` and writes no `qa_report_exists`
  line, which is what distinguishes a broken API from a missing report.
- An issue-named report with a `FAIL` verdict, and an issue-named report gone
  stale, each return `main() == 1` with the same errors a PR-named report
  produces.

Every exit-code assertion drives `qa_mod.main()`, not a helper, per
`.claude/rules/ci-scripts.md` MUST 10. `scripts/ci/cli_exit_contract_ratchet.py`
reports `OK (count == baseline 27)`.

Subprocess is mocked at the process boundary by a fake dispatched on its
argument vector rather than on call order, per `.claude/rules/testing.md`
SHOULD 11. No live API call runs in the suite.

## Discrimination Evidence

Four mutants, each applied to the restored file and run with the bytecode cache
deleted first (`.claude/rules/testing.md` SHOULD 8 and SHOULD 10):

| Mutant | Tests failed |
| --- | --- |
| Fallback removed, `main` calls `_find_qa_report` only | 17 |
| Keyword requirement dropped, regex becomes `(?i)#(\d+)` | 4 |
| Preference reversed, issue fallback consulted first | 3 |
| Issue number dropped from the glob, `*issue-*.md` | 1 |

Mutant 3 also failed two pre-existing tests, which is the expected reading: the
PR-numbered path is what those tests assert. Mutant 2 left the two
bare-mention cases carrying no `#` at all passing, which is correct, since
those inputs contain nothing for a widened regex to match. The file was
restored from a pristine copy after each mutant and the full suite returned to
96 passed.

## Gate Evidence

- `uv run ruff check scripts/ci/check_pr_qa_report.py tests/ci/test_pr_validation_workflow.py`: All checks passed.
- `uv run mypy scripts/ci/check_pr_qa_report.py`: Success, no issues found.
- `uv run python scripts/validation/validate_python_syntax.py`: exit 0 (the 3.10 hook-portability floor; the fallback adds only stdlib `re`, which matters because `.github/workflows/pr-validation.yml` line 129 invokes this script with bare `python3`).
- `uv run python scripts/validation/pre_pr.py`: exit 0, `RESULT: All validations passed`, 121 checks reported PASS.

`ruff format --check` reports both touched files as needing reformatting. That
is pre-existing: the same command on the clean tree at `origin/main` reports the
identical two files. `ruff format --diff` on the changed script shows no
proposed change inside any line this PR adds. The test file's proposed changes
are all collapses of the implicit string concatenation the existing module uses
throughout, and the new tests follow that same house style. Reformatting either
file wholesale is out of scope for this change.

## End-to-End Evidence On This Branch

The shipped script was driven against this repository with `PR_NUMBER` set to a
number no report names and a stub body reading `Fixes #5096`. It resolved
`.agents/qa/issue-5096-qa-report-issue-fallback.md`, ran the full
`_validate_report` path against the real session log and real git ancestry, and
returned 0. That is the same code path the `Validate PR` job takes.

Negative control, same driver with the body changed to `See #5096 with no
keyword`: `main()` returned 1 and printed `No QA report found for code
changes`. So the resolution came from the keyword in the body, not from the
report merely existing on disk.

## Known Gaps

- Both globs match on a numeric prefix, so `*issue-5096*.md` would also match a
  hypothetical `issue-50960-...md`. The PR-numbered glob has carried the same
  weakness since it was written. Tightening both belongs in one change rather
  than half of it here.
- The fallback reads the PR body, so an author who writes the QA report but
  omits the issue link from the body still gets the old failure. That is the
  correct failure: `.claude/rules/universal.md` MUST 2 already requires the
  link.
- The prior-cost evidence is one recorded instance, not a rate:
  `.agents/sessions/2026-08-14-session-14707-4940-model-pin-doc-examples.json`
  logs the rename verbatim. No sweep counted how many PRs paid it, so the "every
  code PR" reading follows from the glob's contract rather than from a census.

## Security

No security-relevant surface. The change adds one read-only `gh api` call
alongside the two the script already makes, builds no shell string (the
argument vector is a list, so there is no CWE-78 exposure), and constructs no
filesystem path from external input: the issue number reaches the glob only
through `(\d+)`, so it cannot carry a separator or a `..` segment (CWE-22).

## Verdict

PASS.
