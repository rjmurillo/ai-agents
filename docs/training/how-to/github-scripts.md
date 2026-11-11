# How to do GitHub work with the skill scripts

## Goal

Do common issue and PR tasks with the `github` skill scripts, not raw `gh`.

By the end you will have run each recipe below as a dry run and read its JSON result. A dry run reads state and changes nothing. Dropping `--dry-run` makes the same command do the work.

## Why use the scripts

Raw `gh` prints text meant for people. The scripts print one JSON envelope and a fixed exit code. That makes them safe for agents and for shell scripts.

- **Structured output.** Every script returns `Success`, `Data`, `Error`, and `Metadata`. You read `.Data` on success and `.Error` on failure. See the Output Format section of the skill file.
- **Exit codes.** `0` is success, `1` is a logic error, `2` is a config error, `3` is an external failure, and `4` is an auth error. ADR-035 sets these. A script may add its own code, such as `100` for "not mergeable".
- **Secret redaction.** The shared library has a redactor, `sanitize_failure_detail` in `github_core/api.py`. It replaces token shapes with `[REDACTED]`. `merge_pr.py`, `reopen_pr.py`, `update_pr_branch.py`, and `rerun_failed_jobs.py` use it on GitHub error text before it reaches an envelope. The `redact_secrets.py` script redacts free text you plan to publish.
- **Guard rails.** Merge, branch update, and PR body edits take a head SHA or hash. A script refuses to act when the state moved after you looked.

## Before you start

You need:

- A checkout of this repository. Run every command from its root.
- `python3`, `jq`, and `gh` installed, and `gh` signed in. The transport check below reports `AuthStatus`.

Set the scripts folder once per shell. The `PR` number is an example. Use your own.

```bash
SCRIPTS_DIR="${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-.claude}}/skills/github/scripts"
PR=7256
```

Always pass `--output-format json` when you pipe to `jq`. The default `auto` picks a format from context.

Sample output below came from `main` at `b959011e3` on 2026-11-10. Issue and PR numbers, counts, and SHAs change. The shape does not.

### Confirm the transport

`gh` can be installed and still be refused for a whole session. Check once before the first call.

```bash
python3 "$SCRIPTS_DIR/utils/check_github_transport.py" --output-format json | jq -c .Data
```

```json
{"Transport":"gh","AuthStatus":"authenticated","Guidance":"","Detail":""}
```

If `Transport` is `gh_unusable`, stop. Use the GitHub MCP tools instead. See `.claude/skills/github/references/transport-routing.md`.

## Steps

### Recipe 1: create an issue

Result: you see the issue the script would create, with its labels.

`new_issue.py` needs `--source`. Use `human` only when a person asked for this exact issue. Use `agent` for anything else.

```bash
python3 "$SCRIPTS_DIR/issue/new_issue.py" --title "Docs: example" --source human --body "Example body" --dry-run --output-format json | jq -c .Data
```

```json
{"action":"would_create","dryRun":true,"owner":"rjmurillo","repo":"ai-agents","title":"Docs: example","source":"human","labels":["source:human"],"milestone":null}
```

The script adds the `source:human` label for you.

#### Gotcha: `--source agent` needs `--blocked-by` and `--signal`

An agent-sourced issue must say who is blocked and what proves the gap.

- `--blocked-by`: who is blocked, and on what.
- `--signal`: the metric, log, run, or ticket that proves it.

Leave either one out and the script exits `2` before it calls GitHub. This holds under `--dry-run` too.

```bash
out=$(python3 "$SCRIPTS_DIR/issue/new_issue.py" --title "Docs: example" --source agent --body "Example body" --signal "Issue 7214" --dry-run --output-format json); echo "exit=$?"; echo "$out" | jq -c .Error
```

```text
exit=2
{"Message":"--blocked-by is required when --source=agent","Code":2,"Type":"InvalidParams"}
```

Leaving out `--signal` gives the same shape with `--signal is required when --source=agent`.

Pass both and the dry run succeeds:

```bash
python3 "$SCRIPTS_DIR/issue/new_issue.py" --title "Docs: example" --source agent --body "Example body" --blocked-by "New contributors need a script how-to" --signal "Issue 7214" --labels documentation --dry-run --output-format json | jq -c .Data
```

```json
{"action":"would_create","dryRun":true,"owner":"rjmurillo","repo":"ai-agents","title":"Docs: example","source":"agent","labels":["source:agent","documentation"],"milestone":null}
```

A body that already has a `## Step 0` block with `### Q3` and `### Q5` can replace the two flags. Passing both is an error. Raw `gh issue create` and the MCP `issue_write` tool skip this check. See the Issue Provenance section of `.claude/skills/github/SKILL.md`.

### Recipe 2: label an issue (#6810)

Result: you see which labels the script would add and remove.

`set_issue_labels.py` adds with `--labels` and removes with `--remove-labels`. It works on issues and PRs. A missing label is created unless you pass `--no-create-missing`.

```bash
python3 "$SCRIPTS_DIR/issue/set_issue_labels.py" --issue 7214 --labels bug --remove-labels documentation --dry-run --output-format json | jq -c .Data
```

```json
{"issue":7214,"action":"would_set_labels","dryRun":true,"wouldApply":["bug"],"wouldCreate":[],"skippedMissing":[],"wouldRemove":["documentation"],"absent":[],"reconcilesPriority":false}
```

Removal runs after additions. A name cannot appear in both lists. Separate names with spaces (`--labels bug needs-triage`) or one quoted comma list (`--labels "bug,needs-triage"`). A quoted space list is one label with a space in its name.

### Recipe 3: set a milestone (#6183)

Result: you see the milestone the issue would get.

You can set the milestone when you create the issue. The script checks the milestone first, so a typo fails before any issue exists.

```bash
python3 "$SCRIPTS_DIR/issue/new_issue.py" --title "Docs: example" --source human --body "Example body" --milestone v0.7.0 --dry-run --output-format json | jq -c .Data
```

```json
{"action":"would_create","dryRun":true,"owner":"rjmurillo","repo":"ai-agents","title":"Docs: example","source":"human","labels":["source:human"],"milestone":"v0.7.0"}
```

To change an issue that already exists, use `set_issue_milestone.py`:

```bash
python3 "$SCRIPTS_DIR/issue/set_issue_milestone.py" --issue 7214 --milestone v0.7.0 --dry-run --output-format json | jq -c .Data
```

```json
{"issue":7214,"milestone":"v0.7.0","previous_milestone":null,"action":"would_assign","dry_run":true}
```

If the issue already has a milestone, the script exits `1`. Add `--force` to replace it, or `--clear` to remove it.

### Recipe 4: filter issues and PRs by milestone and label (#6496)

Result: you see a short list that matches both filters.

`list_issues.py` takes `--milestone` (a title such as `v0.7.0`, or a number). It combines with `--state`, `--label`, `--author`, and `--assignee`.

```bash
python3 "$SCRIPTS_DIR/issue/list_issues.py" --milestone v0.7.0 --label area-skills --limit 3 --output-format json | jq -c '.Data.issues | map({number, labels})'
```

```json
[{"number":7221,"labels":["bug","area-infrastructure","priority:P1","area-skills","source:agent"]},{"number":7219,"labels":["bug","area-installation","priority:P1","area-skills","source:agent"]}]
```

`get_pull_requests.py` filters PRs the same way, with `--label`, `--author`, `--base`, and `--head`:

```bash
python3 "$SCRIPTS_DIR/pr/get_pull_requests.py" --state open --label dependencies --limit 2 --output-format json | jq -c '.Data.PullRequests | map({number, state})'
```

```json
[{"number":7250,"state":"OPEN"}]
```

Three things to know:

- Both scripts return at most `--limit` rows. The default is 30 and the range is 1 to 1000. A full page does not mean you saw every row. A limit is a fetch size, not a completeness bound. For a work queue, where each row is an obligation, follow the `lossless-queue-reads` rule.
- `--search` replaces the other filters. `list_issues.py` ignores `--label`, `--author`, `--assignee`, and `--milestone` when you pass it. `get_pull_requests.py` ignores `--label`, `--author`, `--base`, and `--head`.
- `--state closed` on `get_pull_requests.py` includes merged PRs. Read `state` on each row. Use `--state merged` for merged PRs only.

### Recipe 5: merge a PR pinned to its head SHA

Result: you see the merge the script would make, and a refusal when the SHA is wrong.

Check CI first:

```bash
python3 "$SCRIPTS_DIR/pr/get_pr_checks.py" --pull-request "$PR" --output-format json | jq -c '.Data | {Number, PassedCount, FailedCount, PendingCount}'
```

```json
{"Number":7256,"PassedCount":108,"FailedCount":0,"PendingCount":2}
```

Read the head SHA, then pass it to the merge as the commit you reviewed:

```bash
SHA=$(python3 "$SCRIPTS_DIR/pr/get_pr_context.py" --pull-request "$PR" --output-format json | jq -r .Data.head_sha)
python3 "$SCRIPTS_DIR/pr/merge_pr.py" --pull-request "$PR" --expected-head-sha "$SHA" --strategy squash --dry-run --output-format json | jq -c '.Data | {action, dryRun, strategy, head_sha}'
```

```json
{"action":"would_merge","dryRun":true,"strategy":"squash","head_sha":"bbd06bfce0823734fc36ca96491f47b88fb16022"}
```

Now pass a SHA that is not the head. The script refuses and makes no merge call:

```bash
out=$(python3 "$SCRIPTS_DIR/pr/merge_pr.py" --pull-request "$PR" --expected-head-sha 0123456789abcdef0123456789abcdef01234567 --dry-run --output-format json); echo "exit=$?"; echo "$out" | jq -c .Error
```

```text
exit=1
{"Message":"PR #7256 head does not match the reviewed commit: expected 0123456789abcdef0123456789abcdef01234567, actual bbd06bfce0823734fc36ca96491f47b88fb16022. Wrong PR or the branch moved after review; no merge attempted.","Code":1,"Type":"InvalidParams"}
```

That refusal is the point of the pin. If someone pushes after your review, the merge stops. Review the new head, then pass the new SHA.

A dry run checks the PR itself. GitHub applies branch protection at merge time, so a real merge can still be blocked. Exit `100` means "not mergeable". Run `why_pr_blocked.py` to see the cause. ADR-112 covers the audit block in the real merge output.

### Recipe 6: update a PR branch on the server (#6139)

Result: you see whether the PR is behind its base and whether an update would run.

This is the API behind the "Update branch" button. No local checkout or push is needed.

```bash
python3 "$SCRIPTS_DIR/pr/update_pr_branch.py" --pull-request "$PR" --expected-head-sha "$SHA" --dry-run --output-format json | jq -c '.Data | {action, dry_run, behind_by, precheck}'
```

```json
{"action":"would_update","dry_run":true,"behind_by":1,"precheck":"ok"}
```

Pass `--expected-head-sha` so GitHub refuses when the head moved. Add `--wait` to poll until the PR is no longer behind. The wait defaults to 120 seconds (`--timeout-seconds`). A timeout exits `3`. If the head differs from your SHA, the script exits `1`.

### Recipe 7: rerun failed jobs (#6977)

Result: you see which failed runs would be rerun.

Use this for a flaky check. Do not push an empty commit.

```bash
python3 "$SCRIPTS_DIR/pr/rerun_failed_jobs.py" --pull-request 7244 --dry-run --output-format json | jq -c '.Data | {reason, would_rerun: (.would_rerun | map({name, conclusion}))}'
```

```json
{"reason":"dry_run","would_rerun":[{"name":"Enforcement Closure","conclusion":"failure"}]}
```

The script only reruns runs that finished. If every run is still going, it exits `1`:

```bash
out=$(python3 "$SCRIPTS_DIR/pr/rerun_failed_jobs.py" --pull-request "$PR" --dry-run --output-format json); echo "exit=$?"; echo "$out" | jq -c '{reason: .Data.reason, message: .Error.Message}'
```

```text
exit=1
{"reason":"run_in_progress","message":"Only in-progress runs found; a run that is not completed cannot be rerun. Status: waiting, queued"}
```

Wait for the runs to end, then try again. Use `--run-id` to target one run, and `--job-id` with it to target one job. Exit `100` means GitHub refused the rerun. Do not retry. The `--help` text says to use a fallback.

### Recipe 8: reopen a closed PR (#6533)

Result: you see that a closed PR would be reopened, and that a merged PR cannot be.

```bash
python3 "$SCRIPTS_DIR/pr/reopen_pr.py" --pull-request 7148 --dry-run --output-format json | jq -c .Data
```

```json
{"pull_request":7148,"state":"CLOSED","action":"would_reopen","dry_run":true,"message":"Dry run: PR would be reopened; nothing changed"}
```

A merged PR cannot be reopened:

```bash
out=$(python3 "$SCRIPTS_DIR/pr/reopen_pr.py" --pull-request 7255 --dry-run --output-format json); echo "exit=$?"; echo "$out" | jq -c .Error
```

```text
exit=1
{"Message":"PR #7255 is merged; only a closed PR can be reopened","Code":1,"Type":"InvalidParams"}
```

Add `--comment "reason"` to explain the reopen. Reopening an already open PR exits `0`. Exit `3` covers API failures, timeouts, and a deleted head branch.

## If something fails

Read the exit code first, then `.Error.Message`.

| Exit | Meaning | What to do |
|------|---------|------------|
| 1 | Logic error, such as a moved head or a merged PR | Read `.Error.Message`. Fix the input or re-read the PR state. |
| 2 | Bad arguments or config, or "not found" for scripts that look up a PR, issue, or milestone | Read `.Error.Message`. Fix the flag or the number. |
| 3 | GitHub or network failure | Retry once. If it repeats, run the transport check. |
| 4 | Not signed in | Sign `gh` in, then run the transport check again. |
| 100 | Script-specific refusal: not mergeable (`merge_pr.py`) or rerun refused (`rerun_failed_jobs.py`) | Do not retry the same call. Diagnose with `why_pr_blocked.py`, or use the fallback the script prints. |

An unreachable API is an unknown, not a verdict. Do not report a PR as blocked because a call failed.

Run `python3 "$SCRIPTS_DIR/<folder>/<script>.py" --help` for any script. It lists every flag and its exit codes.

## Check your result

You are done when:

- The transport check printed `"Transport":"gh"`.
- Each recipe printed JSON with `"dryRun":true` or `"dry_run":true`, or the exit code and error shown above.
- You can say what `--source agent` needs. Answer: `--blocked-by` and `--signal`.

Check the redactor too. This builds a fake token and pipes it through:

```bash
printf 'deploy token=%s\n' "ghp_$(printf 'a%.0s' {1..36})" | python3 "$SCRIPTS_DIR/issue/redact_secrets.py"
```

```text
deploy token=[redacted: github-token]
```

## Next

- Pick the right script for a task: the Decision Tree in `.claude/skills/github/SKILL.md`.
- Every flag and exit code: `.claude/skills/github/references/script-catalog.md` and `.claude/skills/github/references/api-reference.md`.
- Link issues to each other: `.claude/skills/github/references/issue-relationships.md`.
- When to use REST or GraphQL: [GitHub API capabilities](../../github-api-capabilities.md).
- Exit code standard: ADR-035 in `.project-toolkit/architecture/ADR-035-exit-code-standardization.md`.
- Merge audit and action tiers: ADR-112 in `.project-toolkit/architecture/ADR-112-risk-tiered-action-boundaries.md`.
