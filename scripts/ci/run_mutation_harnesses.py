#!/usr/bin/env python3
"""Run every mutation harness under tests/mutation and name what failed.

Issue #5538. The ``mutation_harness_*.py`` scripts are the evidence that a guard
test kills the defect it claims to guard, and nothing ran them. Harness 4251
selected a renamed test for as long as the rename sat on main, and no gate
noticed. This runner is the single caller: it discovers harnesses by glob, so a
new file is wired the moment it lands, and it reports each failure under the
harness that produced it.

The harnesses disagree on output format and on exit code (1 for a survivor in
most, 2 in others, a ``SystemExit`` string in a few). The runner does not
parse a verdict out of that. It trusts the exit code for pass or fail, then
classifies a failure from the output so the log says which harness failed and
how:

  SURVIVED       a mutant the tests did not kill
  DID-NOT-APPLY  the mutation anchor no longer matches the target file
  TIMEOUT        the harness exceeded its time budget
  ERROR          anything else (stale selector, import error, crash)

EXIT CODES (ADR-035):
  0  - Success: every harness exited 0
  1  - Error: at least one harness failed
  2  - Error: usage/configuration (no harness found, bad arguments)
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import time
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

EXIT_SUCCESS = 0
EXIT_HARNESS_FAILED = 1
EXIT_USAGE = 2

REPO_ROOT = Path(__file__).resolve().parents[2]
HARNESS_DIR = Path("tests") / "mutation"
HARNESS_GLOB = "mutation_harness_*.py"
DEFAULT_TIMEOUT_SECONDS = 600
ATTRIBUTION_LINE_LIMIT = 12
FAILURE_TAIL_LINES = 40

PASS = "PASS"
SURVIVED = "SURVIVED"
DID_NOT_APPLY = "DID-NOT-APPLY"
TIMEOUT = "TIMEOUT"
ERROR = "ERROR"

_SURVIVOR_LINE = re.compile(r"SURVIV(?:ED|ING)")
# A harness prints its inverted control (a mutant that must survive) and its
# zero count line with the same word. Neither is a failure.
_SURVIVOR_NOISE = re.compile(r"inverted control, expected|expected SURVIVED|SURVIVED:\s+0\b")


@dataclass(frozen=True)
class HarnessResult:
    """One harness run: its name, outcome, wall clock, and the lines that explain it."""

    name: str
    outcome: str
    seconds: float
    evidence: tuple[str, ...]

    @property
    def passed(self) -> bool:
        return self.outcome == PASS


def discover(root: Path) -> list[Path]:
    """Return every ``mutation_harness_*.py`` under ``<root>/tests/mutation``, sorted."""
    return sorted((root / HARNESS_DIR).glob(HARNESS_GLOB))


def _survivor_lines(lines: Sequence[str]) -> list[str]:
    return [
        line.strip()
        for line in lines
        if _SURVIVOR_LINE.search(line) and not _SURVIVOR_NOISE.search(line)
    ]


def classify_failure(output: str) -> tuple[str, tuple[str, ...]]:
    """Name a nonzero harness exit from its output, with the lines that justify it."""
    lines = output.splitlines()
    survivors = _survivor_lines(lines)
    if survivors:
        return SURVIVED, tuple(survivors[:ATTRIBUTION_LINE_LIMIT])
    unapplied = [line.strip() for line in lines if DID_NOT_APPLY in line]
    if unapplied:
        return DID_NOT_APPLY, tuple(unapplied[:ATTRIBUTION_LINE_LIMIT])
    return ERROR, tuple(line for line in lines[-FAILURE_TAIL_LINES:] if line.strip())


def _text(stream: str | bytes | None) -> str:
    if stream is None:
        return ""
    return stream if isinstance(stream, str) else stream.decode("utf-8", errors="replace")


def run_harness(path: Path, root: Path, timeout: int) -> HarnessResult:
    """Run one harness as a subprocess rooted at ``root`` and classify the result."""
    env = {**os.environ, "PYTHONPATH": str(root), "PYTHONUTF8": "1"}
    started = time.monotonic()
    try:
        proc = subprocess.run(
            [sys.executable, str(path)],
            cwd=root,
            env=env,
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        tail = _text(exc.stdout).splitlines()[-FAILURE_TAIL_LINES:]
        return HarnessResult(
            path.name, TIMEOUT, time.monotonic() - started, (f"no exit after {timeout}s", *tail)
        )
    seconds = time.monotonic() - started
    if proc.returncode == 0:
        return HarnessResult(path.name, PASS, seconds, ())
    outcome, evidence = classify_failure(f"{proc.stdout}\n{proc.stderr}")
    return HarnessResult(path.name, outcome, seconds, evidence)


def report_failure(result: HarnessResult) -> None:
    """Print a GitHub error annotation and the evidence lines for a failed harness."""
    print(f"::error title=Mutation harness {result.name}::{result.outcome}")
    print(f"FAIL {result.name}: {result.outcome} ({result.seconds:.1f}s)")
    for line in result.evidence:
        print(f"  | {line}")


def run_all(harnesses: Sequence[Path], root: Path, timeout: int) -> list[HarnessResult]:
    """Run each harness in order and print one line per result."""
    results: list[HarnessResult] = []
    for path in harnesses:
        result = run_harness(path, root, timeout)
        if result.passed:
            print(f"PASS {result.name} ({result.seconds:.1f}s)")
        else:
            report_failure(result)
        results.append(result)
        sys.stdout.flush()
    return results


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser."""
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--root", type=Path, default=REPO_ROOT, help="Repository root to scan.")
    parser.add_argument(
        "--timeout",
        type=int,
        default=DEFAULT_TIMEOUT_SECONDS,
        help="Seconds each harness may run before it counts as TIMEOUT.",
    )
    parser.add_argument("--list", action="store_true", help="Print discovered harnesses and exit.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run every discovered harness. Returns an ADR-035 exit code."""
    args = build_parser().parse_args(argv)
    root = args.root.resolve()
    harnesses = discover(root)
    if not harnesses:
        print(f"ERROR: no {HARNESS_GLOB} under {root / HARNESS_DIR}", file=sys.stderr)
        return EXIT_USAGE
    if args.list:
        print("\n".join(path.name for path in harnesses))
        return EXIT_SUCCESS
    results = run_all(harnesses, root, args.timeout)
    failed = [r for r in results if not r.passed]
    print(f"\n{len(results) - len(failed)}/{len(results)} mutation harnesses passed")
    for result in failed:
        print(f"  {result.outcome}: {result.name}")
    return EXIT_HARNESS_FAILED if failed else EXIT_SUCCESS


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
