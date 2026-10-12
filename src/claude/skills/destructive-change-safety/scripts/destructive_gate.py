#!/usr/bin/env python3
"""CLI for the destructive-change-safety skill.

Subcommands:
    scan          find destructive sinks and trace callers (sink_scan.py)
    preview-files list files a glob would touch (scope_preflight.py)
    preview-sql   count rows a DELETE or UPDATE would change on a SQLite copy
    gate          fail-closed verdict over an evidence file (gate_verdict.py)

Every subcommand prints one JSON object on stdout.

EXIT CODES (ADR-035):
    0 - Success: scan ran, preview counted, or gate verdict is PASS or SKIP
    1 - Logic error: scan decision unknown, preview refused, or gate BLOCK
    2 - Config error: missing path, no scannable file, unreadable JSON, bad arguments
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

import gate_verdict  # noqa: E402
import scope_preflight  # noqa: E402
import sink_scan  # noqa: E402


class ConfigError(Exception):
    """An argument or input file is unusable."""


def emit(payload: dict[str, object]) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True))


def load_json(path: str) -> dict[str, object]:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise ConfigError(f"cannot read JSON from {path}: {error}") from error
    if not isinstance(data, dict):
        raise ConfigError(f"{path} must hold a JSON object")
    return data


def run_scan(args: argparse.Namespace) -> int:
    roots = [Path(p) for p in args.paths]
    missing = [str(p) for p in roots if not p.exists()]
    if missing:
        raise ConfigError(f"path does not exist: {', '.join(missing)}")
    try:
        report = sink_scan.scan(roots, Path(args.base).resolve(), args.changed)
    except sink_scan.EmptyScopeError as error:
        raise ConfigError(str(error)) from error
    emit(report)
    return 1 if report["decision"] == "unknown" else 0


def run_preview_files(args: argparse.Namespace) -> int:
    emit(scope_preflight.preview_files(Path(args.root), args.pattern))
    return 0


def run_preview_sql(args: argparse.Namespace) -> int:
    emit(scope_preflight.preview_sql(Path(args.database), args.statement))
    return 0


def run_gate(args: argparse.Namespace) -> int:
    evidence = load_json(args.evidence)
    scan_report = load_json(args.scan) if args.scan else None
    result = gate_verdict.evaluate(evidence, scan_report)
    emit(result)
    return 1 if result["verdict"] == "BLOCK" else 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    scan = sub.add_parser("scan")
    scan.add_argument("paths", nargs="+")
    scan.add_argument("--base", default=".")
    scan.add_argument("--changed", nargs="*", default=[])
    scan.set_defaults(run=run_scan)
    files = sub.add_parser("preview-files")
    files.add_argument("--root", required=True)
    files.add_argument("--pattern", action="append", required=True)
    files.set_defaults(run=run_preview_files)
    sql = sub.add_parser("preview-sql")
    sql.add_argument("--database", required=True)
    sql.add_argument("--statement", required=True)
    sql.set_defaults(run=run_preview_sql)
    gate = sub.add_parser("gate")
    gate.add_argument("--evidence", required=True)
    gate.add_argument("--scan")
    gate.set_defaults(run=run_gate)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return int(args.run(args))
    except ConfigError as error:
        print(f"config error: {error}", file=sys.stderr)
        return 2
    except scope_preflight.PreviewError as error:
        emit({"verdict": "BLOCK", "reasons": [f"scope unknown: {error}"]})
        return 1


if __name__ == "__main__":
    sys.exit(main())
