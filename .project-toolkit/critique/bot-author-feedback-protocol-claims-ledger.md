# bot-author-feedback-protocol claims ledger, 2026-11-26

Commands ran on 2026-11-26 in the working tree of branch `ci/delete-agent-env-jobs` at head `879dff55b3` (2026-11-26) with the amendments uncommitted. The deletion commit is `3f145f26fd` (2026-11-25). These rows cover the note `**State since 2026-11-25**` and the three labels changed with it.

| Claim | Kind | Command | Result |
|---|---|---|---|
| The process-prs job was deleted from pr-maintenance.yml by 3f145f26fd (job key count before, after) | count | `git show 3f145f26fd^:.github/workflows/pr-maintenance.yml \| grep -c '^  process-prs:$'; grep -c '^  process-prs:$' .github/workflows/pr-maintenance.yml` | VERIFIED: 1 0 |
| process-prs declared an agent-* environment | behavior | `git show 3f145f26fd^:.github/workflows/pr-maintenance.yml \| grep -n 'environment:' \| tr '\n' ' '` | VERIFIED: 103: environment: agent-claude |
| The workflow runs hourly | behavior | `grep -n 'cron' .github/workflows/pr-maintenance.yml` | VERIFIED: 6: - cron: '0 * * * *' # Hourly at minute 0 (UTC) |
| Two jobs remain: discover-prs and summarize | count | `awk '/^jobs:/{j=1} j && /^  [a-z-]+:$/{print NR": "$1}' .github/workflows/pr-maintenance.yml \| tr '\n' ' '` | VERIFIED: 27: discover-prs: 85: summarize: |
| Both jobs are read-only (permission values in the file; count of write values) | absence | `grep -n -E '^ +[a-z-]+: (read\|write)$' .github/workflows/pr-maintenance.yml \| tr '\n' ' '; grep -c ': write' .github/workflows/pr-maintenance.yml` | VERIFIED: 16: contents: read 33: checks: read 34: contents: read 35: pull-requests: read 36: statuses: read 91: contents: read 92: issues: read 93: pull-requests: read 0 |
| The workflow runs seven python invocations: a rate-limit check, PR discovery, two summary writers, an advisory wrapper around an orphan-commit detector, and a supersession report | count | `grep -n -o 'python3 [a-z_./]*' .github/workflows/pr-maintenance.yml \| tr '\n' ' '` | VERIFIED: 50:python3 .github/scripts/test_rate_limit.py 57:python3 .github/scripts/invoke_pr_maintenance.py 68:python3 scripts/ci/write_pr_discovery_summary.py 78:python3 scripts/ci/report_advisory_result.py 82:python3 scripts/maintenance/detect_orphan_commits.py 103:python3 scripts/ci/write_pr_maintenance_summary.py 111:python3 scripts/report_pr_supersession.py |
| The discovery script holds no GraphQL mutation (count of the word in the file) | absence | `grep -c -i 'mutation' .github/scripts/invoke_pr_maintenance.py` | VERIFIED: 0 |
| The workflow reads no repository secret, so every call uses the job token with the read permissions above (count of secret references; token lines) | behavior | `grep -c 'secrets\.' .github/workflows/pr-maintenance.yml; grep -n -E 'TOKEN\|github.token' .github/workflows/pr-maintenance.yml \| cut -c1-90 \| tr '\n' ' '` | VERIFIED: 0 30: # The discovery query reads statusCheckRollup, so github.token needs 49: GH_TOKEN: ${{ github.token }} 55: GH_TOKEN: ${{ github.token }} 66: GH_TOKEN: ${{ github.token }} 76: GH_TOKEN: ${{ github.token }} 101: GH_TOKEN: ${{ github.token }} 110: GH_TOKEN: ${{ github.token }} |
| No step in the workflow calls the comment-processing or conflict-resolution scripts | absence | `grep -c -E 'invoke_pr_comment_processing\|apply_ai_conflict_resolution\|resolve_pr_conflicts' .github/workflows/pr-maintenance.yml` | VERIFIED: 0 |

The sentence "The conflict resolution and comment processing described below run only when a person or an agent session starts them" rests on the last absence row, which searched this one workflow. A search of every workflow follows.

| Claim | Kind | Command | Result |
|---|---|---|---|
| No workflow or action calls the comment-processing or conflict-resolution scripts (count of matching lines under .github/workflows and .github/actions) | absence | `git grep -n -E 'invoke_pr_comment_processing\|apply_ai_conflict_resolution\|resolve_pr_conflicts' -- .github/workflows .github/actions \| wc -l` | VERIFIED: 0 |

## Rows after the panel round of 2026-11-26

Rows added on 2026-11-26 after the panel round of that date, for sentences the round changed. Same working tree, head `879dff55b3` (2026-11-26), amendments uncommitted.

| Claim | Kind | Command | Result |
|---|---|---|---|
| The deleted process-prs job held the write permissions | behavior | `git show 3f145f26fd^:.github/workflows/pr-maintenance.yml \| awk 'NR>=103 && NR<=111 && /environment\|write/{print NR": "$0}'` | VERIFIED: 103:     environment: agent-claude / 109:       contents: write / 110:       pull-requests: write / 111:       issues: write |
| The doc lines the state note now names | quote | `sed -n '91p;603p;612p' .project-toolkit/architecture/bot-author-feedback-protocol.md` | VERIFIED: - **GitHub Actions**: `GITHUB_TOKEN` with `repo`, `workflow`, `pull_requests:write` / - **Comment acknowledgment rate**: >95% / \| Zero actions \| >24 hours \| Verify scheduled workflow enabled \| |
