#!/usr/bin/env python3
"""Score the pre-registered H1 to H4 verdicts for the #5426 routing comparison.

Reads routing-benchmark result JSONL files and applies
`evals/routing-benchmark/PREDICTIONS.md` (`predictions-v1` plus Amendment 1)
through `_routing_verdicts.py`. Deterministic: no model call, no network.

    eval_routing_verdicts.py --results a.jsonl [b.jsonl ...] [--corpus DIR] [--output OUT.json]

The JSON report goes to stdout and, with `--output`, to that file.

Amendment 1 guard. A path with a `results-2026-10-03` component holds
pre-amendment runs (old role prompt). Such files may be scored alone, where
every verdict is `INSUFFICIENT_EVIDENCE` because they do not count toward the
evidence floor. Mixing them with any other file is refused. The rule is by path
because rows do not record which prompt produced them; moving the files out of
that directory defeats the guard.

Exit codes (AGENTS.md): 0 scored. 1 no scorable rows (all NOT_RUN or empty).
2 invalid arguments, unreadable input, unknown scenario or harness, duplicate
rows, or the Amendment 1 pooling refusal.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from _routing_scenario import RoutingCorpusError, load_corpus
from _routing_verdicts import (
    NOT_RUN,
    SUPERSEDED_DIR,
    VerdictInputError,
    parse_runs,
    score,
)

EXIT_OK = 0
EXIT_NO_ROWS = 1
EXIT_CONFIG = 2

DEFAULT_CORPUS = Path(__file__).resolve().parents[2] / "evals" / "routing-benchmark" / "scenarios"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--results", nargs="+", required=True, type=Path, metavar="JSONL")
    parser.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS)
    parser.add_argument("--output", type=Path, default=None, help="also write the report here")
    return parser


def is_superseded(path: Path) -> bool:
    return SUPERSEDED_DIR in path.resolve().parts


def check_pooling(paths: Sequence[Path]) -> bool:
    """True when every input is pre-amendment. Raises when old and new are mixed."""
    flags = [is_superseded(path) for path in paths]
    if any(flags) and not all(flags):
        old = [str(p) for p, flag in zip(paths, flags, strict=True) if flag]
        raise VerdictInputError(
            "Amendment 1 forbids pooling pre-amendment runs with later runs; "
            f"remove {old} or score it alone"
        )
    return all(flags)


def read_rows(paths: Sequence[Path]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in paths:
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except OSError as error:
            raise VerdictInputError(f"cannot read {path}: {error}") from error
        for number, line in enumerate(lines, start=1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as error:
                raise VerdictInputError(f"{path}:{number}: invalid JSON: {error}") from error
            if not isinstance(row, dict):
                raise VerdictInputError(f"{path}:{number}: row is not an object")
            rows.append(row)
    return rows


def _classes(corpus: Path) -> dict[str, str]:
    try:
        scenarios = load_corpus(corpus)
    except RoutingCorpusError as error:
        raise VerdictInputError(f"corpus {corpus}: {error}") from error
    return {s.scenario_id: s.difficulty.value for s in scenarios}


def main(argv: Sequence[str] | None = None) -> int:
    try:
        args = _parser().parse_args(argv)
    except SystemExit as error:
        return EXIT_CONFIG if error.code else EXIT_OK
    try:
        superseded = check_pooling(args.results)
        classes = _classes(args.corpus)
        runs = parse_runs(read_rows(args.results), classes)
    except VerdictInputError as error:
        print(f"error: {error}", file=sys.stderr)
        return EXIT_CONFIG
    if not any(run.status != NOT_RUN for run in runs):
        print("error: no scorable rows", file=sys.stderr)
        return EXIT_NO_ROWS
    report = score(runs, classes, superseded=superseded)
    text = json.dumps(report, indent=2, sort_keys=False)
    if args.output is not None:
        args.output.write_text(text + "\n", encoding="utf-8")
    print(text)
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
