"""Fail when a pytest leg is too slow, and warn when the split legs are uneven.

Reads the JUnit reports the legs wrote::

    uv run python scripts/testing/duration_gate_check.py artifacts/pytest-results-*.xml

``wall_seconds`` per leg is the JUnit ``testsuite`` time, which is pytest's own
session time. It leaves out checkout, environment setup, and the extra steps
split-1 runs, so the limit sits below the job timeout (see
``duration_gates.PARTITION_WALL_LIMIT_SECONDS``).

Exit codes: 0 ok, 1 logic (a leg over the limit, or no test records), 2 config
(bad arguments, or a report declaring a DTD or entity), 3 external (unreadable
input).
"""

from __future__ import annotations

import argparse
import sys
import xml.etree.ElementTree as ET
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

# Bootstrap the repository root so a bare `python3 scripts/testing/duration_gate_check.py`
# resolves the sibling imports, same pattern as `duration_trend.py`.
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.testing.duration_gates import (  # noqa: E402
    PARTITION_WALL_LIMIT_SECONDS,
    SPLIT_IMBALANCE_RATIO,
    gate_commands,
    legs_over_limit,
    split_imbalance,
)
from scripts.testing.duration_snapshot import build_snapshot  # noqa: E402


def _positive(value: str) -> float:
    number = float(value)
    if number <= 0:
        raise argparse.ArgumentTypeError(f"{value} is not positive")
    return number


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("inputs", nargs="+", type=Path, help="pytest JUnit XML reports.")
    parser.add_argument("--leg-limit", type=_positive, default=PARTITION_WALL_LIMIT_SECONDS)
    parser.add_argument("--imbalance-ratio", type=_positive, default=SPLIT_IMBALANCE_RATIO)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(sys.argv[1:] if argv is None else argv)
    try:
        snapshot = build_snapshot(args.inputs, "unknown", datetime.now(UTC))
    except (OSError, ET.ParseError) as exc:
        print(f"could not read input: {exc}", file=sys.stderr)
        return 3
    except ValueError as exc:
        print(f"malformed input: {exc}", file=sys.stderr)
        return 2
    if not snapshot.modules:
        print("no test records in the given inputs", file=sys.stderr)
        return 1
    over_limit = legs_over_limit(snapshot.partitions, args.leg_limit)
    imbalance = split_imbalance(snapshot.partitions, args.imbalance_ratio)
    for line in gate_commands(over_limit, imbalance, args.leg_limit):
        print(line)
    print(
        f"duration gate: {len(over_limit)} of {len(snapshot.partitions)} legs over "
        f"{args.leg_limit:.0f}s",
        file=sys.stderr,
    )
    return 1 if over_limit else 0


if __name__ == "__main__":
    sys.exit(main())
