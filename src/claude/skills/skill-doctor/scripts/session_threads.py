"""Top-level versus subagent sessions: the collector flag, counts, and the gap notice.

Separate child records (Claude Code, Codex, Warp, Hermes, Droid) are collected by
default and tagged ``thread: subagent``. Copilot keeps child events inside the parent
file, so they are folded in only on an explicit ``--include-subagents``.
python3, stdlib only.
"""

from __future__ import annotations

import argparse
import sys
from typing import Any

from session_common import THREAD_SUBAGENT, THREAD_TOP_LEVEL, THREADS


def add_subagent_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--include-subagents",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="subagent/child sessions are included by default and tagged thread=subagent; "
        "--no-include-subagents drops them. Passing --include-subagents explicitly also "
        "folds Copilot's inline child events into the parent session, which pools child "
        "work into the top-level grade",
    )


def resolve_subagent_flags(args: argparse.Namespace) -> argparse.Namespace:
    """Resolve the tri-state ``--include-subagents`` once.

    ``include_subagents`` is True unless ``--no-include-subagents`` was passed. Copilot
    keeps child events inline in the parent file, so folding them in changes the parent's
    grade; ``copilot_fold_child_events`` is True only when the flag was passed explicitly.
    """
    requested = args.include_subagents
    args.copilot_fold_child_events = requested is True
    args.include_subagents = requested is not False
    return args


def child_flag(args: Any, harness: str) -> bool:
    """Copilot folds inline child events only on an explicit request, others include them."""
    if harness == "copilot":
        return bool(args.copilot_fold_child_events)
    return bool(args.include_subagents)


def thread_split(sessions: Any, sampled: set[str]) -> dict[str, dict[str, int]]:
    """Scoreable and sampled counts per session type, top-level and subagent."""
    split = {thread: {"scoreable": 0, "sampled": 0} for thread in THREADS}
    for session in sessions:
        entry = split[session["thread"]]
        entry["scoreable"] += 1
        entry["sampled"] += session["_key"] in sampled
    return split


def add_subagent_counts(
    sessions: Any, sampled: set[str], per_harness: dict[str, dict[str, int]]
) -> None:
    """Add ``scoreable_subagent`` and ``sampled_subagent`` to every per-harness entry."""
    for harness, entry in per_harness.items():
        children = [
            s for s in sessions if s["harness"] == harness and s["thread"] == THREAD_SUBAGENT
        ]
        entry["scoreable_subagent"] = len(children)
        entry["sampled_subagent"] = sum(1 for s in children if s["_key"] in sampled)


def top_level_gap_notice(split: dict[str, dict[str, int]]) -> str | None:
    """Warn when top-level sessions exist but the sample holds only subagent sessions."""
    top = split[THREAD_TOP_LEVEL]
    if top["scoreable"] and not top["sampled"]:
        return (
            f"the sample holds no top-level sessions although {top['scoreable']} top-level "
            f"sessions are scoreable; {split[THREAD_SUBAGENT]['sampled']} sampled sessions are "
            "subagent sessions. Raise --top-level-quota, pass --no-include-subagents, or raise "
            "--max-sessions to cover top-level work."
        )
    return None


def summarize_threads(
    sessions: Any, sampled: set[str], per_harness: Any, sampling: dict[str, Any]
) -> dict[str, dict[str, int]]:
    """Fill per-harness subagent counts and the gap notice; return ``stats.per_thread``."""
    add_subagent_counts(sessions, sampled, per_harness)
    split = thread_split(sessions, sampled)
    sampling["top_level_notice"] = top_level_gap_notice(split)
    return split


def print_thread_summary(inventory: Any) -> None:
    """Print per-type, then per-harness, sampled counts and the top-level gap warning."""
    for thread, counts in inventory["stats"]["per_thread"].items():
        print(
            f"  {thread}: {counts['sampled']} sampled of {counts['scoreable']} scoreable "
            "(session type)"
        )
    for harness, counts in inventory["stats"]["per_harness"].items():
        print(
            f"  {harness}: {counts['sampled']} sampled of {counts['scoreable']} scoreable "
            f"({counts['skill_candidates']} used a skill; "
            f"{counts['sampled_subagent']} of {counts['scoreable_subagent']} subagent)"
        )
    if inventory["sampling"].get("top_level_notice"):
        print(f"warning: {inventory['sampling']['top_level_notice']}", file=sys.stderr)
