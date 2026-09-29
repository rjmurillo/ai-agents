#!/usr/bin/env python3
"""Verify the completion gate's dispatch closure from outside the tree it checks.

ADR-101, Application B, second residual: "The dispatcher itself is in the tree it
checks. ... lifting the same verification into a base-ref job at P1 removes the
self-assertion. The verification logic is already written and does not need
reinventing."

`run_completion_gate.py` byte-compares each verifier its config names, and their
import closure, against a trusted ref. It runs inside the pull request's checkout,
so a pull request that rewrites the dispatcher itself, or its config, executes
attacker code while printing a trusted verdict. Nothing the script asserts about
itself closes that. This module runs the same verification from the base ref:

  * the resolver code is loaded from THIS tree, the base checkout the workflow
    ran from, never from the head;
  * the head is a separate work tree read as data (`ast` and `git cat-file`),
    never imported and never executed;
  * the roots are the base ref's own config, the dispatcher script, and every
    file the base config's commands name, expanded through the head's static
    import closure and its resolvable dynamic loads;
  * every file in that closure is compared byte for byte with the base ref, and a
    dynamic load the resolver cannot resolve is reported, as the gate reports it.

It reuses the gate's own functions (`_collect_command_paths`,
`_expand_import_closure`, `_unresolvable_dynamic_sites`) instead of restating
them, so a fix to the gate reaches this check.

What this changes and what it does not. A change to the dispatcher, its config or
a named verifier is now reported by a job whose definition the pull request cannot
edit. It is reported, not blocked: the job's context is not a required check, and
pinning it needs the publisher App ADR-101 requirement 2 describes. A legitimate
change to a verifier reports here too, exactly as it halts the local gate until a
human approves it.

EXIT CODES (ADR-035):
  0 - the head's dispatch closure is byte-identical to the base ref
  1 - files differ, are removed or new, or a dynamic load cannot be resolved
  2 - configuration: a tree, the base config or the dispatcher cannot be read
"""

from __future__ import annotations

import argparse
import contextlib
import importlib.util
import json
import subprocess
import sys
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType
from typing import Any

import yaml

EXIT_OK = 0
EXIT_DIFFERS = 1
EXIT_CONFIG = 2

GATE = ".claude/skills/github/scripts/pr/run_completion_gate.py"
CONFIG = ".claude/skills/pr-review/pr-review-config.yaml"
_PR_NUMBER = 1  # command templates substitute {pr}; the value does not change which files are named


class DispatchClosureError(Exception):
    """A tree, the config or the dispatcher could not be read."""


@dataclass
class Report:
    """What the head's dispatch closure looks like against the base ref."""

    examined: int = 0
    changed: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)
    added: list[str] = field(default_factory=list)
    unresolved: list[str] = field(default_factory=list)

    @property
    def clean(self) -> bool:
        return not (self.changed or self.removed or self.added or self.unresolved)

    def to_json(self) -> dict[str, Any]:
        return {
            "examined": self.examined,
            "changed": sorted(self.changed),
            "removed": sorted(self.removed),
            "added": sorted(self.added),
            "unresolved": sorted(self.unresolved),
        }


def _load_gate(tool_root: Path) -> ModuleType:
    path = tool_root / GATE
    spec = importlib.util.spec_from_file_location("verify_dispatch_closure_gate", path)
    if spec is None or spec.loader is None or not path.is_file():
        raise DispatchClosureError(f"dispatcher not found at {path}")
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except Exception as exc:
        raise DispatchClosureError(f"dispatcher at {path} does not load: {exc}") from exc
    return module


def _base_config(tool_root: Path) -> dict[str, Any]:
    path = tool_root / CONFIG
    try:
        loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError, UnicodeDecodeError) as exc:
        raise DispatchClosureError(f"base config {path} cannot be read: {exc}") from exc
    if not isinstance(loaded, dict):
        raise DispatchClosureError(f"base config {path} is not a mapping")
    return loaded


def _criteria(gate: ModuleType, config: dict[str, Any]) -> list[Any]:
    completion = config.get("completion_criteria")
    listed = completion if isinstance(completion, list) else []
    return [*listed, *gate._scripts_map_criteria(config)]


def _base_blob(tool_root: Path, base_ref: str, path: str) -> bytes | None:
    """The bytes of ``path`` at ``base_ref`` in the base checkout, or None if absent."""
    result = subprocess.run(
        ["git", "cat-file", "blob", f"{base_ref}:{path}"],
        cwd=tool_root,
        capture_output=True,
        check=False,
    )
    return result.stdout if result.returncode == 0 else None


def _named_files(gate: ModuleType, config: dict[str, Any], tree: Path) -> list[str]:
    """Files the config's commands name, classified from inside ``tree``.

    Relative argv tokens resolve against the working directory, exactly as they do
    when the gate dispatches them, so classification has to run from inside the
    tree it reads. From another directory every verifier would classify as outside
    the tree and drop out.
    """
    try:
        with contextlib.chdir(tree):
            named, _, escaping = gate._collect_command_paths(
                _criteria(gate, config), _PR_NUMBER, tree
            )
    except gate.ConfigError as exc:
        raise DispatchClosureError(f"base config commands cannot be classified: {exc}") from exc
    return [*named, *escaping]


def verify(tool_root: Path, head_root: Path, base_ref: str) -> Report:
    """Compare the head's dispatch closure with ``base_ref`` without running head code.

    The roots are the files the BASE config names, in the base tree, plus the
    dispatcher and the config. A root the head deletes is reported as removed: a
    pull request that deletes the gate must not read as a clean closure.
    """
    gate = _load_gate(tool_root)
    config = _base_config(tool_root)
    base_named = _named_files(gate, config, tool_root)
    roots = list(dict.fromkeys([GATE, CONFIG, *base_named, *_named_files(gate, config, head_root)]))
    closure = gate._expand_import_closure(
        [path for path in roots if (head_root / path).is_file()], head_root
    )
    report = Report(examined=len(closure))
    report.removed.extend(
        path
        for path in roots
        if not (head_root / path).is_file() and _base_blob(tool_root, base_ref, path) is not None
    )
    for path in closure:
        base_bytes = _base_blob(tool_root, base_ref, path)
        if base_bytes is None:
            report.added.append(path)
        elif base_bytes != (head_root / path).read_bytes():
            report.changed.append(path)
    report.unresolved.extend(gate._unresolvable_dynamic_sites(closure, head_root))
    return report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n", maxsplit=1)[0])
    parser.add_argument(
        "--tool-root", type=Path, default=Path.cwd(), help="Base checkout (default: cwd)."
    )
    parser.add_argument(
        "--head-root", type=Path, required=True, help="Pull request head work tree."
    )
    parser.add_argument(
        "--base-ref", default="HEAD", help="Ref in the base checkout to compare against."
    )
    parser.add_argument(
        "--advisory", action="store_true", help="Report, but exit 0 unless a config error."
    )
    parser.add_argument("--json", action="store_true", help="Print the report as JSON.")
    return parser


def _print(report: Report, as_json: bool) -> None:
    if as_json:
        print(json.dumps(report.to_json(), indent=2))
        return
    print(
        f"dispatch-closure: {report.examined} files examined; {len(report.changed)} differ, "
        f"{len(report.removed)} removed, {len(report.added)} not in the base ref, "
        f"{len(report.unresolved)} unresolved loads"
    )
    for label, items in (
        ("DIFFERS", report.changed),
        ("REMOVED", report.removed),
        ("NEW", report.added),
        ("UNRESOLVED", report.unresolved),
    ):
        for item in sorted(items):
            print(
                f"dispatch-closure: {label} {item}".encode("ascii", "backslashreplace").decode(
                    "ascii"
                )
            )


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        report = verify(args.tool_root.resolve(), args.head_root.resolve(), args.base_ref)
    except (DispatchClosureError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return EXIT_CONFIG
    _print(report, args.json)
    return EXIT_OK if report.clean or args.advisory else EXIT_DIFFERS


if __name__ == "__main__":
    sys.exit(main())
