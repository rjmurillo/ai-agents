# Agent PR Intervention Metrics

Generated 2026-11-12 from GitHub PR events. Window: PRs created 2026-10-13 to 2026-11-12 (30 days). Agent-authored PRs in window: 565.

| Outcome | PRs | Zero-touch | Zero-intervention rate | Interventions | Median per intervened PR |
|---------|-----|------------|------------------------|---------------|--------------------------|
| merged | 555 | 344 | 62.0% | 589 | 2 |
| unmerged | 8 | 5 | 62.5% | 4 | 1 |
| open | 2 | 1 | 50.0% | 1 | 1 |

## Zero-touch merge sample

10 of 344 merged PRs with zero interventions, picked at even steps through the PR-number order, newest first.

- [#7324](https://github.com/rjmurillo/ai-agents/pull/7324): `docs(memory): record four first-principles findings from the issue sweep`
- [#7243](https://github.com/rjmurillo/ai-agents/pull/7243): `fix(build): flag and prune rendered output when its template is deleted`
- [#7090](https://github.com/rjmurillo/ai-agents/pull/7090): `fix(github): report refused sessions as unknown in the completion gate`
- [#6946](https://github.com/rjmurillo/ai-agents/pull/6946): `feat(eval): explicit prompt caching for GPT-5.6+ eval requests`
- [#6856](https://github.com/rjmurillo/ai-agents/pull/6856): `fix(validation): analyze each plugin-root script once per scan`
- [#6779](https://github.com/rjmurillo/ai-agents/pull/6779): `fix(validation): stop a stray Provenance bullet sourcing the last table row (follow-up to #6695)`
- [#6729](https://github.com/rjmurillo/ai-agents/pull/6729): `fix(testing): fall back to ~/worktrees when the checkout parent is unwritable`
- [#6582](https://github.com/rjmurillo/ai-agents/pull/6582): `docs(memory): mark LSP escape hatch memories as retired`
- [#6534](https://github.com/rjmurillo/ai-agents/pull/6534): `test(mutation): run every mutation harness in a blocking CI job`
- [#6491](https://github.com/rjmurillo/ai-agents/pull/6491): `fix(rules): resolve the remaining ADR-109 B2 rule content findings`

## Definitions

- **Agent-authored PR.** The author is a `repository` bot in `.github/bot-authors.yml`, or the
  repository owner opened it and the body carries the `Generated with [Claude Code]` trailer.
  Agent PRs here are opened under the owner's login, so the author alone misses almost all of
  them. The trailer is trusted only on the owner's PRs, because anyone can type it.
- **Human intervention.** One of: a review thread whose first comment is by a non-bot, or a
  `CHANGES_REQUESTED` review by a non-bot. Each counts once, so one such review plus two
  human-opened threads is three. A bot is an actor GitHub types as a bot, or a login listed in
  `bot-authors.yml`. A login suffix such as `-bot` is not enough.
- **Not an intervention.** Any bot comment or review. Replies inside a bot-opened thread, because
  the agent replies under the same login as the owner. An approval with no comment. A comment
  that is not a review thread (issue-level comments). An unattributable (deleted) account counts
  as human, so it can never hide an intervention.
- **Zero-intervention rate.** PRs with zero interventions divided by all PRs in the row.
- **Median per intervened PR.** Median intervention count over PRs with at least one.
- **Rows.** `merged`, `unmerged` (closed without merge), and `open` (still in flight).
- **Window.** PRs created in the trailing 30 days.
- **Data source.** GitHub PR events only. Session logs are not used. PRs that are not
  agent-authored arrive with the first page of the PR list, are classified, and are dropped in
  memory. Nothing about them is paged further, stored, or reported.

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
