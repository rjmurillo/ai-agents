"""Fail when a pytest leg is too slow, and warn when the split legs are uneven.

Reads the JUnit reports the legs wrote::

    uv run python scripts/testing/duration_gate_check.py artifacts/pytest-results-*.xml

``wall_seconds`` per leg is the JUnit ``testsuite`` time, which is pytest's own
session time. It leaves out checkout, environment setup, and the extra steps
split-1 runs, so the limit sits below the job timeout (see
``duration_gates.PARTITION_WALL_LIMIT_SECONDS``).

By default any leg over the limit fails. ``--breach-policy consecutive-main``
applies the owner decision of issue #6751: one sample on a shared runner swings
too much to fail on, so a pull request only warns, and a push to main fails only
when the previous completed main run also had a leg over the limit
(``scripts/ci/consecutive_breach.py``). A first breach on main warns and is
recorded. Unknown prior state on main fails closed. The policy treats the run as
the unit: legs trade places between runs, so "any leg over the limit" is one
breach under the key ``LEG_WALL_TIME_GATE``, not one breach per leg name.

Exit codes: 0 ok (nothing over the limit, or only warnings under the policy),
1 logic (a leg over the limit that the policy fails, or no test records), 2 config
(bad arguments, a bad breach policy, or a report declaring a DTD or entity),
3 external (unreadable input, unwritable breach record).
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

from scripts.ci import consecutive_breach  # noqa: E402
from scripts.testing.duration_gates import (  # noqa: E402
    PARTITION_WALL_LIMIT_SECONDS,
    SPLIT_IMBALANCE_RATIO,
    gate_commands,
    leg_breaches,
    legs_over_limit,
    split_imbalance,
)
from scripts.testing.duration_snapshot import build_snapshot  # noqa: E402

# Its own key, so the record does not collide with slow-test-budget or
# duration-trend. The artifact is breach-record-leg-wall-time.
LEG_WALL_TIME_GATE = "leg-wall-time"


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
    consecutive_breach.add_policy_arguments(parser)
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
    try:
        policy = consecutive_breach.policy_from_args(args)
    except ValueError as exc:
        print(f"bad breach policy: {exc}", file=sys.stderr)
        return 2
    over_limit = legs_over_limit(snapshot.partitions, args.leg_limit)
    imbalance = split_imbalance(snapshot.partitions, args.imbalance_ratio)
    strict = policy.name == consecutive_breach.POLICY_STRICT
    # Under a policy the verdict, not this list, reports the slow legs.
    for line in gate_commands(over_limit if strict else (), imbalance, args.leg_limit):
        print(line)
    print(
        f"duration gate: {len(over_limit)} of {len(snapshot.partitions)} legs over "
        f"{args.leg_limit:.0f}s",
        file=sys.stderr,
    )
    if strict:
        return 1 if over_limit else 0
    try:
        verdict = consecutive_breach.apply_policy(
            LEG_WALL_TIME_GATE,
            leg_breaches(LEG_WALL_TIME_GATE, over_limit, args.leg_limit),
            policy,
            title="Test leg wall time",
        )
    except OSError as exc:
        print(f"could not write the breach record: {exc}", file=sys.stderr)
        return 3
    return 1 if verdict.failing else 0


if __name__ == "__main__":
    sys.exit(main())
