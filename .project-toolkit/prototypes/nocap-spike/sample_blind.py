"""SPIKE ONLY. Draw an upstream-style blind sample from unseen transcripts.

Mirrors upstream's docs/eval/BLIND3.md method:
- Precision sample: one visible stamp (NO CAP or CAP) per run, seeded, until ``--stamps`` items.
- Miss sample: one reply per run that has a completion word and no visible stamp, seeded,
  until ``--misses`` items. NO RECEIPT is hidden at upstream's default, so it counts as unstamped.
- CAP census: every CAP stamp in the scanned runs.

Runs named in any ``--exclude`` selection file are skipped, and so are runs whose project
directory matches ``--skip-project``. Raw sheets hold transcript text, so ``--out`` must be
outside the repository.
"""

from __future__ import annotations

import argparse
import json
import random
import re
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from adapter import check_transcript, read_turns
from run_corpus import candidates, session_id

VISIBLE = ("NO_CAP", "CAP")
COMPLETION_RE = re.compile(
    r"\b(?:done|fixed|complete[ds]?|pass(?:es|ed|ing)?|merged|pushed|green|verified|"
    r"implemented|landed|shipped|resolved)\b",
    re.I,
)


def scan(path: Path, min_calls: int = 0) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Visible stamps and unstamped completion replies for one run.

    ``min_calls`` drops replies from turns with fewer tool calls. Probe sessions that make no
    call reply "not DONE" and carry no checkable claim, so they would dilute the miss rate.
    """
    turns = read_turns(path)
    replies = {t.index: t.reply for t in turns}
    calls = {t.index: len(t.calls) for t in turns}
    stamps: list[dict[str, Any]] = []
    quiet: list[dict[str, Any]] = []
    for tv in check_transcript(path):
        shown = [r for r in tv.receipts if r["verdict"] in VISIBLE]
        # a cross-turn receipt carries its cited call's turn in "turn"; keep both turns apart
        stamps += [
            dict(r, reply_turn=tv.turn, cite_turn=int(r.get("turn", tv.turn))) for r in shown
        ]
        worked = calls.get(tv.turn, 0) >= min_calls
        if not shown and worked and COMPLETION_RE.search(replies.get(tv.turn, "")):
            quiet.append({"turn": tv.turn, "hidden": tv.receipts})
    return stamps, quiet


def main(argv: list[str] | None = None) -> int:
    """Draw both samples and write them, with a selection record, under ``--out``."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.home() / ".claude" / "projects")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--exclude", type=Path, nargs="*", default=[])
    parser.add_argument("--skip-project", action="append", default=[])
    parser.add_argument("--stamps", type=int, default=100)
    parser.add_argument("--misses", type=int, default=60)
    parser.add_argument("--seed", type=int, default=20261125)
    parser.add_argument("--min-calls", type=int, default=0)
    args = parser.parse_args(argv)

    used = {s for f in args.exclude for s in json.loads(f.read_text())["selected"]}
    rng = random.Random(args.seed)
    stamp_items: list[dict[str, Any]] = []
    miss_items: list[dict[str, Any]] = []
    caps: list[dict[str, Any]] = []
    scanned = 0
    for path in candidates(args.root):
        if len(stamp_items) >= args.stamps and len(miss_items) >= args.misses:
            break
        if session_id(path) in used or any(s in str(path) for s in args.skip_project):
            continue
        scanned += 1
        stamps, quiet = scan(path, args.min_calls)
        sid = session_id(path)
        caps += [dict(r, session=sid, path=str(path)) for r in stamps if r["verdict"] == "CAP"]
        if stamps and len(stamp_items) < args.stamps:
            stamp_items.append(dict(rng.choice(stamps), session=sid, path=str(path)))
        if quiet and len(miss_items) < args.misses:
            miss_items.append(dict(rng.choice(quiet), session=sid, path=str(path)))

    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "stamps.json").write_text(json.dumps(stamp_items, indent=1, default=str))
    (args.out / "misses.json").write_text(json.dumps(miss_items, indent=1, default=str))
    (args.out / "caps.json").write_text(json.dumps(caps, indent=1, default=str))
    meta = {
        "seed": args.seed,
        "excluded": len(used),
        "scanned": scanned,
        "stamps": len(stamp_items),
        "misses": len(miss_items),
        "caps_seen": len(caps),
        "selected": sorted({i["session"] for i in stamp_items + miss_items}),
    }
    (args.out / "_selection.json").write_text(json.dumps(meta, indent=1))
    print(json.dumps({k: v for k, v in meta.items() if k != "selected"}))
    return 0 if len(stamp_items) == args.stamps and len(miss_items) == args.misses else 1


if __name__ == "__main__":
    raise SystemExit(main())
