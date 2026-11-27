"""Sampling flags for the session collector: window, caps, and the top-level reservation."""

from __future__ import annotations

import argparse
from collections.abc import Callable


def _non_negative(cast: Callable[[str], float], noun: str) -> Callable[[str], float]:
    def parse(value: str) -> float:
        try:
            number = cast(value)
        except ValueError:
            raise argparse.ArgumentTypeError(f"not {noun}: {value!r}") from None
        if number < 0 or number != number:
            raise argparse.ArgumentTypeError("must be 0 or greater")
        return number

    return parse


_non_negative_minutes = _non_negative(float, "a number")
_non_negative_int = _non_negative(int, "an integer")


def add_sampling_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--min-idle-minutes",
        type=_non_negative_minutes,
        default=15.0,
        help="skip sessions whose last record is newer than N minutes, because they may "
        "still be running (default: 15; 0 keeps every session)",
    )
    add = parser.add_argument
    add("--days", type=int, default=14, help="only sessions modified in the last N days (14)")
    add("--max-sessions", type=int, default=100, help="max sessions to sample for scoring (100)")
    add(
        "--top-level-quota",
        type=_non_negative_int,
        default=40,
        help="reserve up to N --max-sessions slots for top-level sessions (40; 0 pools both)",
    )
    add("--per-skill", type=int, default=10, help="max sampled sessions per skill (10)")
    add("--no-skill", type=int, default=20, help="max sampled sessions that used no skill (20)")
    parser.add_argument(
        "--timeline-supplement",
        type=int,
        default=0,
        metavar="N",
        help="opt-in: add up to N no-skill sessions spaced evenly over the window, tagged "
        "stratum timeline_supplement (default: 0, off; the sample is not representative)",
    )
