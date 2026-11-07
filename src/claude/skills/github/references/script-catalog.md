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
| `check_pr_round_cap.py` | Round and wall-clock circuit breaker for the pr-autofix thread loop. Exit 0 under both caps, exit 1 a cap is exceeded | `--pull-request`, `--max-rounds`, `--max-hours`, `--reset`, `--worktree` |
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

## Full text of shortened rows

### `audit_closing_claims.py`

Fleet audit of open-PR closing claims: extracts closing keywords from PR bodies, commit messages, and auto-merge overrides; classifies body (Markdown) and commit/override (plain-text) context; flags a claim unsupported when it can reach the squash commit without a matching active body claim (exit 1). Needs a token with administration read (GitHub hides `squash_merge_commit_message` otherwise); without it the audit exits 3 instead of reporting a clean fleet.

Parameters: `--state open`, `--artifact`, `--resume-from`, `--output-format {json,human,auto}`

### `manage_squash_merge_message.py`

Read or update the `squash_merge_commit_message` repository setting with an expected-current-value guard; reports a real before/after re-read. Needs a token with administration read: GitHub omits merge settings for anyone else, and the script exits 3 rather than assuming a value.

Parameters: `--set`, `--expected-current`, `--dry-run`, `--output-format {json,human,auto}`

### `why_pr_blocked.py`

Diagnose a `mergeable_state`/`mergeStateStatus: blocked` PR: decomposes it into missing/failing/pending required checks, unresolved review threads, or merge conflicts, and says explicitly when none of those hold (the field can be stale).

Parameters: `--pull-request`, `--base-branch`, `--output-format {json,human,auto}`

### `triage_red_check.py`

CI-failure triage step 1: is a failing PR check also red on main's latest run? Exit 0 green on main, exit 1 red on main (EvidenceUrl cites the main run), exit 3 cannot determine (never reported as green).

Parameters: `--check-name`, `--branch`, `--history-depth`, `--pull-request`
