"""SPIKE ONLY. Run the vendored checker over a sampled set of transcripts.

Selection rule, fixed before the first measured run:
1. Candidates: top-level ``*.jsonl`` directly under ``~/.claude/projects/*ai-agents*/``.
2. Order: sha256 of the absolute path, ascending (deterministic, not by recency).
3. Eligible: at least one turn whose final reply yields one or more claims.
4. The first ``--holdout`` eligible files are for adapter debugging only.
   The next ``--measured`` eligible files are the measured set.
5. Re-measure: ``--exclude`` names earlier ``_selection.json`` files. Their
   sessions are skipped before eligibility, so the new sample shares none.

Raw output holds reply excerpts and commands, so it goes to ``--out`` outside
the repository. Only aggregates go into the report.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from adapter import check_transcript


def candidates(root: Path) -> list[Path]:
    """Top-level session files, in sha256-of-path order."""
    files = [p for d in root.glob("*ai-agents*") if d.is_dir() for p in d.glob("*.jsonl")]
    return sorted(files, key=lambda p: hashlib.sha256(str(p).encode()).hexdigest())


def session_id(path: Path) -> str:
    """Short stable hash, so reports never carry the raw path."""
    return hashlib.sha256(str(path).encode()).hexdigest()[:10]


def run_file(path: Path) -> dict[str, Any]:
    """Check every turn in one transcript and time each reply."""
    turns: list[dict[str, Any]] = []
    start = time.perf_counter()
    last = start
    for tv in check_transcript(path):
        now = time.perf_counter()
        turns.append(
            {
                "turn": tv.turn,
                "delegated": tv.delegated,
                "calls": tv.calls,
                "claims": tv.claims,
                "receipts": tv.receipts,
                "seconds_since_prev": round(now - last, 4),
            }
        )
        last = now
    return {
        "session": session_id(path),
        "path": str(path),
        "bytes": path.stat().st_size,
        "seconds_total": round(time.perf_counter() - start, 4),
        "turns": turns,
    }


def main(argv: list[str] | None = None) -> int:
    """Select, run, and write one JSON file per selected transcript."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.home() / ".claude" / "projects")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--holdout", type=int, default=5)
    parser.add_argument("--measured", type=int, default=40)
    parser.add_argument("--set", choices=("holdout", "measured"), default="measured")
    parser.add_argument("--exclude", type=Path, nargs="*", default=[])
    args = parser.parse_args(argv)
    used = {s for f in args.exclude for s in json.loads(f.read_text(encoding="utf-8"))["selected"]}

    args.out.mkdir(parents=True, exist_ok=True)
    pool = [p for p in candidates(args.root) if session_id(p) not in used]
    eligible: list[dict[str, Any]] = []
    scanned = 0
    need = args.holdout + args.measured
    for path in pool:
        if len(eligible) >= need:
            break
        scanned += 1
        result = run_file(path)
        if any(t["claims"] for t in result["turns"]):
            eligible.append(result)
    chosen = eligible[: args.holdout] if args.set == "holdout" else eligible[args.holdout :]
    for result in chosen:
        (args.out / f"{result['session']}.json").write_text(
            json.dumps(result, indent=1, default=str), encoding="utf-8"
        )
    meta = {
        "candidates": len(pool),
        "excluded": len(used),
        "scanned": scanned,
        "eligible_found": len(eligible),
        "set": args.set,
        "selected": [r["session"] for r in chosen],
    }
    (args.out / "_selection.json").write_text(json.dumps(meta, indent=1), encoding="utf-8")
    print(json.dumps(meta))
    return 0 if chosen else 1


if __name__ == "__main__":
    raise SystemExit(main())
