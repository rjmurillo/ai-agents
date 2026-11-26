# ADR-057 claims ledger, 2026-11-25

Claims in the 2026-11-25 amendment or edited sentences of ADR-057. The owner-statement row is `NOT RUN`: it names a source this ledger did not re-query, so the amendment attributes it to the owner and does not assert it as a measurement.

Commands ran in the working tree of branch `ci/delete-agent-env-jobs` at head `7cfb378901` with the ADR amendments uncommitted. The deletion commit is `3f145f26fd` on base `e74b842786`.

| Claim | Kind | Command | Result |
|---|---|---|---|
| slash-command-quality.yml no longer exists | absence | `test ! -e .github/workflows/slash-command-quality.yml && echo absent` | VERIFIED: absent |
| advisory_agent_workflows no longer lists slash-command-quality | absence | `grep -c 'slash-command-quality' src/claude/skills/pr-review/pr-review-config.yaml` | VERIFIED: 0 |
| No workflow invokes eval-prompt-change.py | absence | `grep -rln 'eval-prompt-change' .github \| wc -l` | VERIFIED: 0 |
| The acceptance gate returns FAIL on a regression when run | behavior | `uv run pytest tests/eval/test_eval_prompt_change.py -q -k test_regression_fails_gate` (asserts `gate["passed"] is False` at test line 1004) | VERIFIED: 1 passed, 149 deselected in 0.16s |
| tests/evals/spec-scenarios.json still exists (scenario set cited in the edited sentence) | path | `test -f tests/evals/spec-scenarios.json && echo present` | VERIFIED: present |
| Owner statement: latest 100 deployments of agent-claude and agent-copilot show none approved or run | quote | `echo 'owner statement in the task brief, 2026-11-25; not re-queried'` | NOT RUN: owner statement in the task brief, 2026-11-25; not re-queried |

## Second pass, 2026-11-25

Rows for the reworded first sentences of the 2026-11-25 amendment (the owner's stated reason and its scope). Commands ran on 2026-11-25 in the working tree of branch `ci/delete-agent-env-jobs` at head `879dff55b3` with the ADR amendments uncommitted. The deletion commit is `3f145f26fd` (2026-11-25).

| Claim | Kind | Command | Result |
|---|---|---|---|
| Commit 637b60d749 is a bot stats commit dated 2026-11-13 | behavior | `git log -1 --format='%h %cs %an %s' 637b60d749` | VERIFIED: 637b60d749 2026-11-13 github-actions[bot] chore(stats): update reviewer signal statistics (#7327) |
| That commit title is what the reviewer-stats workflow writes | behavior | `git show 637b60d749:.github/workflows/update-reviewer-stats.yml \| grep -n 'update reviewer signal statistics' \| head -n 2 \| tr '\n' ' '` | VERIFIED: 165: --message "chore(stats): update reviewer signal statistics" \ |
| update-stats declared agent-claude from commit d73c0cf0fe (2026-11-05) | behavior | `git log -1 --format='%h %cs' d73c0cf0fe; git show d73c0cf0fe:.github/workflows/update-reviewer-stats.yml \| grep -n 'environment: agent-claude' \| tr '\n' ' '` | VERIFIED: d73c0cf0fe 2026-11-05 39: environment: agent-claude |
| The parent of d73c0cf0fe did not declare it | absence | `git show d73c0cf0fe^:.github/workflows/update-reviewer-stats.yml \| grep -c 'environment: agent-claude'` | VERIFIED: 0 |
| At 637b60d749 the job still declared it | behavior | `git show 637b60d749:.github/workflows/update-reviewer-stats.yml \| grep -n 'environment: agent-claude' \| tr '\n' ' '` | VERIFIED: 57: environment: agent-claude |
| Owner statement: the latest 100 deployments of agent-claude and agent-copilot show none approved or run | quote | none: the source is the owner's statement, not a query this ledger ran | NOT RUN: attributed to the owner in the ADR text, with the window stated |

## Third pass, 2026-11-26

Rows for the text the reduced panel added on 2026-11-26: the decision-maker line and the rewritten clause about commit `637b60d749` (2026-11-13). Commands ran on 2026-11-26 in the working tree of branch `ci/delete-agent-env-jobs` at head `879dff55b3` with the ADR amendments uncommitted. The deletion commit is `3f145f26fd` (2026-11-25).

| Claim | Kind | Command | Result |
|---|---|---|---|
| Commit 637b60d749 changes a metrics report and a memory file | behavior | `git show --format= --name-only 637b60d749 \| tr '\n' ' '` | VERIFIED: .project-toolkit/metrics/agent-pr-intervention.md .serena/memories/pr-review/pr-comment-responder-skills.md |
| That report says it was generated 2026-11-12 | quote | `git show 637b60d749:.project-toolkit/metrics/agent-pr-intervention.md \| grep -o -m1 'Generated 2026-11-12 from GitHub PR events'` | VERIFIED: Generated 2026-11-12 from GitHub PR events |
| At 637b60d749 the report is built and uploaded inside `update-stats` (lines 53 to 114) | behavior | `git show 637b60d749:.github/workflows/update-reviewer-stats.yml \| sed -n '53,114p' \| grep -c -E 'agent-intervention\|upload-artifact'` | VERIFIED: 3 |
| At 637b60d749 `publish-stats` starts at line 115, needs `update-stats`, and declares no environment | behavior | `git show 637b60d749:.github/workflows/update-reviewer-stats.yml \| sed -n '115,200p' \| grep -n -E '^    needs:\|^    environment:\|download-artifact@\|open_bot_pr.py' \| cut -c1-60 \| tr '\n' ' '` | VERIFIED: 6:    needs: update-stats 30:        uses: actions/download-artifact@9000827ccba6bdab6 43:          python3 -I scripts/ci/open_bot_pr.py \ |
| The two-job layout landed in 4273c7d5e2 (2026-11-11) | behavior | `git log -1 --format='%h %ad %s' --date=short 4273c7d5e2` | VERIFIED: 4273c7d5e2 2026-11-11 fix(ci): publish reviewer stats through a bot pull request (#7317) |
| Commit 3f145f26fd deleted the slash-command-quality workflow | behavior | `git show --format= --name-status 3f145f26fd -- .github/workflows \| grep -i 'slash-command' \| tr '\t' ' '` | VERIFIED: D .github/workflows/slash-command-quality.yml |
| The first debate log named in the pointer line exists | path | `ls .project-toolkit/critique/agent-env-adr-amendments-2026-11-25-debate-log.md` | VERIFIED: .project-toolkit/critique/agent-env-adr-amendments-2026-11-25-debate-log.md |
| The merged pull request body calls the commit scheduled workflow output | quote | `git log -1 --format=%b 637b60d749 \| grep -o -m1 'Scheduled workflow output committed on a bot branch'` | VERIFIED: Scheduled workflow output committed on a bot branch |
