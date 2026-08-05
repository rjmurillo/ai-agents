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

### Gotcha: pass `--base origin/main`, not the default

`--base` defaults to the literal string `main`, which git resolves to the LOCAL
branch. In a worktree that has not fetched recently, local `main` lags
`origin/main`, and `new_pr.py` computes its changed-file set from
`git diff <base>...HEAD` at line 288. A stale base makes that range include every
file the real base gained since the local ref was last updated.

The visible symptom is an opaque failure that names nothing:

```
[1/6] Checking Session End protocol...
Session End validation failed
```

Mechanism: the spurious changed-file set contains `.agents/` paths the branch
never touched, so `agents_changed` is true (line 299). The script then sorts the
session logs it found and validates the newest one (line 318). That log belongs
to someone else's session on `main`. Your PR is rejected for a file you did not
write.

Measured on `docs/eval-fixture-provenance`, whose real diff touches zero
`.agents/` files:

| Base | `.agents/` files in range |
|---|---|
| `main` (local, `05a4a5677`) | 100+, oldest dated 2026-01-03 |
| `origin/main` (`5ee7a95d5`) | 0 |

Passing `--base origin/main` cleared all six validations on the same branch with
no other change. Fetching would also work, but the explicit remote ref does not
depend on remembering to fetch.

This is the general two-dot and stale-base hazard with a concrete consequence:
you cannot open a PR, and the error names a file unrelated to your work.

**Fixed in PR for issues #4461 and #4489 (2026-08-03).** `new_pr.py` now calls
`_resolve_validation_base(pr_base, explicit)` before running validations. It
prefers `origin/<base>` when that remote-tracking ref exists, falling back to the
bare branch name only when it does not. The `gh pr create --base` argument still
receives the bare name (GitHub rejects `origin/main` there). The `--validation-base`
flag lets callers pin the validation base explicitly. The stale-local-ref symptom
no longer requires remembering to pass `--base origin/main`; it is resolved
automatically.

### Gotcha: GraphQL and REST have separate rate-limit pools

`gh pr create`, and therefore `new_pr.py`, creates the PR through GraphQL. The
GraphQL and REST quotas are counted separately, so GraphQL can be fully spent
while REST still has thousands of calls left:

```
$ gh api rate_limit --jq '{core: .resources.core, graphql: .resources.graphql}'
{"core":{"limit":5000,"remaining":4948,...},"graphql":{"limit":5000,"remaining":0,...}}
```

With GraphQL at 0 the script fails after passing every validation:

```
All pre-creation validations passed!
Creating PR...
GraphQL: API rate limit already exceeded for user ID 6811113.
```

The REST endpoint draws from the `core` pool and still works:

```bash
printf '%s' "$JSON" | gh api --method POST /repos/OWNER/REPO/pulls --input -
```

Confirmed by creating PR #4320 this way while GraphQL read 0 remaining. Waiting
for the GraphQL reset also works; the reset time is in
`gh api rate_limit --jq '.resources.graphql.reset'` as a Unix timestamp.

Prefer `new_pr.py`. Reach for REST only when GraphQL is exhausted, and re-run
the script's validations first, since the raw endpoint performs none of them.

### Missing Script: PR Approval

There is currently NO dedicated approve script in this skill set.

Do NOT work around the skill-first workflow by invoking
`gh pr review --approve` through Python subprocess or other wrappers.

If PR approval is needed, implement it as a proper skill script under `.claude/skills/github/scripts/pr/` and use that script instead.

## Discovery Date

2026-04-10. The former hook blocked `gh pr list` on first attempt. PR #3293
retired that hook on 2026-07-21. Approval support remains a missing skill that
should be added properly rather than bypassing the workflow.
