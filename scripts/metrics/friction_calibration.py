#!/usr/bin/env python3
"""REQ-048 TASK-001 calibration: replay the friction signals over a corpus.

Subcommands:

- ``replay``: scan top-level session transcripts in a date window and write
  ``sessions.jsonl`` (counts and ids only) plus a sensitive ``samples/`` area.
- ``split``: seeded 70/30 tune/held-out split of the replayed sessions.
- ``excerpt``: redacted plain-text excerpt of one session up to one Stop.

Signal definitions come from ``scripts/failure_classifier``; the Stop budgets
and ``is_human_turn`` come from the live Stop hook. See
``friction_calibration_scan`` for how a Stop is defined.

EXIT CODES (ADR-035):
    0 - Success
    2 - Invalid arguments or input
"""

from __future__ import annotations

import argparse
import glob
import json
import math
import os
import random
import sys
from collections import Counter
from collections.abc import Iterator
from datetime import date
from multiprocessing import Pool
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_SENTINEL = _PROJECT_ROOT / "scripts" / "validation" / "models.py"
if _SENTINEL.is_file() and str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from scripts.metrics.friction_calibration_excerpt import (  # noqa: E402
    DEFAULT_MAX_BYTES,
    StopOutOfRangeError,
    excerpt_session,
)
from scripts.metrics.friction_calibration_samples import write_samples  # noqa: E402
from scripts.metrics.friction_calibration_scan import (  # noqa: E402
    SessionScan,
    hook,
    safe_scan,
)

EXIT_OK = 0
EXIT_CONFIG = 2
SPLIT_TUNE_FRACTION = 0.7
DEFAULT_SAMPLE_SEED = 48001
MIB = 1024 * 1024
SUBAGENT_STEM_PREFIX = "agent-"


def corpus_files(pattern: str) -> tuple[list[Path], int]:
    """Top-level session files matching ``pattern``, sorted, plus subagent count.

    A subagent file lives under a ``subagents`` directory or has an ``agent-``
    stem. Both are excluded and counted.
    """
    matches = sorted(
        Path(p) for p in glob.glob(os.path.expanduser(pattern)) if p.endswith(".jsonl")
    )
    kept = [
        p
        for p in matches
        if "subagents" not in p.parts and not p.stem.startswith(SUBAGENT_STEM_PREFIX)
    ]
    return kept, len(matches) - len(kept)


def percentile(sorted_values: list[float], q: float) -> float:
    """Nearest-rank percentile of an ascending list; 0.0 when empty."""
    if not sorted_values:
        return 0.0
    rank = max(1, math.ceil(q / 100 * len(sorted_values)))
    return sorted_values[rank - 1]


def _scan_args(args: tuple[Path, date, date, int]) -> SessionScan:
    return safe_scan(*args)


def run_scans(jobs: list[tuple[Path, date, date, int]], workers: int) -> Iterator[SessionScan]:
    """Scan in order; one worker runs inline, more use a process pool."""
    if workers == 1:
        yield from map(_scan_args, jobs)
        return
    with Pool(workers) as pool:
        yield from pool.imap(_scan_args, jobs, chunksize=4)


def _parse_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError(f"not a YYYY-MM-DD date: {value!r}") from error


def summarize(rows: list[dict[str, object]], counts: Counter[str], subagents: int) -> str:
    """One-screen replay summary."""
    seconds = sorted(float(r["scan_seconds"]) for r in rows)  # type: ignore[arg-type]
    total_bytes = sum(int(r["bytes"]) for r in rows)  # type: ignore[call-overload]
    within = sum(1 for r in rows if r["within_budget"])
    share = 100 * within / len(rows) if rows else 0.0
    budgets = hook()
    return "\n".join(
        [
            f"sessions in window : {len(rows)}",
            f"skipped            : window={counts['skipped_window']} "
            f"no_timestamp={counts['skipped_no_timestamp']} subagent={subagents} "
            f"errors={counts['error']}",
            f"total size         : {total_bytes / MIB:.1f} MiB",
            f"within budget      : {within}/{len(rows)} ({share:.1f}%) "
            f"[<= {budgets.MAX_TRANSCRIPT_BYTES // MIB} MiB, "
            f"<= {budgets.SCAN_BUDGET_SECONDS}s]",
            f"scan_seconds       : p50={percentile(seconds, 50):.4f} "
            f"p99={percentile(seconds, 99):.4f} max={seconds[-1] if seconds else 0.0:.4f}",
        ]
    )


def cmd_replay(args: argparse.Namespace) -> int:
    files, subagents = corpus_files(args.corpus_glob)
    if not files:
        print(f"error: no session files match {args.corpus_glob!r}", file=sys.stderr)
        return EXIT_CONFIG
    if args.since > args.until:
        print("error: --since is after --until", file=sys.stderr)
        return EXIT_CONFIG
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    jobs = [(path, args.since, args.until, args.seed) for path in files]
    counts: Counter[str] = Counter()
    rows: list[dict[str, object]] = []
    cands = []
    for result in run_scans(jobs, args.workers):
        counts[result.status] += 1
        if result.row is not None and result.cands is not None:
            rows.append(result.row)
            cands.append(result.cands)
    with (out / "sessions.jsonl").open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True) + "\n")
    sizes = write_samples(out / "samples", cands)
    print(summarize(rows, counts, subagents))
    print(f"samples            : {sizes}")
    return EXIT_OK


def cmd_split(args: argparse.Namespace) -> int:
    path = Path(args.sessions)
    if not path.is_file():
        print(f"error: {path} is not a file", file=sys.stderr)
        return EXIT_CONFIG
    ids = sorted(
        {
            json.loads(line)["session_id"]
            for line in path.read_text(encoding="utf-8").splitlines()
            if line
        }
    )
    random.Random(args.seed).shuffle(ids)
    cut = round(SPLIT_TUNE_FRACTION * len(ids))
    split = {"seed": args.seed, "tune": sorted(ids[:cut]), "heldout": sorted(ids[cut:])}
    Path(args.out).write_text(json.dumps(split, indent=1) + "\n", encoding="utf-8")
    print(f"split seed={args.seed}: tune={len(split['tune'])} heldout={len(split['heldout'])}")
    return EXIT_OK


def cmd_excerpt(args: argparse.Namespace) -> int:
    files, _ = corpus_files(args.corpus_glob)
    path = next((p for p in files if p.stem == args.session), None)
    if path is None:
        print(f"error: session {args.session!r} not found", file=sys.stderr)
        return EXIT_CONFIG
    try:
        text, counts = excerpt_session(path, args.stop, args.max_bytes)
    except StopOutOfRangeError as error:
        print(f"error: {error}", file=sys.stderr)
        return EXIT_CONFIG
    Path(args.out).write_text(text + "\n", encoding="utf-8")
    print(f"stop {args.stop}: " + " ".join(f"{k}={v}" for k, v in counts.items()))
    return EXIT_OK


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0] if __doc__ else None)
    sub = parser.add_subparsers(dest="command", required=True)

    replay = sub.add_parser("replay", help="scan the corpus and write sessions.jsonl")
    replay.add_argument("--corpus-glob", required=True)
    replay.add_argument("--since", type=_parse_date, required=True)
    replay.add_argument("--until", type=_parse_date, required=True)
    replay.add_argument("--out", required=True)
    replay.add_argument("--workers", type=int, default=min(16, os.cpu_count() or 1))
    replay.add_argument("--seed", type=int, default=DEFAULT_SAMPLE_SEED, help="sample seed")
    replay.set_defaults(func=cmd_replay)

    split = sub.add_parser("split", help="seeded 70/30 split by session_id")
    split.add_argument("--sessions", required=True)
    split.add_argument("--seed", type=int, required=True)
    split.add_argument("--out", required=True)
    split.set_defaults(func=cmd_split)

    excerpt = sub.add_parser("excerpt", help="redacted excerpt up to one Stop")
    excerpt.add_argument("--corpus-glob", required=True)
    excerpt.add_argument("--session", required=True)
    excerpt.add_argument("--stop", type=int, required=True)
    excerpt.add_argument("--out", required=True)
    excerpt.add_argument("--max-bytes", type=int, default=DEFAULT_MAX_BYTES)
    excerpt.set_defaults(func=cmd_excerpt)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if getattr(args, "workers", 1) < 1:
        print("error: --workers must be >= 1", file=sys.stderr)
        return EXIT_CONFIG
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())
