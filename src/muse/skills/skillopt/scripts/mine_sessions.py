#!/usr/bin/env python3
"""Mine Claude Code / Copilot session transcripts into SkillOpt eval baselines.

SkillOpt's gate is only real with a scored eval set per skill. The honest limit
is that most skills have no benchmark. This miner closes part of that gap: it
reads local session transcripts (`~/.claude/projects/**/*.jsonl`) and derives,
per skill, how often it was invoked and how often a user correction followed it,
a weak but real outcome signal. The skill with high usage AND a high correction
rate is the data-driven optimization target. For that skill it can also pull the
triggering prompts as candidate eval tasks.

Subcommands:
  sources         : list each session source, its resolved path, and availability
  rank            : ranked usage + correction-rate map for this machine
  tasks --skill X : the triggering prompts for skill X as candidate tasks
  collect --out P : write this machine's raw stats to P as a mergeable baseline
  merge           : pool per-host baseline files into one ranked map

Sources: Claude jsonl under `~/.claude/projects` and the Copilot
`~/.copilot/session-store.db`. A source that is not present is skipped, never an
error. When no requested source is available and no `--patterns` file is given,
rank, tasks, and collect print a note to stderr and emit an empty result.

Privacy: sessions stay local. Raw transcript bytes never leave this process.
`rank`, `collect`, and `merge` output skill names and counts only. Only `tasks`
carries prompt text. `collect --out` takes a path you choose; nothing is written
into the skill directory.

Pure stdlib. Exit codes: 0 ok, 2 usage or validation error.
"""

from __future__ import annotations

import argparse
import json
import socket
import sys
from pathlib import Path

from _mine_handoff import (
    _load_baseline,
    load_pattern_handoff,
    merge_stats,
    pattern_stats,
    pattern_tasks,
)
from _mine_records import (
    CORRECTION_CUES,
    aggregate,
    extract_skill_invocations,
    extract_tasks,
    is_correction,
    iter_copilot_records,
    iter_records,
    rank,
    user_text,
)
from _mine_sources import _note_if_no_source, _repo_skills, _source_records, _sources

__all__ = [
    "CORRECTION_CUES",
    "aggregate",
    "build_parser",
    "extract_skill_invocations",
    "extract_tasks",
    "is_correction",
    "iter_copilot_records",
    "iter_records",
    "load_pattern_handoff",
    "main",
    "merge_stats",
    "pattern_stats",
    "pattern_tasks",
    "rank",
    "user_text",
]


def _stats_for(args: argparse.Namespace) -> dict[str, dict[str, int]]:
    """Per-skill stats from a pattern handoff or from the session sources."""
    if args.patterns:
        return pattern_stats(load_pattern_handoff(Path(args.patterns)))
    _note_if_no_source(args)
    return aggregate(_source_records(args), window=args.window)


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def _cmd_sources(args: argparse.Namespace) -> int:
    rows = [{**s, "path": str(s["path"])} for s in _sources(args)]
    print(json.dumps(rows, indent=2))
    return 0


def _cmd_rank(args: argparse.Namespace) -> int:
    known = _repo_skills(Path(args.skills_dir)) if args.skills_dir else None
    rows = rank(_stats_for(args), known)
    if args.repo_only and known is not None:
        rows = [r for r in rows if r["in_repo"]]
    print(json.dumps(rows[: args.top], indent=2))
    return 0


def _cmd_tasks(args: argparse.Namespace) -> int:
    if args.patterns:
        tasks = pattern_tasks(load_pattern_handoff(Path(args.patterns)), args.skill)
    else:
        _note_if_no_source(args)
        tasks = extract_tasks(_source_records(args), args.skill)
    uniq = list(dict.fromkeys(tasks))  # de-dup while preserving order
    print(
        json.dumps({"skill": args.skill, "count": len(uniq), "tasks": uniq[: args.limit]}, indent=2)
    )
    return 0


def _cmd_collect(args: argparse.Namespace) -> int:
    """Write this machine's RAW per-skill stats to --out as a mergeable baseline."""
    stats = _stats_for(args)
    out = {
        "host": args.host or socket.gethostname(),
        "skill_count": len(stats),
        "stats": stats,
    }
    target = Path(args.out)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes((json.dumps(out, indent=2, sort_keys=True) + "\n").encode("utf-8"))
    sys.stderr.write(f"wrote baseline for host {out['host']} -> {target}\n")
    return 0


def _cmd_merge(args: argparse.Namespace) -> int:
    """Merge per-host baseline files (from `collect`) into one ranked map."""
    files: list[Path] = []
    if args.baselines_dir:
        d = Path(args.baselines_dir)
        if d.is_dir():
            files.extend(sorted(d.glob("*.json")))
    files.extend(Path(f) for f in (args.file or []))
    loaded = [_load_baseline(f) for f in files]
    known = _repo_skills(Path(args.skills_dir)) if args.skills_dir else None
    rows = rank(merge_stats(stats for _, stats in loaded), known)
    if args.repo_only and known is not None:
        rows = [r for r in rows if r["in_repo"]]
    print(json.dumps({"hosts": [host for host, _ in loaded], "ranked": rows[: args.top]}, indent=2))
    return 0


def _add_location_args(p: argparse.ArgumentParser) -> None:
    """Where the session sources live. Shared by every subcommand that reads them."""
    p.add_argument("--root", action="append", help="Claude transcript root (repeatable)")
    p.add_argument(
        "--copilot", help="path to Copilot session-store.db (default: ~/.copilot/session-store.db)"
    )


def _add_source_args(p: argparse.ArgumentParser) -> None:
    """Source-selection flags shared by every subcommand that reads transcripts."""
    _add_location_args(p)
    p.add_argument("--no-claude", action="store_true", help="skip Claude transcripts")
    p.add_argument("--no-copilot", action="store_true", help="skip the Copilot store")
    p.add_argument(
        "--window",
        type=int,
        default=2,
        help="user-turns after a skill in which a correction counts (default 2)",
    )
    p.add_argument(
        "--patterns",
        help=(
            "session-patterns/1 artifact from a companion session-mining skill; "
            "when set, bypass direct transcript-store reads"
        ),
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mine_sessions", description=(__doc__ or "").splitlines()[0]
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("sources", help="list session sources, resolved paths, availability")
    _add_location_args(p)
    p.set_defaults(func=_cmd_sources)

    p = sub.add_parser("rank", help="ranked usage + correction-rate map (this machine)")
    _add_source_args(p)
    p.add_argument("--skills-dir", help="repo skills dir to flag in_repo")
    p.add_argument("--top", type=int, default=25)
    p.add_argument("--repo-only", action="store_true")
    p.set_defaults(func=_cmd_rank)

    p = sub.add_parser("tasks", help="triggering prompts for a skill")
    _add_source_args(p)
    p.add_argument("--skill", required=True)
    p.add_argument("--limit", type=int, default=50)
    p.set_defaults(func=_cmd_tasks)

    p = sub.add_parser("collect", help="write this machine's raw stats as a mergeable baseline")
    _add_source_args(p)
    p.add_argument("--host", help="override host label (default: hostname)")
    p.add_argument("--out", required=True, help="baseline file path of your choosing")
    p.set_defaults(func=_cmd_collect)

    p = sub.add_parser("merge", help="merge per-host baseline files into one ranked map")
    p.add_argument("--baselines-dir", help="dir of <host>.json baseline files")
    p.add_argument("file", nargs="*", help="explicit baseline files to merge")
    p.add_argument("--skills-dir", help="repo skills dir to flag in_repo")
    p.add_argument("--top", type=int, default=25)
    p.add_argument("--repo-only", action="store_true")
    p.set_defaults(func=_cmd_merge)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return int(args.func(args))
    except (ValueError, OSError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
