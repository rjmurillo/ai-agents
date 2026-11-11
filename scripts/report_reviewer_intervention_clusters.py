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
       complete, or the API returned malformed data, or the report file could not be
       written.
    4  Authentication error.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import subprocess
import sys
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
from scripts.reviewer_intervention_fetch import (  # noqa: E402
    FetchError,
    GraphQL,
    fetch_pull_requests,
)

logger = logging.getLogger(__name__)

EXIT_OK = 0
EXIT_CONFIG = 2
EXIT_EXTERNAL = 3
EXIT_AUTH = 4

DEFAULT_REPORT = ".project-toolkit/metrics/reviewer-intervention-clusters/report.json"
DEFAULT_DISPOSITIONS = ".project-toolkit/pr-checks/suppressed-finding-dispositions.json"


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

    ``pull_requests`` are the normalized records ``fetch_pull_requests``
    returns. Returns ``(interventions, counts)``; ``counts`` has one entry per
    name in ``FUNNEL_KEYS``, so a drop at any filter is visible in the report.
    """
    interventions: list[dict[str, Any]] = []
    counts = dict.fromkeys(FUNNEL_KEYS, 0)
    for pr in pull_requests:
        author = pr["author_login"]
        body = pr.get("body") or ""
        # Only a GraphQL Bot actor is a bot here. A "-bot" suffix on a User account is a
        # name anyone can register, so it earns no agent status without standing.
        if not review_clusters.is_agent_pull_request(
            author, pr["author_kind"] == "Bot", pr.get("author_association"), body
        ):
            continue
        counts["agent_pull_requests"] += 1
        if review_clusters.AGENT_TRAILER in body:
            counts["trailer_pull_requests"] += 1
        for thread in pr["threads"]:
            counts["threads_seen"] += 1
            opener = thread["opener"]
            if opener is None:
                counts["threads_without_comments"] += 1
                continue
            login = opener["login"]
            verdict = review_clusters.classify_thread_opener(
                login, bool(login) and is_bot(login, opener["kind"]), opener["association"]
            )
            if verdict == review_clusters.OPENER_BOT_OR_UNKNOWN:
                counts["threads_excluded_bot_or_unknown"] += 1
                continue
            if verdict == review_clusters.OPENER_NO_STANDING:
                counts["threads_excluded_no_standing"] += 1
                continue
            if verdict != review_clusters.OPENER_KEPT:
                raise ValueError(f"unknown opener verdict {verdict!r} on PR #{pr['number']}")
            if login == author:
                counts["interventions_by_pr_author"] += 1
            interventions.append(
                {
                    "pr": pr["number"],
                    "thread_id": thread["id"],
                    "created_at": opener["created_at"],
                    "body": opener["body"],
                    "path": opener["path"],
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
    try:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(render_report(report), encoding="utf-8")
    except OSError as exc:
        logger.error("report not written, the file could not be saved: %s", exc)
        return EXIT_EXTERNAL
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
