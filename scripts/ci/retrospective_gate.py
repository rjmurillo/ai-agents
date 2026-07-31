"""Decide whether a closed pull request gets a retrospective, and how deep.

Three skips and three escalation heuristics, all reading the pull request
metadata the workflow passes through the environment. Nothing here reaches a
shell, so the workflow-injection mitigation the original relied on (read
untrusted values into env vars, never interpolate them into a command string)
holds by construction rather than by review.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from collections.abc import Mapping
from pathlib import Path

EXIT_OK = 0
EXIT_CONFIG = 2

BOT_AUTHORS = frozenset(
    {
        "dependabot[bot]",
        "renovate[bot]",
        "github-actions[bot]",
        "copilot[bot]",
        "coderabbitai[bot]",
    }
)

REWORK_TITLE_RE = re.compile(r"\b(rework|retry|fix-cycle|to.improve|hotfix)\b", re.IGNORECASE)

REVIEW_COMMENT_ESCALATION_THRESHOLD = 10


def is_bot(author: str) -> bool:
    """True for the automation accounts whose pull requests teach us nothing."""
    return author in BOT_AUTHORS


def is_fork(head_repo: str, base_repo: str) -> bool:
    """True when the head lives in another repository.

    A fork run has no secrets, so the agent step could not authenticate even if
    it were scheduled.
    """
    return head_repo != base_repo


def review_comment_count(raw: str | None) -> int:
    """Parse the review-comment count, treating anything unparseable as zero.

    Matches the shell original. ``[ "$x" -ge 10 ]`` on a non-numeric value
    writes ``integer expression expected`` to stderr and evaluates false;
    ``set -e`` does not abort because the test sits in an ``if`` condition.
    This port reaches the same verdict without the stderr noise. An unreadable
    count skips one escalation heuristic, it does not fail the gate.

    ``None`` means the workflow supplied no value at all, which is the same
    "cannot tell" state as a non-numeric one. It is handled up front rather
    than through ``TypeError`` so the intent is visible to a reader and to the
    type checker.
    """
    if raw is None:
        return 0
    try:
        return int(raw)
    except ValueError:
        return 0


def should_escalate(*, merged: str, title: str, review_comments: str | None) -> bool:
    """True when the run warrants the deeper framework.

    Any one of three signals is enough: the pull request closed unmerged, its
    title carries a rework marker, or its review-comment count shows friction.
    """
    if merged != "true":
        return True
    if REWORK_TITLE_RE.search(title):
        return True
    return review_comment_count(review_comments) >= REVIEW_COMMENT_ESCALATION_THRESHOLD


def decide(env: Mapping[str, str]) -> dict[str, str]:
    """Return the step outputs for this event."""
    if env.get("EVENT_NAME", "") == "workflow_dispatch":
        return {
            "should_run": "true",
            "pr_number": env.get("PR_NUMBER", ""),
            "merged": "unknown",
            "escalate_depth": env.get("DISPATCH_ESCALATE") or "false",
        }

    author = env.get("PR_AUTHOR", "")
    if is_bot(author):
        print(f"::notice::Skipping retrospective for bot author: {author}")
        return {"should_run": "false"}

    head_repo = env.get("PR_HEAD_REPO", "")
    if is_fork(head_repo, env.get("PR_BASE_REPO", "")):
        print(f"::notice::Skipping retrospective for fork PR head={head_repo}")
        return {"should_run": "false"}

    merged = env.get("PR_MERGED", "")
    escalate = should_escalate(
        merged=merged,
        title=env.get("PR_TITLE", ""),
        review_comments=env.get("REVIEW_COMMENTS", ""),
    )
    return {
        "should_run": "true",
        "pr_number": env.get("PR_NUMBER", ""),
        "merged": merged,
        "escalate_depth": "true" if escalate else "false",
    }


def write_outputs(path: Path, outputs: Mapping[str, str]) -> None:
    with path.open("a", encoding="utf-8") as handle:
        for key, value in outputs.items():
            handle.write(f"{key}={value}\n")


def main(argv: list[str] | None = None, env: Mapping[str, str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args(argv)

    resolved = os.environ if env is None else env
    output = resolved.get("GITHUB_OUTPUT", "")
    if not output:
        print("::error::GITHUB_OUTPUT is required", file=sys.stderr)
        return EXIT_CONFIG

    write_outputs(Path(output), decide(resolved))
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
