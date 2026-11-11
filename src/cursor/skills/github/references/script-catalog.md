# Script Catalog

Scripts the `SKILL.md` tables do not carry, plus the full text of rows that
were shortened there. The first eight scripts below sit in the `pr` subdirectory
of the skill's script directory, the last four in `issue`. Run every script with
`python3` and read `--help` first. Mutating scripts take `--dry-run` where the
`SKILL.md` table lists it.

## Additional scripts

| Script | Purpose | Key Parameters |
|--------|---------|----------------|
| `check_pr_live_state.py` | Re-triage probe before acting on a queued PR. Exit 0 safe to act, exit 1 skip (merged, closed, or superseded by main), exit 2 not found | `--pull-request`, `--skip-fetch`, `--expected-head-sha`, `--expected-base-ref`, `--expected-base-sha` |
| `check_pr_round_cap.py` | Round and wall-clock circuit breaker for the pr-autofix thread loop. Exit 0 under both caps, exit 1 a cap is exceeded | `--pull-request`, `--max-rounds`, `--max-hours`, `--reset`, `--worktree`, `--dry-run` |
| `run_completion_gate.py` | Run the `/pr-review` completion criteria from a config file and print one result per criterion. Exit 0 all pass, exit 1 any fails, exit 3 unverified | `--config`, `--pull-request`, `--json`, `--evidence-path`, `--trusted-ref`, `--verify-config-only` |
| `check_review_thread_resolution_shas.py` | Verify that commits cited in resolved review threads are in the PR head | `--pull-request`, `--repo-path` |
| `check_suppressed_review_findings.py` | Report Copilot review findings that GitHub suppressed instead of threading; waive one with a tracked dispositions file | `--pull-request`, `--dispositions-file` |
| `detect_stale_pr_comments.py` | Find review comments on files that no longer exist at the PR head | `--pull-request`, `--bot-only` |
| `get_pr_comments_by_reviewer.py` | Group PR review and issue comments by reviewer login | `--pull-request`, `--include-reviewer`, `--exclude-reviewer`, `--since`, `--until`, `--comment-type` |
| `prepare_pr_body.py` | Create a private PR body file seeded with the repository template and print its path; takes no flags but `--help` | none |
| `check_existing_pr_for_issue.py` | Before opening a PR, check whether an open PR already claims the issue with a closing keyword. Exit 0 safe to proceed, exit 1 an open PR claims it | `--issue` |
| `claim_issue.py` | Self-assign an issue; refuse (exit 1) when another login holds it; warn about pushed branches that name the issue | `--issue`, `--dry-run` |
| `edit_issue_body.py` | Replace an issue body from `--body` or `--body-file` | `--issue`, `--body`, `--body-file` |
| `redact_secrets.py` | Redact secret and PII shapes from text on stdin or `FILE`; writes the result to stdout | `FILE` |
| `get_pr_code_scanning_alerts.py` | Read a PR's CodeQL alerts for `/review` (ADR-041 amendment). GET only, every page, JSON on stdout. `Data.outcome` is CURRENT, STALE, NOT ANALYZED, or SKIPPED. Alerts reduce to rule id, path, line. Exit 0 outcome read, exit 2 usage, exit 3 SKIPPED (request or paging failed), exit 4 SKIPPED (auth or not found) | `--pull-request`, `--head-sha`, `--tree-state`, `--changed-file`, `--changed-files-from` |

## Full text of shortened rows

### `audit_closing_claims.py`

Fleet audit of open-PR closing claims: extracts closing keywords from PR bodies, commit messages, and auto-merge overrides; classifies body (Markdown) and commit/override (plain-text) context; flags a claim unsupported when it can reach the squash commit without a matching active body claim (exit 1). Needs a token with administration read (GitHub hides `squash_merge_commit_message` otherwise); without it the audit exits 3 instead of reporting a clean fleet.

Parameters: `--state open`, `--artifact`, `--resume-from`, `--output-format {json,human,auto}`

### `close_issue.py`

Close with an optional comment. `--verify-claims` aborts with exit 1 on a cited commit or PR the remote disproves, and separately with exit 3 or 4 on one it could not check.

Parameters: `--issue`, `--reason`, `--comment`, `--verify-claims`, `--dry-run`

### `get_pr_checks.py`

CI check status with polling. Falls back to REST on a GraphQL rate limit and reports the source in `DataSource`. REST `--required-only` with no ruleset exits 3.

Parameters: `--pull-request`, `--wait`, `--timeout-seconds` (keep at or below 570 with `--wait`; it warns above), `--missing-grace-seconds`, `--required-only`, `--output-format {json,human,auto}`

### `manage_squash_merge_message.py`

Read or update the `squash_merge_commit_message` repository setting with an expected-current-value guard; reports a real before/after re-read. Needs a token with administration read: GitHub omits merge settings for anyone else, and the script exits 3 rather than assuming a value.

Parameters: `--set`, `--expected-current`, `--dry-run`, `--output-format {json,human,auto}`

### `why_pr_blocked.py`

Diagnose a `mergeable_state`/`mergeStateStatus: blocked` PR: decomposes it into missing/failing/pending required checks, unresolved review threads, or merge conflicts, and says explicitly when none of those hold (the field can be stale).

Parameters: `--pull-request`, `--base-branch`, `--output-format {json,human,auto}`

### `triage_red_check.py`

CI-failure triage step 1: is a failing PR check also red on main's latest run? Exit 0 green on main, exit 1 red on main (EvidenceUrl cites the main run), exit 3 cannot determine (never reported as green).

Parameters: `--check-name`, `--branch`, `--history-depth`, `--pull-request`

## Previewing a change with `--dry-run`

Each script below runs its reads and validation as a real run does, then
reports the planned change and writes nothing. The result carries
`dryRun: true` (or `DryRun`/`dry_run` where the script already used that key)
and a `would_*` action. A refusal fails the same way under `--dry-run`, with
the same exit code.

The marker means the run was a preview, so it is present even when nothing
needs to change. A dry run on such a target reports the same no-op action as a
real run (`action: none` for a merged PR or a PR already up to date, `NoChange`
for auto-merge that is already off, `already_closed` for a closed issue) and
adds the marker. Read the action to learn whether a change would happen.

| Script | Action reported | Note |
|--------|-----------------|------|
| `close_issue.py` | `would_close` | `--verify-claims` still runs and can still refuse |
| `new_issue.py` | `would_create` | no label, issue, or milestone write |
| `edit_issue_body.py` | `would_update` | reads the issue first; a missing or hidden issue exits 3, as the edit would |
| `set_issue_labels.py` | `would_set_labels` | reads the issue and label existence (a missing issue exits 3); lists `wouldCreate`, `wouldApply`, `wouldRemove` (including the stale `priority:*` label a new priority replaces) |
| `set_issue_assignee.py` | `would_assign` | reads the issue first; a missing issue exits 3 |
| `close_pr.py` | `would_close` | reports `wouldComment` and posts no comment; a real run exits 3 and leaves the PR open when the closing comment fails |
| `new_pr.py` | text line `Dry run: would create PR` | runs the pre-creation validations; writes no audit log; exits 2 with `--prepare-body-file` |
| `new_pr_review_comment.py` | `would_post` | reads the PR head commit and every review comment; `would_skip` (reason `duplicate`) when the same author already posted the same body at the path, line, and side |
| `post_pr_comment_reply.py` | `would_post` | reads the PR or comment first (exit 2 if missing, or if the comment is on another PR); names the endpoint and body length; `would_skip` (reason `duplicate`) when the same author already posted the same body in the thread or PR conversation |
| `add_pr_review_thread_reply.py` | `would_post` | reads the thread and applies the `--pull-request` and `--expected-*` guards as a real run does; `would_skip` when a real run skips (not found, resolved, another PR), exit 1 when the PR identity moved; with `--resolve` also reports `resolve_action: would_resolve`; posts, resolves, and disarms auto-merge nothing |
| `resolve_pr_review_thread.py` | `would_resolve`, `would_skip` | reads the thread state as a real run does (`would_skip` for not found, already resolved, wrong PR); `--pull-request` pages every thread, exits 3 if a page cannot be read, and lists a per-thread `would_resolve` or `would_skip` |
| `set_pr_auto_merge.py` | `WouldEnable`, `WouldDisable`, `NoChange` | enabling on a closed or merged PR exits 3, as a real run does |
| `unresolve_pr_review_thread.py` | `would_unresolve` | `--thread-id` reads the thread and exits 1 when it is not found; `--all` lists the thread ids, reading every page and failing if a page cannot be read |
| `update_pr_branch.py` | `would_update` | |
| `set_pr_ready.py` | `would_mark_ready`, `would_convert_to_draft`, `none` | reads state, draft flag, and head; a closed or merged PR exits 1, a head that differs from `--expected-head-sha` exits 1, as a real run does |
| `invoke_pr_comment_processing.py` | `[dry-run]` lines | classifies every comment; posts no reaction or reply; does not check that a comment id exists |
| `check_pr_round_cap.py` | the usual verdict plus `dryRun` | records no round: no state marker, no escalation note, and `--worktree` fetches no git objects (a missing head reports as unverified) |
| `merge_pr.py` | `would_merge` | stops after the pre-merge refusals and before any merge call; the audit record says `dry run; no merge call`. Branch protection and stack readiness are evaluated by GitHub at merge time, so a dry run is not a merge-ready verdict |

`unresolve_pr_review_thread.py --pull-request N` now requires `--all`, as the
`SKILL.md` row already says. Without it the script exits 2.
