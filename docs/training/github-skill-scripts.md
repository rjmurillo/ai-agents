# Do GitHub work with the skill scripts, not raw gh

## Goal

By the end, you will have run eight common issue and PR tasks through the `github` skill scripts and read each JSON result. You will know a step worked when the output matches the sample shown. Every step that could change something uses `--dry-run`, so nothing in the repository changes. Drop `--dry-run` to do the task for real.

This page is for contributors and agents who do PR and issue work.

Raw `gh` prints text meant for people. The scripts print one JSON envelope and a fixed exit code. We use them for four reasons:

- **Structured output.** Every script returns `Success`, `Data`, `Error`, and `Metadata`. You read `.Data` on success and `.Error` on failure. The Output Format section of the [skill file](../../.claude/skills/github/SKILL.md) has the shape.
- **Exit codes.** `0` is success, `1` is a logic error, `2` is a config error, `3` is an external failure, and `4` is an auth error. [ADR-035](../../.project-toolkit/architecture/ADR-035-exit-code-standardization.md) sets these. A script may add its own code, such as `100`.
- **Secret redaction.** The shared library has a redactor, `sanitize_failure_detail` in [`api.py`](../../scripts/github_core/api.py). It replaces token shapes with `[REDACTED]`. `merge_pr.py`, `reopen_pr.py`, `update_pr_branch.py`, and `rerun_failed_jobs.py` use it on GitHub error text before it reaches an envelope. The `redact_secrets.py` script redacts free text you plan to publish.
- **Guard rails.** Merge and branch update take the head SHA you reviewed. A script refuses to act when the branch moved after you looked.

## Before you start

You need:

- A checkout of this repository. Run every command from its root.
- `uv`, `jq`, and `gh` installed, with `gh` signed in. Step 1 reports `AuthStatus`.

Set the scripts folder once per shell. The PR number is an example. Use your own.

```bash
SCRIPTS_DIR="${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-.claude}}/skills/github/scripts"
PR=7297
```

Pass `--output-format json` whenever you pipe to `jq`. The default, `auto`, picks a format from context.

The sample output came from `main` at `d34536c95` on 2026-11-11. Issue and PR numbers, counts, and SHAs change as the repository moves. The shape does not.

In a sandbox with no network, `uv run` cannot resolve the project. See Offline Invocation in the [skill file](../../.claude/skills/github/SKILL.md).

For when to use REST or GraphQL under these scripts, read [GitHub API capabilities](../github-api-capabilities.md). This page does not repeat it.

## Steps

1. Confirm the transport. `gh` can be installed and still be refused for a whole session, so check once before the first call.

   ```bash
   uv run python "$SCRIPTS_DIR/utils/check_github_transport.py" --output-format json | jq -c .Data
   ```

   ```json
   {"Transport":"gh","AuthStatus":"authenticated","Guidance":"","Detail":""}
   ```

   If `Transport` is `gh_unusable`, stop and use the GitHub MCP tools. See [transport routing](../../.claude/skills/github/references/transport-routing.md).

2. Create an issue (outcome: you see the issue the script would create, with its labels). `new_issue.py` needs `--source`. Use `human` only when a person asked for this exact issue. Use `agent` for anything else.

   ```bash
   uv run python "$SCRIPTS_DIR/issue/new_issue.py" --title "Docs: example" --source human --body "Example body" --dry-run --output-format json | jq -c .Data
   ```

   ```json
   {"action":"would_create","dryRun":true,"owner":"rjmurillo","repo":"ai-agents","title":"Docs: example","source":"human","labels":["source:human"],"milestone":null}
   ```

   The script adds the `source:human` label for you.

   **Gotcha: `--source agent` needs `--blocked-by` and `--signal`.** An agent-sourced issue must say who is blocked and what proves the gap. `--blocked-by` names who is blocked, and on what. `--signal` names the metric, log, run, or ticket that proves it. Leave either one out and the script exits `2` before it calls GitHub. This holds under `--dry-run` too.

   ```bash
   out=$(uv run python "$SCRIPTS_DIR/issue/new_issue.py" --title "Docs: example" --source agent --body "Example body" --signal "Issue 7214" --dry-run --output-format json); echo "exit=$?"; echo "$out" | jq -c .Error
   ```

   ```text
   exit=2
   {"Message":"--blocked-by is required when --source=agent","Code":2,"Type":"InvalidParams"}
   ```

   Leaving out `--signal` gives the same shape, with the message `--signal is required when --source=agent`. Pass both and the dry run succeeds:

   ```bash
   uv run python "$SCRIPTS_DIR/issue/new_issue.py" --title "Docs: example" --source agent --body "Example body" --blocked-by "New contributors need a script how-to" --signal "Issue 7214" --labels documentation --dry-run --output-format json | jq -c .Data
   ```

   ```json
   {"action":"would_create","dryRun":true,"owner":"rjmurillo","repo":"ai-agents","title":"Docs: example","source":"agent","labels":["source:agent","documentation"],"milestone":null}
   ```

   A body that already has a `## Step 0` block with `### Q3` and `### Q5` can replace the two flags. Passing both is an error. Raw `gh issue create` and the MCP `issue_write` tool skip this check. The Issue Provenance section of the [skill file](../../.claude/skills/github/SKILL.md) has the full rule.

3. Label an issue (outcome: you see which labels the script would add and remove). `set_issue_labels.py` adds with `--labels` and removes with `--remove-labels`. It works on issues and PRs. A missing label is created unless you pass `--no-create-missing`.

   ```bash
   uv run python "$SCRIPTS_DIR/issue/set_issue_labels.py" --issue 7214 --labels bug --remove-labels documentation --dry-run --output-format json | jq -c .Data
   ```

   ```json
   {"issue":7214,"action":"would_set_labels","dryRun":true,"wouldApply":["bug"],"wouldCreate":[],"skippedMissing":[],"wouldRemove":["documentation"],"absent":[],"reconcilesPriority":false}
   ```

   Removal runs after additions. A name cannot appear in both lists. Separate names with spaces (`--labels bug needs-triage`) or one quoted comma list (`--labels "bug,needs-triage"`). A quoted space list is one label with a space in its name.

4. Set a milestone (outcome: you see the milestone the issue would get). You can set it when you create the issue. The script checks the milestone first, so a typo fails before any issue exists.

   ```bash
   uv run python "$SCRIPTS_DIR/issue/new_issue.py" --title "Docs: example" --source human --body "Example body" --milestone v0.7.0 --dry-run --output-format json | jq -c .Data
   ```

   ```json
   {"action":"would_create","dryRun":true,"owner":"rjmurillo","repo":"ai-agents","title":"Docs: example","source":"human","labels":["source:human"],"milestone":"v0.7.0"}
   ```

   To change an issue that already exists, use `set_issue_milestone.py`:

   ```bash
   uv run python "$SCRIPTS_DIR/issue/set_issue_milestone.py" --issue 7214 --milestone v0.7.0 --dry-run --output-format json | jq -c .Data
   ```

   ```json
   {"issue":7214,"milestone":"v0.7.0","previous_milestone":null,"action":"would_assign","dry_run":true}
   ```

   If the issue already has a milestone, the script exits `1`. Add `--force` to replace it, or `--clear` to remove it.

5. Filter issues and PRs by milestone and label (outcome: you see a short list that matches both filters). `list_issues.py` takes `--milestone`, a title such as `v0.7.0` or a number. It combines with `--state`, `--label`, `--author`, and `--assignee`.

   ```bash
   uv run python "$SCRIPTS_DIR/issue/list_issues.py" --state closed --milestone v0.7.0 --label area-skills --limit 3 --output-format json | jq -c '.Data.issues | map({number, state})'
   ```

   ```json
   [{"number":7280,"state":"CLOSED"},{"number":7277,"state":"CLOSED"},{"number":7248,"state":"CLOSED"}]
   ```

   `get_pull_requests.py` filters PRs the same way, with `--label`, `--author`, `--base`, and `--head`:

   ```bash
   uv run python "$SCRIPTS_DIR/pr/get_pull_requests.py" --state open --label dependencies --limit 2 --output-format json | jq -c '.Data.PullRequests | map({number, state})'
   ```

   ```json
   [{"number":7250,"state":"OPEN"}]
   ```

   Three things to know:

   - Both scripts return at most `--limit` rows. The default is 30 and the range is 1 to 1000. A full page does not mean you saw every row. A limit is a fetch size, not a completeness bound. For a work queue, where each row is an obligation, follow the [lossless work-queue reads rule](../../.claude/rules/lossless-queue-reads.md).
   - `--search` replaces the other filters. `list_issues.py` ignores `--label`, `--author`, `--assignee`, and `--milestone` when you pass it. `get_pull_requests.py` ignores `--label`, `--author`, `--base`, and `--head`.
   - `--state closed` on `get_pull_requests.py` includes merged PRs. Read `state` on each row. Use `--state merged` for merged PRs only.

6. Merge a PR pinned to its head SHA (outcome: you see the merge the script would make, and a refusal when the SHA is wrong). Check CI first:

   ```bash
   uv run python "$SCRIPTS_DIR/pr/get_pr_checks.py" --pull-request "$PR" --output-format json | jq -c '.Data | {Number, PassedCount, FailedCount, PendingCount}'
   ```

   ```json
   {"Number":7297,"PassedCount":110,"FailedCount":0,"PendingCount":1}
   ```

   Read the head SHA, then pass it to the merge as the commit you reviewed:

   ```bash
   SHA=$(uv run python "$SCRIPTS_DIR/pr/get_pr_context.py" --pull-request "$PR" --output-format json | jq -r .Data.head_sha)
   uv run python "$SCRIPTS_DIR/pr/merge_pr.py" --pull-request "$PR" --expected-head-sha "$SHA" --strategy squash --dry-run --output-format json | jq -c '.Data | {action, dryRun, strategy, head_sha}'
   ```

   ```json
   {"action":"would_merge","dryRun":true,"strategy":"squash","head_sha":"5ec2d18a6941457a67a76f30af145561acd7c035"}
   ```

   Now pass a SHA that is not the head. The script refuses and makes no merge call:

   ```bash
   out=$(uv run python "$SCRIPTS_DIR/pr/merge_pr.py" --pull-request "$PR" --expected-head-sha 0123456789abcdef0123456789abcdef01234567 --dry-run --output-format json); echo "exit=$?"; echo "$out" | jq -c .Error
   ```

   ```text
   exit=1
   {"Message":"PR #7297 head does not match the reviewed commit: expected 0123456789abcdef0123456789abcdef01234567, actual 5ec2d18a6941457a67a76f30af145561acd7c035. Wrong PR or the branch moved after review; no merge attempted.","Code":1,"Type":"InvalidParams"}
   ```

   That refusal is the point of the pin. If someone pushes after your review, the merge stops. Review the new head, then pass the new SHA.

   A dry run checks the PR itself. GitHub applies branch protection at merge time, so a real merge can still be blocked. Exit `100` means "not mergeable". Run `why_pr_blocked.py` to see the cause. [ADR-112](../../.project-toolkit/architecture/ADR-112-risk-tiered-action-boundaries.md) covers the audit block in the real merge output.

7. Update a PR branch on the server (outcome: you see whether the PR is behind its base and whether an update would run). This is the API behind the "Update branch" button. It needs no local checkout or push.

   ```bash
   uv run python "$SCRIPTS_DIR/pr/update_pr_branch.py" --pull-request "$PR" --expected-head-sha "$SHA" --dry-run --output-format json | jq -c '.Data | {action, dry_run, behind_by, precheck}'
   ```

   ```json
   {"action":"would_update","dry_run":true,"behind_by":2,"precheck":"ok"}
   ```

   Pass `--expected-head-sha` so GitHub refuses when the head moved. Add `--wait` to poll until the PR is no longer behind. The wait defaults to 120 seconds (`--timeout-seconds`). A timeout exits `3`. If the head differs from your SHA, the script exits `1`.

8. Rerun failed jobs (outcome: you see which failed runs would be rerun). Use this for a flaky check. Do not push an empty commit. This sample uses a PR whose `PR Validation` run failed:

   ```bash
   uv run python "$SCRIPTS_DIR/pr/rerun_failed_jobs.py" --pull-request 7270 --dry-run --output-format json | jq -c '.Data | {reason, would_rerun: (.would_rerun | map({name, conclusion}))}'
   ```

   ```json
   {"reason":"dry_run","would_rerun":[{"name":"PR Validation","conclusion":"failure"}]}
   ```

   The script only works on open PRs. On a PR that is not open, it exits `1`:

   ```bash
   out=$(uv run python "$SCRIPTS_DIR/pr/rerun_failed_jobs.py" --pull-request 7255 --dry-run --output-format json); echo "exit=$?"; echo "$out" | jq -c '{message: .Error.Message}'
   ```

   ```text
   exit=1
   {"message":"PR #7255 is closed; rerunning CI on a PR that is not open spends minutes for no merge outcome"}
   ```

   It also exits `1` when every run is still going, because a run that has not finished cannot be rerun. Wait for the runs to end, then try again. Use `--run-id` to target one run, and `--job-id` with it to target one job. Exit `100` means GitHub refused the rerun. Do not retry. The `--help` text says to use a fallback.

9. Reopen a closed PR (outcome: you see that a closed PR would be reopened, and that a merged PR cannot be).

   ```bash
   uv run python "$SCRIPTS_DIR/pr/reopen_pr.py" --pull-request 7148 --dry-run --output-format json | jq -c .Data
   ```

   ```json
   {"pull_request":7148,"state":"CLOSED","action":"would_reopen","dry_run":true,"message":"Dry run: PR would be reopened; nothing changed"}
   ```

   A merged PR cannot be reopened:

   ```bash
   out=$(uv run python "$SCRIPTS_DIR/pr/reopen_pr.py" --pull-request 7255 --dry-run --output-format json); echo "exit=$?"; echo "$out" | jq -c .Error
   ```

   ```text
   exit=1
   {"Message":"PR #7255 is merged; only a closed PR can be reopened","Code":1,"Type":"InvalidParams"}
   ```

   Add `--comment "reason"` to explain the reopen. Reopening an already open PR exits `0`. Exit `3` covers API failures, timeouts, and a deleted head branch.

## Check your result

You are done when each step printed JSON with `"dryRun":true` or `"dry_run":true`, or the exit code and error shown above.

Check the redactor too. This builds a fake token and pipes it through:

```bash
printf 'deploy token=%s\n' "ghp_$(printf 'a%.0s' {1..36})" | uv run python "$SCRIPTS_DIR/issue/redact_secrets.py"
```

```text
deploy token=[redacted: github-token]
```

If a step fails, read the exit code first, then `.Error.Message`:

| Exit | Meaning | What to do |
|------|---------|------------|
| 1 | Logic error, such as a moved head or a merged PR | Read `.Error.Message`. Fix the input or re-read the PR state. |
| 2 | Bad arguments or config, or "not found" for scripts that look up a PR, issue, or milestone | Read `.Error.Message`. Fix the flag or the number. |
| 3 | GitHub or network failure | Retry once. If it repeats, run the transport check from step 1. |
| 4 | Not signed in | Sign `gh` in, then run the transport check again. |
| 100 | Script-specific refusal: not mergeable (`merge_pr.py`) or rerun refused (`rerun_failed_jobs.py`) | Do not retry the same call. Diagnose with `why_pr_blocked.py`, or use the fallback the script prints. |

An unreachable API is an unknown, not a verdict. Do not report a PR as blocked because a call failed. Run any script with `--help` to see its flags and exit codes.

## Next

Pick the right script for a task with the Decision Tree in the [skill file](../../.claude/skills/github/SKILL.md). For every flag and exit code, read the [script catalog](../../.claude/skills/github/references/script-catalog.md) and the [API reference](../../.claude/skills/github/references/api-reference.md). To link issues to each other, read [issue relationships](../../.claude/skills/github/references/issue-relationships.md).

Reference sources this page relies on:

- [GitHub skill](../../.claude/skills/github/SKILL.md)
- [GitHub API capabilities](../github-api-capabilities.md)
- [ADR-035: exit code standardization](../../.project-toolkit/architecture/ADR-035-exit-code-standardization.md)
- [ADR-112: risk-tiered action boundaries](../../.project-toolkit/architecture/ADR-112-risk-tiered-action-boundaries.md)
