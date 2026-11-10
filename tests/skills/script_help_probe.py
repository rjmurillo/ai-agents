"""Probe one skill script's argparse parser, then stop before it acts.

``test_script_help_examples.py`` runs this file in a subprocess, once per
script, so a script's import-time ``sys.path`` and ``sys.modules`` edits cannot
leak into the pytest process.

The probe loads the script with ``runpy`` under a name other than
``__main__``, so the ``if __name__ == "__main__"`` block never runs. It then
calls the script's entry function with ``ArgumentParser.parse_args`` patched.
A ``build_parser`` style entry that returns a parser is used as is. The first
parse request records the parser and raises a ``BaseException`` sentinel, so
``main`` stops before it reads input, calls an API, or writes a file. The probe
parses each ``examples:`` line from the epilog with the real ``parse_args`` and
prints one JSON document on stdout.

Usage: python script_help_probe.py SCRIPT_PATH
"""

from __future__ import annotations

import argparse
import contextlib
import inspect
import io
import json
import re
import runpy
import shlex
import sys
from pathlib import Path
from typing import Any
from unittest import mock

ENTRY_NAMES = (
    "main",
    "run",
    "cli",
    "_main",
    "build_parser",
    "_build_parser",
    "create_parser",
    "_create_parser",
    "get_parser",
    "make_parser",
)
EXAMPLE_LINE = re.compile(r"^\s+(?:[^%]*\|\s*)?%\(prog\)s(?:\s+(?P<args>.*\S))?\s*$")
SECTION_START = re.compile(r"^[a-z][a-z ]*:")


class ParserCaptured(BaseException):
    """Raised to stop the script's entry function once its parser exists."""

    def __init__(self, parser: argparse.ArgumentParser) -> None:
        super().__init__("parser captured")
        self.parser = parser


def example_arguments(epilog: str) -> list[str]:
    """Return the argument text of each ``%(prog)s`` line under ``examples:``.

    A line may pipe into the script (``echo text | %(prog)s --flag``). Only the
    words after ``%(prog)s`` are parsed.
    """
    lines = epilog.splitlines()
    try:
        start = lines.index("examples:")
    except ValueError:
        return []
    found: list[str] = []
    for line in lines[start + 1 :]:
        if SECTION_START.match(line):
            break
        match = EXAMPLE_LINE.match(line)
        if match:
            found.append(match.group("args") or "")
    return found


def _call_entry(entry: Any) -> Any:
    """Call ``entry`` with an empty argument list when it accepts one."""
    try:
        positional = [
            p
            for p in inspect.signature(entry).parameters.values()
            if p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD) and p.default is p.empty
        ]
    except (TypeError, ValueError):
        positional = []
    return entry(*([[]] * len(positional)))


def _run_entries(script: Path) -> argparse.ArgumentParser:
    namespace = runpy.run_path(str(script), run_name="__help_probe__")
    for name in ENTRY_NAMES:
        entry = namespace.get(name)
        if not callable(entry):
            continue
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                returned = _call_entry(entry)
        except ParserCaptured as captured:
            return captured.parser
        except (Exception, SystemExit):
            continue
        if isinstance(returned, argparse.ArgumentParser):
            return returned
    raise LookupError(f"no entry function of {ENTRY_NAMES} reached a parser")


def capture_parser(script: Path) -> argparse.ArgumentParser:
    """Run the script's entry function until it asks its parser to parse."""

    def capture(self: argparse.ArgumentParser, *_args: Any, **_kwargs: Any) -> Any:
        raise ParserCaptured(self)

    sys.argv = [script.name]
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(script.parent))
    with (
        mock.patch.object(argparse.ArgumentParser, "parse_args", capture),
        mock.patch.object(argparse.ArgumentParser, "parse_known_args", capture),
    ):
        return _run_entries(script)


def probe(script: Path) -> dict[str, Any]:
    """Return the epilog, the help formatting result, and each example's parse result."""
    parser = capture_parser(script)
    report: dict[str, Any] = {"epilog": parser.epilog or "", "help_error": None, "examples": []}
    try:
        parser.format_help()
    except Exception as exc:
        report["help_error"] = f"{type(exc).__name__}: {exc}"
    prog = parser.prog
    for text in example_arguments(report["epilog"]):
        argv = shlex.split(text)
        result: dict[str, Any] = {"argv": argv, "ok": True, "error": ""}
        stderr = io.StringIO()
        try:
            with contextlib.redirect_stderr(stderr):
                argparse.ArgumentParser.parse_args(parser, argv)
        except SystemExit as exc:
            result["ok"] = False
            result["error"] = f"{prog} exit {exc.code}: {stderr.getvalue().strip()}"
        report["examples"].append(result)
    return report


def main() -> int:
    script = Path(sys.argv[1]).resolve()
    try:
        report = probe(script)
    except Exception as exc:
        report = {"probe_error": f"{type(exc).__name__}: {exc}"}
    print(json.dumps(report))
    return 0


if __name__ == "__main__":
    sys.exit(main())
