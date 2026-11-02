"""Session source discovery: which transcript stores exist and are readable."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from _mine_records import SESSION_BOUNDARY, iter_copilot_records, iter_records


def _default_roots() -> list[Path]:
    return [Path.home() / ".claude" / "projects"]


def _default_copilot_path() -> Path:
    return Path.home() / ".copilot" / "session-store.db"


def _gather_paths(roots: list[Path]) -> list[Path]:
    paths: list[Path] = []
    for root in roots:
        if root.is_file():
            paths.append(root)
        elif root.is_dir():
            paths.extend(sorted(root.rglob("*.jsonl")))
    return paths


def _repo_skills(skills_dir: Path) -> set[str]:
    if not skills_dir.is_dir():
        return set()
    return {p.name for p in skills_dir.iterdir() if p.is_dir()}


def _sources(args: argparse.Namespace) -> list[dict[str, Any]]:
    """Each requested session source with its resolved path and availability.

    --root overrides the Claude default (repeatable); --copilot sets an explicit
    DB; --no-claude / --no-copilot drop a source. The `sources` subcommand has
    no --no-* flags, so it lists everything.
    """
    found: list[dict[str, Any]] = []
    if not getattr(args, "no_claude", False):
        roots = [Path(r) for r in args.root] if args.root else _default_roots()
        for root in roots:
            found.append(
                {
                    "source": "claude",
                    "path": root.resolve(),
                    "available": root.is_file() or root.is_dir(),
                }
            )
    if not getattr(args, "no_copilot", False):
        db = Path(args.copilot) if getattr(args, "copilot", None) else _default_copilot_path()
        found.append({"source": "copilot", "path": db.resolve(), "available": db.is_file()})
    return found


def _with_boundaries(streams: list[Iterator[dict[str, Any]]]) -> Iterator[dict[str, Any]]:
    """Chain streams, marking a session boundary between consecutive ones."""
    for index, stream in enumerate(streams):
        if index:
            yield dict(SESSION_BOUNDARY)
        yield from stream


def _source_records(args: argparse.Namespace) -> Iterator[dict[str, Any]]:
    """Chain records from every AVAILABLE source. Unavailable ones are skipped."""
    streams: list[Iterator[dict[str, Any]]] = []
    for source in _sources(args):
        if not source["available"]:
            continue
        if source["source"] == "copilot":
            streams.append(iter_copilot_records(source["path"]))
        else:
            streams.append(iter_records(_gather_paths([source["path"]])))
    return _with_boundaries(streams)


def _note_if_no_source(args: argparse.Namespace) -> None:
    """Tell the user, on stderr, when there is nothing to read."""
    if not any(source["available"] for source in _sources(args)):
        sys.stderr.write("mine_sessions: no session source available\n")
