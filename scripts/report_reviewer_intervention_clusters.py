#!/usr/bin/env python3
"""Report repeated human review interventions on agent pull requests.

Reads every pull request updated in the trailing window, keeps the review
threads that a human opened on an agent-authored pull request, clusters them
with ``review_clusters`` and writes one JSON report. It proposes; it never
edits a rule, contract or prompt, and it files no issue (issue #7153).

The cluster definition lives in the ``review_clusters`` module docstring and
in ``.project-toolkit/metrics/reviewer-intervention-clusters/README.md``.

Population
    Defined in the ``review_clusters`` module so every consumer counts alike:
    ``AGENT_TRAILER``, ``DEPENDENCY_BOTS``, ``REVIEWER_ASSOCIATIONS``,
    ``is_agent_pull_request`` and ``classify_thread_opener``. This script
    resolves bot status with ``github_core.bot_config.is_bot`` and passes it in.

Reads are lossless (``lossless-queue-reads``): pull requests arrive newest-update
first and the walk ends at the first one older than the 90-day window; every
page inside that bound is fetched until the API reports no next page. A
missing cursor or a page cap fails the run with exit 3 and names what was not
read. A partial result is never written.

Exit codes (AGENTS.md contract):
    0  Report written. Zero clusters is a success and says so.
    2  Configuration error: bad arguments, unreadable or malformed
       dispositions file, unresolvable repository, a path outside its
       allowed directory.
    3  External error: the API failed or timed out, pagination could not
       complete, or the API returned malformed data.
    4  Authentication error.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import subprocess
import sys
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

workspace = os.environ.get(
    "GITHUB_WORKSPACE",
    os.path.abspath(os.path.join(os.path.dirname(__file__), "..")),
)
sys.path.insert(0, workspace)
# Deliberate coupling: the shared cluster module ships inside the skill-bootstrap skill so a
# shipped skill can import it. This upstream-only script reaches it by path.
sys.path.insert(
    0, str(Path(workspace) / "src" / "claude" / "skills" / "skill-bootstrap" / "scripts")
)

import review_clusters  # noqa: E402

from scripts.github_core.api import (  # noqa: E402
    gh_graphql,
    is_auth_failure_text,
    resolve_repo_params,
)
from scripts.github_core.bot_config import is_bot  # noqa: E402

logger = logging.getLogger(__name__)

EXIT_OK = 0
EXIT_CONFIG = 2
EXIT_EXTERNAL = 3
EXIT_AUTH = 4

DEFAULT_REPORT = ".project-toolkit/metrics/reviewer-intervention-clusters/report.json"
DEFAULT_DISPOSITIONS = ".project-toolkit/pr-checks/suppressed-finding-dispositions.json"
MAX_PR_PAGES = 200
MAX_THREAD_PAGES = 50
PROGRESS_EVERY_PAGES = 10

GraphQL = Callable[[str, dict[str, Any] | None], dict[str, Any]]


class FetchError(RuntimeError):
    """Pagination or response shape prevented a complete read."""


_ACTOR = "login __typename"
_THREAD_FIELDS = f"""
  id
  comments(first: 1) {{
    nodes {{ id body createdAt path authorAssociation author {{ {_ACTOR} }} }}
  }}
"""

_PRS_QUERY = f"""
query($owner: String!, $repo: String!, $cursor: String) {{
  rateLimit {{ cost remaining }}
  repository(owner: $owner, name: $repo) {{
    pullRequests(first: 50, orderBy: {{field: UPDATED_AT, direction: DESC}}, after: $cursor) {{
      pageInfo {{ hasNextPage endCursor }}
      nodes {{
        number
        updatedAt
        body
        authorAssociation
        author {{ {_ACTOR} }}
        reviewThreads(first: 50) {{
          pageInfo {{ hasNextPage endCursor }}
          nodes {{ {_THREAD_FIELDS} }}
        }}
      }}
    }}
  }}
}}"""

_THREADS_QUERY = f"""
query($owner: String!, $repo: String!, $number: Int!, $cursor: String) {{
  repository(owner: $owner, name: $repo) {{
    pullRequest(number: $number) {{
      reviewThreads(first: 50, after: $cursor) {{
        pageInfo {{ hasNextPage endCursor }}
        nodes {{ {_THREAD_FIELDS} }}
      }}
    }}
  }}
}}"""


def _obj(value: object, what: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise FetchError(f"malformed GraphQL response: {what} is not an object")
    return value


def _next_cursor(connection: dict[str, Any], what: str) -> str | None:
    info = connection.get("pageInfo")
    if not isinstance(info, dict):
        raise FetchError(f"missing pagination info for {what}")
    if not info.get("hasNextPage"):
        return None
    cursor = info.get("endCursor")
    if not isinstance(cursor, str) or not cursor:
        raise FetchError(f"missing pagination cursor for {what}")
    return cursor


def _nodes(connection: dict[str, Any], what: str) -> list[dict[str, Any]]:
    nodes = connection.get("nodes")
    if not isinstance(nodes, list):
        raise FetchError(f"missing nodes for {what}")
    if any(n is None for n in nodes):
        raise FetchError(f"null node in {what}; the read is incomplete")
    return [_obj(n, what) for n in nodes]


def _remaining_threads(
    graphql: GraphQL, owner: str, repo: str, number: int, cursor: str
) -> list[dict[str, Any]]:
    threads: list[dict[str, Any]] = []
    for _ in range(MAX_THREAD_PAGES):
        data = _obj(
            graphql(
                _THREADS_QUERY,
                {"owner": owner, "repo": repo, "number": number, "cursor": cursor},
            ),
            "threads page",
        )
        pr = _obj(_obj(data.get("repository"), "repository").get("pullRequest"), "pullRequest")
        conn = _obj(pr.get("reviewThreads"), "reviewThreads")
        threads.extend(_nodes(conn, f"PR #{number} threads"))
        next_cursor = _next_cursor(conn, f"PR #{number} threads")
        if next_cursor is None:
            return threads
        cursor = next_cursor
    raise FetchError(
        f"thread pagination exceeded {MAX_THREAD_PAGES} pages on PR #{number}; "
        "later threads were not read"
    )


def fetch_pull_requests(
    graphql: GraphQL,
    owner: str,
    repo: str,
    since: datetime,
    stats: dict[str, int] | None = None,
) -> tuple[list[dict[str, Any]], int]:
    """Return ``(pull_requests, examined)`` for PRs updated at or after ``since``.

    Each returned PR carries ``number``, ``author``, ``author_association``,
    ``body`` and a complete ``threads`` list. Pull requests arrive ordered by
    ``updatedAt`` descending, so the first one older than ``since`` ends the
    walk: a comment in the window implies its PR was updated in the window. A
    pull request updated during the walk can jump ahead of the cursor and wait
    for the next run. A repeated number is skipped and counted. ``stats``, when
    given, receives ``pages``, ``duplicate_pull_requests_skipped`` and the
    GraphQL ``graphql_cost`` in points.
    """
    result: list[dict[str, Any]] = []
    seen: set[int] = set()
    counters = stats if stats is not None else {}
    counters.update({"pages": 0, "duplicate_pull_requests_skipped": 0, "graphql_cost": 0})
    examined = 0
    cursor: str | None = None
    for _ in range(MAX_PR_PAGES):
        variables: dict[str, Any] = {"owner": owner, "repo": repo}
        if cursor:
            variables["cursor"] = cursor
        data = _obj(graphql(_PRS_QUERY, variables), "pull request page")
        counters["pages"] += 1
        limit = data.get("rateLimit")
        if isinstance(limit, dict) and isinstance(limit.get("cost"), int):
            counters["graphql_cost"] += limit["cost"]
        if counters["pages"] % PROGRESS_EVERY_PAGES == 0:
            logger.info("read %d pages, %d pull requests", counters["pages"], examined)
        conn = _obj(_obj(data.get("repository"), "repository").get("pullRequests"), "pullRequests")
        reached_boundary = False
        for pr in _nodes(conn, "pull requests"):
            updated = review_clusters.parse_timestamp(pr.get("updatedAt"))
            if updated < since:
                reached_boundary = True
                break
            number = pr.get("number")
            if not isinstance(number, int):
                raise FetchError("pull request without a numeric `number`")
            if number in seen:
                counters["duplicate_pull_requests_skipped"] += 1
                continue
            seen.add(number)
            examined += 1
            threads_conn = _obj(pr.get("reviewThreads"), f"PR #{number} reviewThreads")
            threads = _nodes(threads_conn, f"PR #{number} threads")
            more = _next_cursor(threads_conn, f"PR #{number} threads")
            if more is not None:
                threads.extend(_remaining_threads(graphql, owner, repo, number, more))
            result.append(
                {
                    "number": number,
                    "author": pr.get("author"),
                    "author_association": pr.get("authorAssociation"),
                    "body": pr["body"] if isinstance(pr.get("body"), str) else "",
                    "threads": threads,
                }
            )
        if reached_boundary:
            return result, examined
        cursor = _next_cursor(conn, "pull requests")
        if cursor is None:
            return result, examined
    raise FetchError(
        f"pull request pagination exceeded {MAX_PR_PAGES} pages; older pull requests were not read"
    )


def _actor(raw: object) -> tuple[str, str | None]:
    if not isinstance(raw, dict):
        return "", None
    login = raw.get("login")
    kind = raw.get("__typename")
    return (login if isinstance(login, str) else ""), (kind if isinstance(kind, str) else None)


FUNNEL_KEYS = (
    "agent_pull_requests",
    "trailer_pull_requests",
    "threads_seen",
    "threads_without_comments",
    "threads_excluded_bot_or_unknown",
    "threads_excluded_no_standing",
    "interventions_by_pr_author",
)


def extract_interventions(
    pull_requests: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """Keep human-opened threads on agent pull requests.

    Returns ``(interventions, counts)``. ``counts`` has one entry per name in
    ``FUNNEL_KEYS``, so a drop at any filter is visible in the report.
    """
    interventions: list[dict[str, Any]] = []
    counts = dict.fromkeys(FUNNEL_KEYS, 0)
    for pr in pull_requests:
        author, author_kind = _actor(pr["author"])
        body = pr.get("body") or ""
        author_is_bot = bool(author) and is_bot(author, author_kind)
        if not review_clusters.is_agent_pull_request(
            author, author_is_bot, pr.get("author_association"), body
        ):
            continue
        counts["agent_pull_requests"] += 1
        if review_clusters.AGENT_TRAILER in body:
            counts["trailer_pull_requests"] += 1
        for thread in pr["threads"]:
            counts["threads_seen"] += 1
            comments = _obj(thread.get("comments"), "thread comments")
            first = _nodes(comments, f"thread {thread.get('id')} comments")
            if not first:
                counts["threads_without_comments"] += 1
                continue
            comment = first[0]
            login, kind = _actor(comment.get("author"))
            verdict = review_clusters.classify_thread_opener(
                login, bool(login) and is_bot(login, kind), comment.get("authorAssociation")
            )
            if verdict == review_clusters.OPENER_BOT_OR_UNKNOWN:
                counts["threads_excluded_bot_or_unknown"] += 1
                continue
            if verdict == review_clusters.OPENER_NO_STANDING:
                counts["threads_excluded_no_standing"] += 1
                continue
            if login == author:
                counts["interventions_by_pr_author"] += 1
            thread_id = thread.get("id")
            if not isinstance(thread_id, str) or not thread_id:
                raise FetchError(f"thread on PR #{pr['number']} has no id")
            interventions.append(
                {
                    "pr": pr["number"],
                    "thread_id": thread_id,
                    "created_at": comment.get("createdAt"),
                    "body": comment.get("body") if isinstance(comment.get("body"), str) else "",
                    "path": comment.get("path"),
                }
            )
    return interventions, counts


def load_dispositions(path: Path) -> dict[str, Any]:
    """Read the disposition registry. A missing file is an empty registry."""
    if not path.exists():
        logger.warning("dispositions file %s is absent; treating it as an empty registry", path)
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ValueError(f"cannot read dispositions file {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError(f"dispositions file {path} must hold a JSON object")
    review_clusters.validate_dispositions(data)
    return data


def build_report(
    graphql: GraphQL,
    owner: str,
    repo: str,
    dispositions: dict[str, Any],
    now: datetime,
) -> dict[str, Any]:
    """Fetch, filter and cluster. Raises FetchError or ValueError, never partial."""
    since = review_clusters.window_start(now)
    fetch_stats: dict[str, int] = {}
    pull_requests, examined_prs = fetch_pull_requests(graphql, owner, repo, since, fetch_stats)
    interventions, counts = extract_interventions(pull_requests)
    clustered = review_clusters.cluster_interventions(
        interventions, dispositions, now=now, window_days=review_clusters.WINDOW_DAYS
    )
    clustered["examined"].update(
        {
            "pull_requests": examined_prs,
            "duplicate_pull_requests_skipped": fetch_stats["duplicate_pull_requests_skipped"],
            **counts,
        }
    )
    logger.info(
        "read %d pages for %d pull requests; GraphQL cost %d points",
        fetch_stats["pages"],
        examined_prs,
        fetch_stats["graphql_cost"],
    )
    return {
        "as_of": now.date().isoformat(),
        "repository": f"{owner}/{repo}",
        **clustered,
    }


def render_report(report: dict[str, Any]) -> str:
    """Serialize with one field per line and one cluster per line.

    A daily diff stays readable and the file stays short; indent=2 would give
    each cluster's evidence its own lines.
    """
    fields: dict[str, str] = {}
    for key, value in report.items():
        if key == "clusters":
            rows = ",\n".join(f"    {json.dumps(c, sort_keys=True)}" for c in value)
            fields[key] = f"[\n{rows}\n  ]" if rows else "[]"
        else:
            fields[key] = json.dumps(value, sort_keys=True)
    body = ",\n".join(f"  {json.dumps(k)}: {fields[k]}" for k in sorted(fields))
    return "{\n" + body + "\n}\n"


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--owner", default="")
    parser.add_argument("--repo", default="")
    parser.add_argument("--output", default=DEFAULT_REPORT)
    parser.add_argument("--dispositions-file", default=DEFAULT_DISPOSITIONS)
    return parser


def _resolve_inside(
    workspace_root: Path, value: str, *, flag: str, under: str, suffix: str
) -> Path:
    """Resolve ``value`` against the workspace; it must stay under ``under`` with ``suffix``."""
    root = workspace_root.resolve()
    base = (root / under).resolve()
    target = (root / value).resolve()
    if not target.is_relative_to(base) or target.suffix != suffix:
        raise ValueError(f"{flag} must be a {suffix} path under {under}: {value}")
    return target


def main(argv: list[str] | None = None, *, graphql: GraphQL | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    try:
        args = _build_parser().parse_args(argv)
    except SystemExit as exc:
        return EXIT_OK if exc.code == 0 else EXIT_CONFIG
    root = Path(workspace)
    try:
        output = _resolve_inside(
            root, args.output, flag="--output", under=".project-toolkit/metrics", suffix=".json"
        )
        dispositions = load_dispositions(
            _resolve_inside(
                root,
                args.dispositions_file,
                flag="--dispositions-file",
                under=".project-toolkit/pr-checks",
                suffix=".json",
            )
        )
        repo_info = resolve_repo_params(args.owner, args.repo)
    except (ValueError, SystemExit) as exc:
        logger.error("configuration error: %s", exc)
        return EXIT_CONFIG
    try:
        report = build_report(
            graphql or gh_graphql,
            repo_info.owner,
            repo_info.repo,
            dispositions,
            datetime.now(timezone.utc),
        )
    except (FetchError, ValueError) as exc:
        logger.error("report not written, read incomplete or API data malformed: %s", exc)
        return EXIT_EXTERNAL
    except (subprocess.TimeoutExpired, OSError) as exc:
        logger.error("report not written, the gh call timed out or could not run: %s", exc)
        return EXIT_EXTERNAL
    except RuntimeError as exc:
        logger.error("report not written, GitHub request failed: %s", exc)
        return EXIT_AUTH if is_auth_failure_text(str(exc)) else EXIT_EXTERNAL
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(render_report(report), encoding="utf-8")
    examined = report["examined"]
    logger.info(
        "%d clusters in %d interventions (%d in window) across %d agent PRs "
        "(%d with trailer) of %d examined; %d dispositions; wrote %s",
        report["cluster_count"],
        examined["interventions"],
        examined["interventions_in_window"],
        examined["agent_pull_requests"],
        examined["trailer_pull_requests"],
        examined["pull_requests"],
        examined["dispositions"],
        output.relative_to(root.resolve()),
    )
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
