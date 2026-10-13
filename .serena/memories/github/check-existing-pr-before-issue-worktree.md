# Check for an existing PR before creating an issue worktree

## Statement

Before you create a branch or worktree for issue N, run this as session-init
Step 0, from `main` or a detached HEAD:

```bash
python3 .claude/skills/github/scripts/issue/check_existing_pr_for_issue.py --issue N
```

Exit 0 means no open PR claims the issue, so proceed. Exit 1 means an open PR
already claims it, so continue on that PR and do not open a second one.

Do not run it from a feature branch you already own. `_is_self_branch_pr` skips
a PR written by the current `gh` user whose head ref matches the current branch
(issue #4965), so the script returns 0 and hides that PR.

## Reading the result

Branch on the exit code, not on `Success`. `Success` is false for a claim and
for every error. The codes (ADR-035): 0 safe to proceed, 1 an open PR claims the
issue, 2 plugin lib path missing, 3 gh or API failure, 4 not authenticated.

- Exit 1 writes the JSON envelope with `Success: false`, `Error.Code: 1`, and
  `Data` still carrying `existing_pr_count` and `existing_prs`.
- Exit 3 leaves `Data` null.
- Exit 2 writes plain text to stderr and no envelope.

The default `--output-format auto` already emits JSON when stdout is not a TTY
or `CI` is set.

## What counts as a claim

GitHub closing keywords in the PR title or body: close, fix, resolve and their
-s, -d, -es, -ed forms, in any case. The issue ref is `#N`, or `owner/repo#N`
for this repository. A different repository's `#N` does not match. `Refs #N`
does not count (issue #4894). A keyword inside an inline code span or fenced
block does not count either (issue #3827).

## Incident

2026-07-17: the fix for issue #3089 launched without this check. It produced a
redundant, more complex competing branch and wasted a full build cycle.
Hindsight REF 3748996e.

## Evidence

Verified 2026-10-13 against `origin/main` at ec57f45d4. The script exists and
`--help` lists `--issue` and `--output-format`. The keyword pattern and exit
codes are read from the script. Exit 1 is asserted by
`test_duplicate_pr_exits_without_invalid_error_type` and
`test_detached_head_reports_existing_owner_pr` in
`tests/test_issue_coordination.py`.

Source: Hindsight page "Multi-agent run playbook"
(kp-5ad73a597d6a4cb69a6a3dd731fad139), section "Pre-Run Checks", REF 3748996e.
The page ties the 2026-10-12 sweep to a different behavior, so this memory makes
no claim about that sweep.
