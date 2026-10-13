# Check For An Existing PR Before Creating An Issue Worktree

## Statement

Before you create a branch or worktree for issue N, run:

```bash
python3 .claude/skills/github/scripts/issue/check_existing_pr_for_issue.py --issue N
```

Exit 0 means no open PR claims the issue, so proceed. Exit 1 means an open PR
already claims it, so continue on that PR and do not open a second one.

## Exit codes

From the script docstring (ADR-035): 0 safe to proceed, 1 an open PR claims the
issue, 2 plugin lib path missing, 3 gh or API failure, 4 not authenticated.
With `--output-format json` the result carries `Success`, plus
`Data.existing_pr_count` and `Data.existing_prs`.

## What counts as a claim

The script matches closing keywords only: Fixes, Closes, Resolves. A PR that
says `Refs #N` does not count (issue #4894). A keyword inside an inline code
span or fenced block does not count either (issue #3827).

## Incidents

- 2026-07-17: the fix for issue #3089 launched without this check and wasted a
  build cycle. Hindsight REF 3748996e.
- 2026-10-12: sweep agents rediscovered the check and reused existing work in
  PR #6335 and PR #6384.

## Evidence

Verified 2026-10-13 against `origin/main` at ec57f45d4: the script exists, its
`--help` lists `--issue` and `--output-format`, and a run for issue 6335 exited 0
with `existing_pr_count` 0 (no open PR claimed it at that moment). The exit 1
path is read from the docstring, not reproduced.

Source: Hindsight page "Multi-agent run playbook" (kp-5ad73a597d6a4cb69a6a3dd731fad139),
REF 3748996e.
