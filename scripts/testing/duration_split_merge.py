"""Merge the per-leg pytest-split durations into one map for the Actions cache.

Each split leg writes its own file (``--store-durations --clean-durations``), so
a leg file holds only the tests that leg ran. The legs run disjoint groups, so
the union is the full, fresh map::

    uv run python scripts/testing/duration_split_merge.py \\
        artifacts/durations-split-1.json artifacts/durations-split-2.json \\
        --output pytest-split-cache/durations.json

Exit codes: 0 ok, 1 logic (the merge is empty), 2 config (a malformed file),
3 external (an unreadable input or an output that cannot be written).
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path


def merge_durations(maps: Sequence[Mapping[str, float]]) -> dict[str, float]:
    """Union of keys across ``maps``; a later map's value wins on a shared key."""
    merged: dict[str, float] = {}
    for durations in maps:
        merged.update(durations)
    return merged


def _seconds(path: Path, node_id: str, value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{path}: {node_id} is {value!r}, not a number")
    if not math.isfinite(value) or value < 0:
        raise ValueError(f"{path}: {node_id} is {value}, not a finite non-negative number")
    return float(value)


def load_durations(path: Path) -> dict[str, float]:
    """Read one leg file, raising ``ValueError`` on anything but node ID to seconds."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"{path}: not valid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError(f"{path}: not a JSON object of node ID to seconds")
    return {str(key): _seconds(path, str(key), value) for key, value in data.items()}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("inputs", nargs="+", type=Path, help="Per-leg durations JSON files.")
    parser.add_argument("--output", type=Path, required=True, help="Merged durations JSON.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(sys.argv[1:] if argv is None else argv)
    try:
        merged = merge_durations([load_durations(path) for path in args.inputs])
    except OSError as exc:
        print(f"could not read input: {exc}", file=sys.stderr)
        return 3
    except ValueError as exc:
        print(f"malformed input: {exc}", file=sys.stderr)
        return 2
    if not merged:
        print("the merged durations map is empty; nothing to cache", file=sys.stderr)
        return 1
    try:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(merged, sort_keys=True, indent=4), encoding="utf-8")
    except OSError as exc:
        print(f"could not write output: {exc}", file=sys.stderr)
        return 3
    print(f"merged {len(args.inputs)} files into {len(merged)} durations", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
