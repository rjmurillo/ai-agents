# GitHub Skill Scripts Reference

## Critical Rule

You MUST use the Python skill scripts for covered GitHub operations. This rule
is canonical in `AGENTS.md`. PR #3293 retired the former PreToolUse enforcement
hook, so current sessions do not get a runtime block or redirect. Direct `gh`
commands remain valid where no skill script exists.

Do not treat the missing runtime block as permission to bypass an available
skill script.

## Script Location

GitHub skill scripts live under `.claude/skills/github/scripts/`, with multiple subdirectories such as `pr/`, `issue/`, and `reactions/`.

The scripts listed in this reference are primarily PR-related, so most are under `.claude/skills/github/scripts/pr/`.

## Available Scripts

### Listing and Querying

| Script | Purpose | Key Args |
|--------|---------|----------|
| `get_pull_requests.py` | List PRs | `--owner`, `--repo`, `--state`, `--limit`, `--label`, `--author` |
| `get_pr_context.py` | PR details (title, body, files) | `--owner`, `--repo`, `--pull-request` |
| `test_pr_merge_ready.py` | Check merge readiness | `--owner`, `--repo`, `--pull-request` |
| `test_pr_merged.py` | Check if PR merged | `--owner`, `--repo`, `--pull-request` |
| `get_pr_checks.py` | CI check status | `--owner`, `--repo`, `--pull-request`, `--output-format json` |
| `get_pr_check_logs.py` | CI failure logs | `--owner`, `--repo`, `--pull-request`, `--check-name` |
| `get_pr_reviewers.py` | List reviewers | `--owner`, `--repo`, `--pull-request` |

### Review Threads

| Script | Purpose | Key Args |
|--------|---------|----------|
| `get_unresolved_review_threads.py` | Open threads | `--owner`, `--repo`, `--pull-request` |
| `get_pr_review_threads.py` | All threads | `--owner`, `--repo`, `--pull-request` |
| `add_pr_review_thread_reply.py` | Reply to thread | `--owner`, `--repo`, `--pull-request`, `--thread-id`, `--body` |
| `resolve_pr_review_thread.py` | Resolve thread | `--owner`, `--repo`, `--pull-request`, `--thread-id` |
| `get_unaddressed_comments.py` | Comments needing response | `--owner`, `--repo`, `--pull-request` |

### Actions

| Script | Purpose | Key Args |
|--------|---------|----------|
| `merge_pr.py` | Merge a PR | `--owner`, `--repo`, `--pull-request` |
| `set_pr_auto_merge.py` | Enable auto-merge | `--owner`, `--repo`, `--pull-request` |
| `close_pr.py` | Close a PR | `--owner`, `--repo`, `--pull-request` |
| `new_pr.py` | Create a PR | `--title`, `--body`, `--head`, `--base` (NO `--owner`/`--repo`) |

### Gotcha: new_pr.py

`new_pr.py` does NOT accept `--owner` or `--repo`. It infers the repo from the current git remote. If you pass `--owner`, it exits with error code 2.

### Missing Script: PR Approval

There is currently NO dedicated approve script in this skill set.

Do NOT work around the skill-first workflow by invoking
`gh pr review --approve` through Python subprocess or other wrappers.

If PR approval is needed, implement it as a proper skill script under `.claude/skills/github/scripts/pr/` and use that script instead.

## Discovery Date

2026-04-10. The former hook blocked `gh pr list` on first attempt. PR #3293
retired that hook on 2026-07-21. Approval support remains a missing skill that
should be added properly rather than bypassing the workflow.
