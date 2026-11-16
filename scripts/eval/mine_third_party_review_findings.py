#!/usr/bin/env python3
"""Mine third-party bot review findings from recent pull requests.

Reads the newest N pull requests with every review thread, review, and
top-level comment (lossless, see ``_third_party_review_fetch``), and writes
the raw records as JSON. ``--summarize`` reads a saved dump and prints, per
reviewer bot, how many threads it opened and how many the author resolved.

The dump feeds the corpus in ``evals/third-party-review-gap/``. Method and
limits: ``evals/third-party-review-gap/README.md``.

Exit codes:
    0  ok
    2  config error (bad arguments, unreadable dump, unresolvable repository)
    3  external error (API failure, pagination incomplete, budget low)
    4  authentication error
"""

from __future__ import annotations

import argparse
import json
import logging
import subprocess
import sys
from collections import Counter
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import _third_party_review_findings as findings  # noqa: E402
from _third_party_review_fetch import (  # noqa: E402
    Budget,
    FetchError,
    fetch_recent_pull_requests,
)

EXIT_OK = 0
EXIT_CONFIG = 2
EXIT_EXTERNAL = 3
EXIT_AUTH = 4

logger = logging.getLogger(__name__)


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--limit", type=int, default=1000, help="newest N pull requests")
    parser.add_argument("--owner", default="")
    parser.add_argument("--repo", default="")
    parser.add_argument("--output", type=Path, help="write the raw dump here")
    parser.add_argument("--summarize", type=Path, help="summarize a saved dump; no API call")
    return parser.parse_args(argv)


def summarize(dump: dict[str, Any]) -> dict[str, Any]:
    prs = dump["pull_requests"]
    rows = findings.extract_bot_threads(prs)
    by_bot: Counter[str] = Counter()
    resolved: Counter[str] = Counter()
    for row in rows:
        by_bot[row["bot"]] += 1
        if row["is_resolved"]:
            resolved[row["bot"]] += 1
    return {
        "pull_requests": len(prs),
        "number_range": [min(p["number"] for p in prs), max(p["number"] for p in prs)]
        if prs
        else [],
        "bot_threads": len(rows),
        "by_bot": {
            bot: {"threads": n, "resolved": resolved[bot]} for bot, n in by_bot.most_common()
        },
    }


def _fetch(args: argparse.Namespace) -> int:
    from scripts.github_core.api import gh_graphql, is_auth_failure_text, resolve_repo_params

    try:
        info = resolve_repo_params(args.owner, args.repo)
    except SystemExit:
        return EXIT_CONFIG
    budget = Budget()
    try:
        prs = fetch_recent_pull_requests(gh_graphql, info.owner, info.repo, args.limit, budget)
    except FetchError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_EXTERNAL
    except RuntimeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_AUTH if is_auth_failure_text(str(exc)) else EXIT_EXTERNAL
    except (subprocess.SubprocessError, OSError) as exc:
        print(f"error: gh could not run: {exc}", file=sys.stderr)
        return EXIT_EXTERNAL
    dump = {
        "repository": f"{info.owner}/{info.repo}",
        "limit": args.limit,
        "graphql_cost": budget.cost,
        "requests": budget.requests,
        "pull_requests": prs,
    }
    try:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(dump), encoding="utf-8")
    except OSError as exc:
        print(f"error: cannot write {args.output}: {exc}", file=sys.stderr)
        return EXIT_CONFIG
    print(json.dumps({k: v for k, v in dump.items() if k != "pull_requests"} | {"read": len(prs)}))
    return EXIT_OK


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    args = parse_args(argv)
    if args.limit <= 0:
        print("error: --limit must be positive", file=sys.stderr)
        return EXIT_CONFIG
    if args.summarize:
        try:
            summary = summarize(json.loads(args.summarize.read_text(encoding="utf-8")))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            print(f"error: cannot read dump: {exc}", file=sys.stderr)
            return EXIT_CONFIG
        except (AttributeError, KeyError, TypeError) as exc:
            print(f"error: dump has no pull_requests list: {exc!r}", file=sys.stderr)
            return EXIT_CONFIG
        print(json.dumps(summary, indent=2))
        return EXIT_OK
    if args.output is None:
        print("error: --output is required to fetch", file=sys.stderr)
        return EXIT_CONFIG
    return _fetch(args)


if __name__ == "__main__":
    sys.exit(main())
