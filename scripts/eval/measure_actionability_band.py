#!/usr/bin/env python3
"""Measure how many review comments land in the actionability fallback band.

Plan task M1-T2 and M1-T3 of
``.project-toolkit/plans/active/harness-agnostic-llm-fallback.md``.
It answers kill criterion 1 of
``.project-toolkit/specs/SPEC-harness-agnostic-llm-fallback.md``: if fewer
than 5 percent of comments land in the band, a model fallback moves nothing.

The script scores comments with the production heuristic and no model. It
reuses the production fetch and scoring code unchanged:
``get_all_prs_with_comments``, ``get_comments_by_reviewer`` and
``get_actionability_score`` with ``llm_classifier=None``.

It also reports what the fetch may have dropped. The GraphQL query reads at
most 100 review threads per PR and 50 comments per thread, with no cursor for
either (``scripts/github_core/api.py``). A PR or thread that hits either limit
may hold more rows than were scored.

Usage:
    uv run python scripts/eval/measure_actionability_band.py --days-back 90 \\
        --output evals/comment-actionability/band-measurement.json
    uv run python scripts/eval/measure_actionability_band.py \\
        --from-json prs.json --output result.json

Exit codes (ADR-035):
    0 - Measured, result written
    2 - Bad argument or unreadable input file
    3 - GitHub fetch failed
"""

from __future__ import annotations

import argparse
import json
import logging
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.eval.actionability_io import atomic_write_text  # noqa: E402
from scripts.github_core.api import (  # noqa: E402
    get_all_prs_with_comments,
    resolve_repo_params,
)
from scripts.update_reviewer_signal_stats import (  # noqa: E402
    CommentData,
    get_actionability_score,
    get_comments_by_reviewer,
)

logger = logging.getLogger(__name__)

# Page sizes in the reviewThreads and comments connections of _ALL_PRS_QUERY
# in scripts/github_core/api.py. Neither connection requests pageInfo, so a
# count at the limit means rows past it were never fetched.
THREADS_PER_PR_LIMIT = 100
COMMENTS_PER_THREAD_LIMIT = 50

# Spec LLMFallbackConfig defaults (scripts/llm_classification/config.py).
BAND_MIN = 0.4
BAND_MAX = 0.6
NEUTRAL_SCORE = 0.5

# Kill criterion 1: under this band share, the fallback moves nothing.
KILL_CRITERION_1_THRESHOLD = 0.05

UNKNOWN_POSITION = -1


@dataclass
class PositionCounts:
    """Comment counts for one thread position class."""

    total: int = 0
    in_band: int = 0
    neutral_no_signal: int = 0

    def add(self, in_band: bool, neutral_no_signal: bool) -> None:
        """Count one scored comment."""
        self.total += 1
        if in_band:
            self.in_band += 1
        if neutral_no_signal:
            self.neutral_no_signal += 1


@dataclass
class Truncation:
    """Fetch limits hit, which mean rows may be missing from the scored set."""

    prs_at_thread_limit: list[int] = field(default_factory=list)
    threads_at_comment_limit: int = 0


@dataclass
class BandReport:
    """Result of one band measurement."""

    total: int
    in_band: int
    neutral_no_signal: int
    band_share: float
    neutral_no_signal_share: float
    openers: PositionCounts
    replies: PositionCounts
    unknown_position: PositionCounts
    truncation: Truncation
    kill_criterion_1_fired: bool | None


def thread_position(comment: CommentData) -> int:
    """Return the comment's index in its thread, or -1 when it cannot be found.

    ``CommentData`` carries no comment id, so the match is on body and
    creation time, the two fields the fetch returns for every node.
    """
    for index, node in enumerate(comment.thread_comments):
        if node.get("body", "") == comment.body and node.get("createdAt", "") == comment.created_at:
            return index
    return UNKNOWN_POSITION


def is_in_band(score: float) -> bool:
    """Return True when the heuristic score falls in the fallback band."""
    return BAND_MIN <= score <= BAND_MAX


def count_truncation(prs: list[dict[str, Any]]) -> Truncation:
    """Count PRs and threads whose fetched rows reached the query limit."""
    truncation = Truncation()
    for pr in prs:
        threads = (pr.get("reviewThreads") or {}).get("nodes") or []
        if len(threads) >= THREADS_PER_PR_LIMIT:
            truncation.prs_at_thread_limit.append(int(pr.get("number") or 0))
        for thread in threads:
            comments = (thread.get("comments") or {}).get("nodes") or []
            if len(comments) >= COMMENTS_PER_THREAD_LIMIT:
                truncation.threads_at_comment_limit += 1
    return truncation


def _share(part: int, whole: int) -> float:
    return round(part / whole, 4) if whole else 0.0


def measure_band(prs: list[dict[str, Any]]) -> BandReport:
    """Score every reviewer comment with the heuristic alone and count the band."""
    buckets = {
        "openers": PositionCounts(),
        "replies": PositionCounts(),
        "unknown": PositionCounts(),
    }
    for stats in get_comments_by_reviewer(prs).values():
        for comment in stats.comments:
            result = get_actionability_score(comment, llm_classifier=None)
            in_band = is_in_band(result.score)
            neutral = result.score == NEUTRAL_SCORE and not result.reasons
            position = thread_position(comment)
            if position == 0:
                key = "openers"
            elif position > 0:
                key = "replies"
            else:
                key = "unknown"
            buckets[key].add(in_band, neutral)

    total = sum(b.total for b in buckets.values())
    in_band_total = sum(b.in_band for b in buckets.values())
    neutral_total = sum(b.neutral_no_signal for b in buckets.values())
    band_share = _share(in_band_total, total)
    return BandReport(
        total=total,
        in_band=in_band_total,
        neutral_no_signal=neutral_total,
        band_share=band_share,
        neutral_no_signal_share=_share(neutral_total, total),
        openers=buckets["openers"],
        replies=buckets["replies"],
        unknown_position=buckets["unknown"],
        truncation=count_truncation(prs),
        kill_criterion_1_fired=(band_share < KILL_CRITERION_1_THRESHOLD) if total else None,
    )


def head_sha() -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return "unknown"
    return result.stdout.strip() or "unknown"


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--owner", default="", help="Repository owner (default: from git remote)")
    parser.add_argument("--repo", default="", help="Repository name (default: from git remote)")
    parser.add_argument("--days-back", type=int, default=90, help="PR updatedAt window, 1 to 365")
    parser.add_argument(
        "--from-json",
        type=Path,
        help="Read PR nodes from this file instead of GitHub (offline, reproducible)",
    )
    parser.add_argument("--save-prs", type=Path, help="Also write the fetched PR nodes here")
    parser.add_argument("--output", type=Path, required=True, help="Where to write the result JSON")
    return parser


def _load_prs(args: argparse.Namespace) -> tuple[list[dict[str, Any]], dict[str, Any]] | int:
    """Return PR nodes and source metadata, or an exit code on failure."""
    if args.from_json is not None:
        try:
            prs = json.loads(args.from_json.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            logger.error("Cannot read --from-json %s: %s", args.from_json, exc)
            return 2
        if not isinstance(prs, list):
            logger.error("--from-json must hold a JSON array of PR nodes")
            return 2
        return prs, {"source": "file", "path": str(args.from_json)}

    if not 1 <= args.days_back <= 365:
        logger.error("--days-back must be between 1 and 365, got %d", args.days_back)
        return 2
    try:
        repo_params = resolve_repo_params(args.owner, args.repo)
        since = datetime.now(UTC) - timedelta(days=args.days_back)
        prs = get_all_prs_with_comments(repo_params.owner, repo_params.repo, since)
    except RuntimeError as exc:
        # Class name only: a GraphQL error can embed a response body.
        logger.error("GitHub fetch failed: %s", type(exc).__name__)
        return 3
    meta = {
        "source": "github",
        "repository": f"{repo_params.owner}/{repo_params.repo}",
        "days_back": args.days_back,
        "window": "PR updatedAt on or after now minus days_back, not comment createdAt",
    }
    return prs, meta


def main(argv: list[str] | None = None) -> int:
    """CLI entry point. Returns an exit code."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s", stream=sys.stderr)
    args = _build_parser().parse_args(argv)

    loaded = _load_prs(args)
    if isinstance(loaded, int):
        return loaded
    prs, meta = loaded

    if args.save_prs is not None:
        atomic_write_text(args.save_prs, json.dumps(prs))

    report = measure_band(prs)
    payload = {
        "measured_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "head_sha": head_sha(),
        "band": [BAND_MIN, BAND_MAX],
        "kill_criterion_1_threshold": KILL_CRITERION_1_THRESHOLD,
        "prs_examined": len(prs),
        **meta,
        **asdict(report),
    }
    atomic_write_text(args.output, json.dumps(payload, indent=2) + "\n")

    print(
        f"examined {report.total} comments in {len(prs)} PRs: "
        f"{report.in_band} in band ({report.band_share:.1%}), "
        f"{report.neutral_no_signal} neutral with no signal; "
        f"truncated PRs {len(report.truncation.prs_at_thread_limit)}, "
        f"truncated threads {report.truncation.threads_at_comment_limit}; "
        f"kill criterion 1 fired: {report.kill_criterion_1_fired}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
