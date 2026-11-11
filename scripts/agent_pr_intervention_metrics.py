"""Human-intervention metrics for agent-authored pull requests (issue #7154).

Measures, from PR events only, how often a human had to step in on a PR that
an agent wrote. Session logs are not a source: session log creation is
discontinued (``universal.md`` MUST NOT 10), so the "iterations before the
first intervention" metric from the issue is out of scope.

Called by ``scripts/update_reviewer_signal_stats.py --agent-intervention`` on
the ``update-reviewer-stats.yml`` cadence. Kept in its own module so the
reviewer-signal functions in that script stay untouched.

Definitions (also rendered into the report):

* Agent-authored PR: the body carries the Claude Code trailer, or the author
  canonicalizes to a ``repository`` bot in ``.github/bot-authors.yml``. Agent
  PRs here are opened under the owner's login, so the author login alone
  misses almost all of them.
* Human intervention: a review thread whose first comment is by a non-bot, or
  a ``CHANGES_REQUESTED`` review by a non-bot. Replies inside a bot-opened
  thread are not counted, because the agent replies under the same login as
  the owner. An approval with no comment is not an intervention.
* Zero-intervention rate: PRs with zero interventions over all PRs in the cohort.
"""

from __future__ import annotations

import os
import re
import statistics
import tempfile
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from scripts.github_core.api import gh_graphql
from scripts.github_core.bot_config import canonicalize_login, get_bot_authors, is_bot

INTERVENTION_WINDOW_DAYS = 30
ZERO_TOUCH_SAMPLE_SIZE = 10
MAX_PR_PAGES = 100
MAX_NESTED_PAGES = 50
REPORT_PATH = ".project-toolkit/metrics/agent-pr-intervention.md"

AGENT_TRAILER_PATTERN = re.compile(r"Generated with \[Claude Code\]", re.IGNORECASE)

MERGED = "merged"
UNMERGED = "unmerged"
OPEN = "open"
STATUSES = (MERGED, UNMERGED, OPEN)

_ACTOR_FIELDS = """\
login
__typename
... on Bot { databaseId }
... on User { databaseId }"""

_PRS_QUERY = """\
query($owner: String!, $repo: String!, $cursor: String) {
  repository(owner: $owner, name: $repo) {
    pullRequests(first: 50, orderBy: {field: CREATED_AT, direction: DESC}, after: $cursor) {
      pageInfo { hasNextPage endCursor }
      nodes {
        id
        number
        title
        url
        state
        merged
        createdAt
        mergedAt
        body
        author { __ACTOR__ }
        reviews(first: 100) {
          pageInfo { hasNextPage endCursor }
          nodes { state author { __ACTOR__ } }
        }
        reviewThreads(first: 100) {
          pageInfo { hasNextPage endCursor }
          nodes { comments(first: 1) { nodes { author { __ACTOR__ } } } }
        }
      }
    }
  }
}""".replace("__ACTOR__", _ACTOR_FIELDS)

# Selection for each nested connection, used when a PR overflows the first page.
_NESTED_SELECTIONS = {
    "reviews": "nodes { state author { __ACTOR__ } }".replace("__ACTOR__", _ACTOR_FIELDS),
    "reviewThreads": "nodes { comments(first: 1) { nodes { author { __ACTOR__ } } } }".replace(
        "__ACTOR__", _ACTOR_FIELDS
    ),
}

_NESTED_QUERY = """\
query($id: ID!, $cursor: String) {
  node(id: $id) {
    ... on PullRequest {
      __CONNECTION__(first: 100, after: $cursor) {
        pageInfo { hasNextPage endCursor }
        __SELECTION__
      }
    }
  }
}"""


@dataclass
class CohortStats:
    """Counts for one outcome bucket of agent PRs."""

    prs: int = 0
    zero_touch: int = 0
    interventions: int = 0
    intervened_counts: list[int] = field(default_factory=list)

    @property
    def zero_rate(self) -> float | None:
        """Zero-intervention rate, or None for an empty cohort."""
        return self.zero_touch / self.prs if self.prs else None

    @property
    def median_when_intervened(self) -> float | None:
        """Median intervention count over PRs that had at least one."""
        return statistics.median(self.intervened_counts) if self.intervened_counts else None


@dataclass
class InterventionMetrics:
    """Cohort stats per outcome plus the merged zero-touch spot-check list."""

    window_start: datetime
    window_end: datetime
    cohorts: dict[str, CohortStats]
    zero_touch_merged: list[dict[str, Any]]

    @property
    def total_prs(self) -> int:
        return sum(c.prs for c in self.cohorts.values())


# ---------------------------------------------------------------------------
# Classification
# ---------------------------------------------------------------------------


def _repository_bots() -> set[str]:
    """Lowercased ``repository`` bot logins with any ``[bot]`` suffix removed."""
    return {b.lower().removesuffix("[bot]") for b in get_bot_authors("repository")}


def is_agent_pr(pr: dict[str, Any]) -> bool:
    """Return True when the PR body or author marks it as agent-authored."""
    if AGENT_TRAILER_PATTERN.search(pr.get("body") or ""):
        return True
    author = pr.get("author") or {}
    login = canonicalize_login(author.get("login") or "", author.get("databaseId"))
    return login.lower().removesuffix("[bot]") in _repository_bots() if login else False


def _is_human(actor: dict[str, Any] | None) -> bool:
    """Return True unless the actor is a known bot.

    A null actor (deleted account) counts as human. A zero-touch claim has to
    be provable, so an unattributable event must not hide an intervention.
    """
    if not actor:
        return True
    login = actor.get("login") or ""
    if actor.get("__typename") == "Bot":
        return False
    return not is_bot(canonicalize_login(login, actor.get("databaseId")))


def count_interventions(pr: dict[str, Any]) -> int:
    """Count human-opened review threads plus human CHANGES_REQUESTED reviews."""
    threads = (pr.get("reviewThreads") or {}).get("nodes") or []
    opened_by_human = 0
    for thread in threads:
        first = ((thread.get("comments") or {}).get("nodes") or [None])[0]
        if first is not None and _is_human(first.get("author")):
            opened_by_human += 1

    reviews = (pr.get("reviews") or {}).get("nodes") or []
    changes_requested = sum(
        1 for r in reviews if r.get("state") == "CHANGES_REQUESTED" and _is_human(r.get("author"))
    )
    return opened_by_human + changes_requested


def pr_status(pr: dict[str, Any]) -> str:
    """Return ``merged``, ``unmerged`` (closed without merge) or ``open``."""
    if pr.get("merged"):
        return MERGED
    return OPEN if pr.get("state") == "OPEN" else UNMERGED


def _parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


# ---------------------------------------------------------------------------
# Aggregation and rendering
# ---------------------------------------------------------------------------


def _evenly_spaced(items: list[dict[str, Any]], size: int) -> list[dict[str, Any]]:
    """Pick ``size`` items spread across the list so the sample spans the window."""
    if len(items) <= size:
        return list(items)
    step = len(items) / size
    return [items[int(i * step)] for i in range(size)]


def build_metrics(
    prs: list[dict[str, Any]], window_start: datetime, window_end: datetime
) -> InterventionMetrics:
    """Aggregate agent PRs created inside the window. Other PRs are discarded."""
    cohorts = {status: CohortStats() for status in STATUSES}
    zero_touch_merged: list[dict[str, Any]] = []

    for pr in prs:
        created = _parse_time(pr["createdAt"])
        if not window_start <= created <= window_end or not is_agent_pr(pr):
            continue
        count = count_interventions(pr)
        status = pr_status(pr)
        cohort = cohorts[status]
        cohort.prs += 1
        cohort.interventions += count
        if count == 0:
            cohort.zero_touch += 1
            if status == MERGED:
                zero_touch_merged.append(
                    {"number": pr["number"], "title": pr["title"], "url": pr["url"]}
                )
        else:
            cohort.intervened_counts.append(count)

    zero_touch_merged.sort(key=lambda p: p["number"], reverse=True)
    return InterventionMetrics(
        window_start=window_start,
        window_end=window_end,
        cohorts=cohorts,
        zero_touch_merged=zero_touch_merged,
    )


def _fmt_rate(value: float | None) -> str:
    return "n/a" if value is None else f"{value * 100:.0f}%"


def _fmt_median(value: float | None) -> str:
    return "n/a" if value is None else f"{value:g}"


def _escape_title(title: str) -> str:
    return " ".join(title.split()).replace("[", "\\[").replace("]", "\\]")


DEFINITIONS = """\
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
"""


def render_report(metrics: InterventionMetrics, generated_at: datetime) -> str:
    """Render the Markdown report."""
    lines = [
        "# Agent PR Intervention Metrics",
        "",
        f"Generated {generated_at:%Y-%m-%d} from GitHub PR events. Window: PRs created "
        f"{metrics.window_start:%Y-%m-%d} to {metrics.window_end:%Y-%m-%d} "
        f"({INTERVENTION_WINDOW_DAYS} days). Agent-authored PRs in window: {metrics.total_prs}.",
        "",
        "| Outcome | PRs | Zero-touch | Zero-intervention rate | Interventions | "
        "Median per intervened PR |",
        "|---------|-----|------------|------------------------|---------------|"
        "--------------------------|",
    ]
    for status in STATUSES:
        c = metrics.cohorts[status]
        lines.append(
            f"| {status} | {c.prs} | {c.zero_touch} | {_fmt_rate(c.zero_rate)} "
            f"| {c.interventions} | {_fmt_median(c.median_when_intervened)} |"
        )

    sample = _evenly_spaced(metrics.zero_touch_merged, ZERO_TOUCH_SAMPLE_SIZE)
    lines += [
        "",
        "## Zero-touch merge sample",
        "",
        f"{len(sample)} of {len(metrics.zero_touch_merged)} merged PRs with zero interventions, "
        "spread across the window, newest first.",
        "",
    ]
    lines += [f"- [#{p['number']}]({p['url']}): {_escape_title(p['title'])}" for p in sample]
    if not sample:
        lines.append("- none")
    lines += ["", DEFINITIONS]
    return "\n".join(lines)


def write_report(path: str | os.PathLike[str], text: str) -> None:
    """Write the report atomically, creating the parent directory."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=target.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
        os.replace(tmp, target)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


# ---------------------------------------------------------------------------
# Fetching (lossless: every page is read or the run raises)
# ---------------------------------------------------------------------------


def _complete_connection(pr: dict[str, Any], connection: str) -> None:
    """Page one nested connection of a PR to the end, in place.

    A truncated list can report a false zero-touch, so an incomplete read
    raises instead of returning a partial PR.
    """
    data = pr.get(connection) or {}
    nodes: list[dict[str, Any]] = list(data.get("nodes") or [])
    page_info = data.get("pageInfo") or {}
    pages = 0
    while page_info.get("hasNextPage"):
        pages += 1
        if pages > MAX_NESTED_PAGES:
            raise RuntimeError(
                f"PR #{pr['number']}: {connection} exceeded {MAX_NESTED_PAGES} pages"
            )
        cursor = page_info.get("endCursor")
        if not cursor:
            raise RuntimeError(f"PR #{pr['number']}: {connection} has a next page but no cursor")
        query = _NESTED_QUERY.replace("__CONNECTION__", connection).replace(
            "__SELECTION__", _NESTED_SELECTIONS[connection]
        )
        response = gh_graphql(query, {"id": pr["id"], "cursor": cursor})
        page = ((response.get("node") or {}).get(connection)) or {}
        nodes.extend(page.get("nodes") or [])
        page_info = page.get("pageInfo") or {}
    pr[connection] = {"nodes": nodes, "pageInfo": {"hasNextPage": False, "endCursor": None}}


def fetch_prs_created_since(owner: str, repo: str, since: datetime) -> list[dict[str, Any]]:
    """Return every PR created at or after ``since`` with complete nested lists.

    PRs are ordered by creation time, newest first, so the first PR older than
    ``since`` ends the scan exactly. Raises RuntimeError on a missing cursor, a
    page cap hit, or an unreadable response.
    """
    collected: list[dict[str, Any]] = []
    cursor: str | None = None
    for _ in range(MAX_PR_PAGES):
        variables: dict[str, Any] = {"owner": owner, "repo": repo}
        if cursor:
            variables["cursor"] = cursor
        data = gh_graphql(_PRS_QUERY, variables)
        connection = (data.get("repository") or {}).get("pullRequests")
        if connection is None:
            raise RuntimeError(f"Could not read pull requests for {owner}/{repo}")

        for pr in connection["nodes"]:
            if _parse_time(pr["createdAt"]) < since:
                return collected
            for name in _NESTED_SELECTIONS:
                _complete_connection(pr, name)
            collected.append(pr)

        page_info = connection["pageInfo"]
        if not page_info["hasNextPage"]:
            return collected
        cursor = page_info.get("endCursor")
        if not cursor:
            raise RuntimeError("pullRequests has a next page but no cursor")

    raise RuntimeError(f"pullRequests pagination exceeded {MAX_PR_PAGES} pages")


def run_report(
    owner: str,
    repo: str,
    report_path: str | os.PathLike[str],
    now: datetime | None = None,
) -> InterventionMetrics:
    """Fetch, aggregate and write the report. Raises RuntimeError on API failure."""
    end = now or datetime.now(UTC)
    start = end - timedelta(days=INTERVENTION_WINDOW_DAYS)
    metrics = build_metrics(fetch_prs_created_since(owner, repo, start), start, end)
    write_report(report_path, render_report(metrics, end))
    return metrics
