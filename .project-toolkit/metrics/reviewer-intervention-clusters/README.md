# Reviewer intervention clusters

A job, scheduled daily when its workflow is enabled, counts repeated human
corrections on agent pull requests. A repeat
means a lesson was not carried forward. The job reports; it never edits a rule,
contract, or prompt, and it files no issue (issue #7153).

## Files

| File | Role |
|---|---|
| `report.json` | Latest report. Overwritten each run. |
| `src/claude/skills/skill-bootstrap/scripts/review_clusters.py` | Cluster definition, population rules, and counting. Stdlib only. It lives in a shipped skill so the skill-bootstrap consumer (#7155) imports it and counts the same way. |
| `scripts/reviewer_intervention_fetch.py` | Lossless GraphQL reads of pull requests and review threads. |
| `scripts/report_reviewer_intervention_clusters.py` | Filters to the population, clusters, writes `report.json`. |
| `.github/workflows/update-reviewer-stats.yml` | Holds the step `Cluster repeated review interventions`, scheduled daily at 06:00 UTC when the workflow is enabled. See Status. |

## Status

As of 2026-11-11 the schedule is not running. `update-reviewer-stats.yml` has
been disabled since 2026-10-26, and the default-branch ruleset lets only the
Admin role bypass its pull request rule, so the commit step's push is rejected.
Issue #7287 tracks both. Until it is resolved the report refreshes only when a
person runs `scripts/report_reviewer_intervention_clusters.py` and commits the
result. The committed `report.json` is the 2026-11-11 run.

## Cluster definition

The signals, threshold, window, and area depth were fixed before the first run.
The population was corrected three times afterward; see Population correction. Change
the definition only in a reviewed pull request that states why, never to move a
count.

- **Agent pull request:** the body carries `Generated with [Claude Code]` and its author has OWNER, MEMBER, or COLLABORATOR standing, or its author is a bot account (`github_core.bot_config.is_bot`). Dependency bots (dependabot, renovate) are excluded. Agents here open pull requests under the owner's login, so the trailer is the usable marker. The standing check stops an outside contributor from marking a pull request as agent-made.
- **Intervention:** the first comment of a review thread. The author is not a bot and has OWNER, MEMBER, or COLLABORATOR standing on the repository, so an outsider's own comment never counts. The pull request author is not excluded, because on a trailer pull request the owner is both nominal author and human reviewer. Later replies do not count.
- **Window:** 90 days. A thread counts when its first comment was created in the trailing 90 days.
- **Threshold:** 3.

Three signals, all explicit. The job compares no free text.

| Signal | Key | Counts |
|---|---|---|
| `rule` | `ADR-NNN`, or `rules/<name>` from a `rules/<name>.md` path in the comment body | distinct pull requests |
| `area` | directory of the commented file, cut to its first 4 segments; a path with a segment outside `[A-Za-z0-9._@+-]` has no area signal | distinct pull requests |
| `disposition` | the `disposition` value in `.project-toolkit/pr-checks/suppressed-finding-dispositions.json` | distinct registry entries |

A cluster is one `(signal, key)` pair at or above the threshold. Two threads on
one pull request count once.

The disposition registry holds no pull request number and no date. Its entries
cannot join the window or the distinct-pull-request count, so that signal counts
entries over the whole file. An empty registry gives zero disposition clusters.

## Population correction

The first run used the author login alone to find agent pull requests and
excluded comments by the pull request author. On 2026-11-11 that read 295
pull requests of 1621 examined and kept 0 interventions. The filter had
removed the owner's own pull requests and threads, so the zero measured the
filter, not the repository. The population above replaces it. Threshold,
window, signals, and area depth did not change, and no cluster count was
read before the change.

A second correction followed a security review. A thread now counts only when
its first comment has OWNER, MEMBER, or COLLABORATOR standing. Without it, an
outside contributor could put the trailer in a pull request body and comment on
it to mint a cluster. The cluster count was 36 before and after the change.

A third correction followed the review of that change. The trailer now counts
only when the pull request author also has OWNER, MEMBER, or COLLABORATOR
standing. Before it, a maintainer's thread on an outsider's forged-trailer pull
request counted. No cluster count was read to decide it, and the population
rules moved into the shared module so the skill-bootstrap consumer counts the
same way. The same change counts only a GraphQL `Bot` actor as a bot author, so a
`User` account whose name ends in `-bot` earns no agent status. The count was 36
clusters from 755 interventions before and after.

Known limit: an agent that opens a thread under the owner's login cannot be
told from the owner. Such a thread counts as an intervention.
`interventions_by_pr_author` in `examined` counts the threads opened under the
pull request author's login. On 2026-11-11 that was 755 of 755, so the bound is
the whole population: no cluster is shown to rest on a correction by a different
human, and the report counts owner-login threads on agent pull requests without
proving a human wrote each one.

A sample read on 2026-11-11 points the other way. Of the 106 interventions on
pull requests updated in the six days to that date, 30 drawn at random were long,
structured findings with file and line references and exact quotes of the diff.
That is consistent with agent-written review posted under the owner's login, and
the API does not say who typed them. Read the clusters as repeated review
findings under the owner's login. Do not read them as proven human corrections
until a signal separates the two, such as a distinct agent account or a marker on
the comment.

## Reading a result

- `examined` states how much was read: pull requests, agent pull requests, trailer pull requests, interventions, interventions in the window, dispositions, and the filter funnel (`threads_seen`, `threads_without_comments`, `threads_excluded_bot_or_unknown`, `threads_excluded_no_standing`, `interventions_by_pr_author`, `duplicate_pull_requests_skipped`). Zero clusters next to a large `examined` means nothing recurred. Zero next to a small one means little was read. A jump in a funnel count explains a jump in the result.
- A cluster proves the same marker recurred on three or more pull requests. It does not prove the corrections shared a cause. Read the `evidence` list.
- An `area` cluster in a busy directory can be volume, not a lesson. The report carries no per-area denominator.
- A symlinked tree can appear under two area keys, such as a mirrored skill directory. The module does not fold them.
- Cluster keys come from comment text and file paths a contributor influences. A consumer treats them as data and escapes them.
- A cluster whose fix is skill-shaped routes through a `skill-bootstrap` run. A cluster whose fix is a gate or a contract clause goes to the owner as an issue the owner files.

## Prerequisites

The job runs inside `update-reviewer-stats.yml`, so that workflow must be
enabled. Its commit step pushes to the default branch, so the workflow token
must be allowed to push there; a branch ruleset that requires pull requests
rejects the push. The commit step rebases onto the default branch before it pushes, so a branch
that moved during the run does not reject the push. Any failed push leaves the
previous `report.json` in place and the step red; the next run replaces it.

One run cost 421 GraphQL points on 2026-11-11 (33 pages, 1641 pull requests;
858 before the thread page size dropped from 50 to 20). The job stops with exit 3
when fewer than 100 points remain, so it does not empty a budget other jobs
share.

## Reads are lossless

Pull requests arrive newest-update first. The walk ends at the first one older
than the 90-day window, because a comment inside the window implies a pull
request updated inside it. Every page and every review thread inside that bound
is read until the API reports no next page. A missing cursor, a null node, or a
page cap stops the run with exit 3 and writes nothing. A partial report is never
committed.

A pull request updated while the walk runs can jump ahead of the cursor. The
next daily run reads it. A repeated pull request is skipped and counted.

## Exit codes

| Code | Meaning |
|---|---|
| 0 | Report written. Zero clusters is a success. |
| 2 | Bad arguments, an unreadable or malformed dispositions file, or a path outside its allowed directory. |
| 3 | API failure or timeout, incomplete pagination, or malformed API data. No report is written. |
| 4 | Authentication or permission failure. A rate-limit response is exit 3. |
