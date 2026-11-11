# Agent PR Intervention Metrics

Generated 2026-11-11 from GitHub PR events. Window: PRs created 2026-10-12 to 2026-11-11 (30 days). Agent-authored PRs in window: 591.

| Outcome | PRs | Zero-touch | Zero-intervention rate | Interventions | Median per intervened PR |
|---------|-----|------------|------------------------|---------------|--------------------------|
| merged | 578 | 349 | 60% | 665 | 2 |
| unmerged | 5 | 4 | 80% | 1 | 1 |
| open | 8 | 5 | 62% | 5 | 1 |

## Zero-touch merge sample

10 of 349 merged PRs with zero interventions, spread across the window, newest first.

- [#7256](https://github.com/rjmurillo/ai-agents/pull/7256): `fix(build): reword Cursor handoffs to the unshipped security agent`
- [#7073](https://github.com/rjmurillo/ai-agents/pull/7073): `feat(hooks): friction branch in the Stop retrospective nudge (REQ-048 TASK-003)`
- [#6937](https://github.com/rjmurillo/ai-agents/pull/6937): `fix(tests): join api-doc-authoring test server threads before each test ends`
- [#6850](https://github.com/rjmurillo/ai-agents/pull/6850): `docs(eval): record the S7 baseline versus full run for the reframing check`
- [#6776](https://github.com/rjmurillo/ai-agents/pull/6776): `fix(evals): key dates.py fix check on the crashing call (follow-up to #6687)`
- [#6723](https://github.com/rjmurillo/ai-agents/pull/6723): `fix(memory): keep dangling commit events when dropping all would zero commits`
- [#6572](https://github.com/rjmurillo/ai-agents/pull/6572): `docs(skills): host global workflow rules in decision-question, orchestrator, test`
- [#6528](https://github.com/rjmurillo/ai-agents/pull/6528): `fix(github): report reply_posted separately in add_pr_review_thread_reply.py`
- [#6470](https://github.com/rjmurillo/ai-agents/pull/6470): `feat(github): add --check-name filter and failed step names to get_pr_check_logs`
- [#6345](https://github.com/rjmurillo/ai-agents/pull/6345): `perf(hooks): run pre-push pytest partitions at the same time`

## Definitions

- **Agent-authored PR.** The PR body carries the `Generated with [Claude Code]` trailer, or the
  author canonicalizes to a `repository` bot in `.github/bot-authors.yml`. Agent PRs here are
  opened under the owner's login, so the author alone misses almost all of them.
- **Human intervention.** One of: a review thread whose first comment is by a non-bot, or a
  `CHANGES_REQUESTED` review by a non-bot. Each counts once.
- **Not an intervention.** Any bot comment or review. Replies inside a bot-opened thread, because
  the agent replies under the same login as the owner. An approval with no comment. A comment
  that is not a review thread (issue-level comments). An unattributable (deleted) account counts
  as human, so it can never hide an intervention.
- **Zero-intervention rate.** PRs with zero interventions divided by all PRs in the row.
- **Median per intervened PR.** Median intervention count over PRs with at least one.
- **Rows.** `merged`, `unmerged` (closed without merge), and `open` (still in flight).
- **Window.** PRs created in the trailing 30 days.
- **Data source.** GitHub PR events only. Session logs are not used. PRs that are not
  agent-authored are read to classify them and are not stored or reported.

## Known limits

- The owner's login is shared with the agent. A thread opened under it counts as an
  intervention even when the agent opened it (for example a self-review). So the count can
  overstate human effort on PRs with threads.
- A human who corrects the agent inside a bot-opened thread, under the owner's login, is
  invisible. So the zero-touch rate can overstate how often nobody stepped in. The zero-touch
  sample exists so a person can spot-check that zero-touch meant done, not ignored.
- Iterations before the first intervention are not measured. They need session logs, which are
  no longer created.
- No targets or thresholds. This is a baseline. Metrics aggregate over PRs, not people.
