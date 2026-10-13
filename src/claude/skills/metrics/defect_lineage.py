#!/usr/bin/env python3
"""Check, report, and recheck defect lineage records (issue #5638).

Read-only except ``recheck --write``, which appends one status_history entry to
the record file. It never deletes the chain, and it never files or closes an
issue. The record schema lives in ``defect_lineage_record.py`` and the report
rules in ``defect_lineage_report.py``.

Subcommands:
    check  PATH...             validate records, print each problem
    report PATH...             print the grouped report (markdown or json)
    recheck RECORD [--rev REV] probe REV (default origin/<default_branch>) and
                               print the new status; --write saves it

PATH is a record file or a directory of ``*.json`` records. ``--root`` is the
git repository that ``recheck`` probes (default: the current directory).

The recheck probe reads ``recheck.path`` from the revision with ``git show``
and matches ``recheck.pattern`` as a regular expression. The pattern comes from
a reviewed record in this repository. A path that is missing at the revision is
``unavailable``, so the status becomes UNVERIFIED instead of guessing that the
finding is fixed. A revision that does not resolve is an external error (exit 3)
and records nothing.

EXIT CODES (ADR-035):
    0 - Success
    1 - Logic error (a record is invalid)
    2 - Config error (bad path, unreadable JSON, bad argument)
    3 - External error (git missing or failed)
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from collections.abc import Callable, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_here = os.path.dirname(os.path.abspath(__file__))
if _here not in sys.path:
    sys.path.insert(0, _here)

from defect_lineage_record import (  # noqa: E402
    LineageError,
    Probe,
    apply_recheck,
    require_valid,
    validate_record,
)
from defect_lineage_report import (  # noqa: E402
    build_summary,
    render_json,
    render_markdown,
)

GIT_TIMEOUT_SECONDS = 30
_REV = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]*$")


class ConfigError(Exception):
    """Bad path, unreadable JSON, or bad argument. Exit 2."""


class ExternalError(Exception):
    """git is missing or failed in an unexpected way. Exit 3."""


Prober = Callable[[Path, str, dict[str, Any], str], Probe]


def utc_now() -> str:
    """Return the current UTC time at seconds resolution."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _git(root: Path, *args: str) -> subprocess.CompletedProcess[bytes]:
    try:
        return subprocess.run(
            ["git", "-C", str(root), *args],
            capture_output=True,
            check=False,
            timeout=GIT_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.TimeoutExpired) as err:
        raise ExternalError(f"git failed to run: {err}") from err


def probe_git(root: Path, rev: str, record: dict[str, Any], checked_at: str) -> Probe:
    """Observe the record's recheck pattern at ``rev`` in the repository at ``root``."""
    check = record["recheck"]
    resolved = _git(
        root, "rev-parse", "--verify", "--quiet", "--end-of-options", f"{rev}^{{commit}}"
    )
    sha = resolved.stdout.decode("utf-8", "replace").strip()
    if resolved.returncode != 0 or not sha:
        raise ExternalError(f"revision {rev} does not resolve; fetch it first")
    listing = _git(root, "ls-tree", "--name-only", sha, "--", check["path"])
    if listing.returncode != 0 or not listing.stdout.strip():
        return Probe("unavailable", sha, checked_at, f"{check['path']} is missing at {sha[:9]}")
    shown = _git(root, "show", f"{sha}:{check['path']}")
    if shown.returncode != 0:
        return Probe("unavailable", sha, checked_at, f"git show failed for {check['path']}")
    text = shown.stdout.decode("utf-8", "replace")
    found = re.search(check["pattern"], text, re.MULTILINE) is not None
    state = "present" if found else "absent"
    return Probe(state, sha, checked_at, f"pattern {state} in {check['path']} at {sha[:9]}")


def load_record(path: Path) -> dict[str, Any]:
    """Read one JSON record file. Raises ConfigError when it cannot be read."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as err:
        raise ConfigError(f"cannot read {path}: {err}") from err
    if not isinstance(data, dict):
        raise ConfigError(f"{path} must hold one JSON object")
    return data


def expand_paths(paths: Sequence[str]) -> list[Path]:
    """Expand files and directories into a sorted, duplicate-free file list."""
    found: list[Path] = []
    for raw in paths:
        path = Path(raw)
        if path.is_dir():
            found.extend(sorted(path.glob("*.json")))
        elif path.is_file():
            found.append(path)
        else:
            raise ConfigError(f"no such record file or directory: {raw}")
    if not found:
        raise ConfigError("no lineage records found")
    return list(dict.fromkeys(found))


def _cmd_check(args: argparse.Namespace, out: Callable[[str], None]) -> int:
    failed = 0
    for path in expand_paths(args.paths):
        problems = validate_record(load_record(path))
        failed += bool(problems)
        for problem in problems:
            out(f"{path}: {problem}")
    return 1 if failed else 0


def _cmd_report(args: argparse.Namespace, out: Callable[[str], None]) -> int:
    records = [load_record(path) for path in expand_paths(args.paths)]
    summary = build_summary(records)
    text = render_json(summary) if args.output_format == "json" else render_markdown(summary)
    out(text.rstrip("\n"))
    return 0


def _cmd_recheck(
    args: argparse.Namespace,
    out: Callable[[str], None],
    prober: Prober,
    now: Callable[[], str],
) -> int:
    path = Path(args.record)
    record = require_valid(load_record(path))
    rev = args.rev or f"origin/{record['default_branch']}"
    if not _REV.match(rev):
        raise ConfigError(f"unsafe revision: {rev!r}")
    probe = prober(Path(args.root), rev, record, now())
    updated = apply_recheck(record, probe)
    last = updated["status_history"][-1]
    out(f"{record['id']}: {record['status']} -> {updated['status']} at {last['live_sha']}")
    out(f"basis: {last['basis']}")
    if args.write:
        path.write_text(json.dumps(updated, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        out(f"wrote {path}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser."""
    parser = argparse.ArgumentParser(description="Defect lineage records (issue #5638).")
    parser.add_argument("--root", default=".", help="repository root (default: cwd)")
    sub = parser.add_subparsers(dest="command", required=True)
    check = sub.add_parser("check", help="validate records")
    check.add_argument("paths", nargs="+")
    report = sub.add_parser("report", help="print the grouped report")
    report.add_argument("paths", nargs="+")
    report.add_argument("--output-format", choices=("markdown", "json"), default="markdown")
    recheck = sub.add_parser("recheck", help="probe a revision and update the status")
    recheck.add_argument("record")
    recheck.add_argument("--rev", default=None)
    recheck.add_argument("--write", action="store_true")
    return parser


def run(
    argv: Sequence[str] | None = None,
    *,
    out: Callable[[str], None] = print,
    prober: Prober = probe_git,
    now: Callable[[], str] = utc_now,
) -> int:
    """Run the CLI and return an ADR-035 exit code."""
    args = build_parser().parse_args(argv)
    try:
        if args.command == "check":
            return _cmd_check(args, out)
        if args.command == "report":
            return _cmd_report(args, out)
        return _cmd_recheck(args, out, prober, now)
    except LineageError as err:
        for problem in err.problems:
            out(f"invalid: {problem}")
        return 1
    except ConfigError as err:
        print(f"config error: {err}", file=sys.stderr)
        return 2
    except ExternalError as err:
        print(f"external error: {err}", file=sys.stderr)
        return 3


if __name__ == "__main__":
    sys.exit(run())
