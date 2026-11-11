# Reviewer intervention clusters

A daily job counts repeated human corrections on agent pull requests. A repeat
means a lesson was not carried forward. The job reports; it never edits a rule,
contract, or prompt, and it files no issue (issue #7153).

## Files

| File | Role |
|---|---|
| `report.json` | Latest report. Overwritten each run. |
| `src/claude/skills/skill-bootstrap/scripts/review_clusters.py` | Cluster definition and counting. Stdlib only. |
| `scripts/report_reviewer_intervention_clusters.py` | Fetches pull requests, writes `report.json`. |
| `.github/workflows/update-reviewer-stats.yml` | Runs the job daily at 06:00 UTC, step `Cluster repeated review interventions`. |

## Cluster definition

This definition was fixed before the first run. Change it only in a reviewed
pull request that states why, never to move a count.

- **Agent pull request:** the body carries `Generated with [Claude Code]`, or the author is a bot account (`github_core.bot_config.is_bot`). Dependency bots (dependabot, renovate) are excluded. Agents here open pull requests under the owner's login, so the trailer is the usable marker.
- **Intervention:** the first comment of a review thread. The author is not a bot. The pull request author is not excluded, because on a trailer pull request the owner is both nominal author and human reviewer. Later replies do not count.
- **Window:** 90 days. A thread counts when its first comment was created in the trailing 90 days.
- **Threshold:** 3.

Three signals, all explicit. The job compares no free text.

| Signal | Key | Counts |
|---|---|---|
| `rule` | `ADR-NNN`, or `rules/<name>` from a `rules/<name>.md` path in the comment body | distinct pull requests |
| `area` | directory of the commented file, cut to its first 4 segments | distinct pull requests |
| `disposition` | the `disposition` value in `.project-toolkit/pr-checks/suppressed-finding-dispositions.json` | distinct registry entries |

A cluster is one `(signal, key)` pair at or above the threshold. Two threads on
one pull request count once.

The disposition registry holds no pull request number and no date. Its entries
cannot join the window or the distinct-pull-request count, so that signal counts
entries over the whole file. An empty registry gives zero disposition clusters.

## Population correction

The first run used the author login alone to find agent pull requests and
excluded comments by the pull request author. On 2026-11-10 that read 295
pull requests of 1621 examined and kept 0 interventions. The filter had
removed the owner's own pull requests and threads, so the zero measured the
filter, not the repository. The population above replaces it. Threshold,
window, signals, and area depth did not change, and no cluster count was
read before the change.

Known limit: an agent that opens a thread under the owner's login cannot be
told from the owner. Such a thread counts as an intervention.

## Reading a result

- `examined` states how much was read: pull requests, agent pull requests, trailer pull requests, interventions, interventions in the window, dispositions. Zero clusters next to a large `examined` means nothing recurred. Zero next to a small one means little was read.
- A cluster proves the same marker recurred on three or more pull requests. It does not prove the corrections shared a cause. Read the `evidence` list.
- An `area` cluster in a busy directory can be volume, not a lesson.
- A cluster whose fix is skill-shaped routes through a `skill-bootstrap` run. A cluster whose fix is a gate or a contract clause goes to the owner as an issue the owner files.

## Reads are lossless

The job pages every pull request and every review thread until the API reports
no next page. A missing cursor or a page cap stops the run with exit 3 and
writes nothing. A partial report is never committed.

## Exit codes

| Code | Meaning |
|---|---|
| 0 | Report written. Zero clusters is a success. |
| 2 | Bad arguments, unreadable dispositions file, or output path outside the repository. |
| 3 | API failure or incomplete pagination. |
| 4 | Authentication failure. |
