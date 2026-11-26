#!/usr/bin/env python3
"""Scored review loop for llm-council: the PR "Council review" table.

Review loop mode follows t3dotgg/tstack council (MIT). Each delegate reviews
the change read-only and ends its reply with one line ``SCORE: N/10``. Each
full review pass is one round; a fresh review after fixes starts a new round.

Layout of one review: ``<review-dir>/round-<n>/<member>.md``, where
``<member>`` is the member id with unsafe characters replaced by ``_``.

``table`` prints the section for the PR description. A delegate with no
readable score gets ``no score``; a score is never invented.

Exit codes: 0 table printed, 2 config error (no rounds, unreadable directory).
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

_HERE = Path(__file__).absolute().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, _HERE.as_posix())

from council_core import member_slug  # noqa: E402

EXIT_OK, EXIT_CONFIG = 0, 2
# The whole line must be the score: optional Markdown emphasis markers, "SCORE:",
# a number, "/10", then optional closing markers. "8/10.5" and "8/10 (ok)" do not match.
_SCORE = re.compile(
    r"^[ \t]*[*_]*[ \t]*SCORE[ \t]*[*_]*[ \t]*:[ \t]*[*_]*[ \t]*(\d+(?:\.\d+)?)"
    r"[ \t]*/[ \t]*10[ \t]*[*_]*[ \t\r]*$",
    re.I | re.M,
)
_ROUND = re.compile(r"^round-(\d+)$")


def parse_score(text: str) -> str:
    """Return the last ``SCORE: N/10`` line as a normalized ``N/10``, or "" when absent or invalid."""
    matches = _SCORE.findall(text)
    if not matches:
        return ""
    value = float(matches[-1])
    if not 0 <= value <= 10:
        return ""
    return f"{value:g}/10"


def numbered_rounds(review_dir: Path) -> list[tuple[int, Path]]:
    """(round number, directory) pairs in numeric order."""
    found = [
        (int(m.group(1)), p)
        for p in review_dir.iterdir()
        if p.is_dir() and (m := _ROUND.match(p.name))
    ]
    return sorted(found)


def round_dirs(review_dir: Path) -> list[Path]:
    """Round directories in numeric order."""
    return [p for _, p in numbered_rounds(review_dir)]


def score_for(round_dir: Path, member: str) -> str:
    path = round_dir / f"{member_slug(member)}.md"
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return "no score"
    return parse_score(text) or "no score"


def render_table(review_dir: Path, members: list[str]) -> str:
    rounds = numbered_rounds(review_dir)
    header = "| Delegate | " + " | ".join(f"Round {n}" for n, _ in rounds) + " |"
    rule = "| --- |" + " --- |" * len(rounds)
    rows = [f"| {m} | " + " | ".join(score_for(r, m) for _, r in rounds) + " |" for m in members]
    return (
        "\n".join(["## Council review", "", f"Rounds: {len(rounds)}", "", header, rule, *rows])
        + "\n"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Print the PR Council review table.")
    sub = parser.add_subparsers(dest="command", required=True)
    table = sub.add_parser("table", help="print the Council review section")
    table.add_argument("--review-dir", required=True)
    table.add_argument(
        "--members", required=True, help="comma-separated member ids, in table order"
    )
    args = parser.parse_args(argv)
    review_dir = Path(args.review_dir)
    members = [m.strip() for m in args.members.split(",") if m.strip()]
    try:
        rounds = round_dirs(review_dir)
    except OSError as exc:
        print(f"council_review: cannot read {review_dir}: {exc}", file=sys.stderr)
        return EXIT_CONFIG
    if not rounds or not members:
        print(
            f"council_review: no round-<n> directories or no members in {review_dir}",
            file=sys.stderr,
        )
        return EXIT_CONFIG
    print(render_table(review_dir, members), end="")
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
