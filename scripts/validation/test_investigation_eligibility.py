#!/usr/bin/env python3
"""Check if staged files qualify for investigation-only QA skip.

Tests whether the currently staged git files are all within the
investigation-only allowlist defined in ADR-034. This allows agents
to check eligibility before committing with "SKIPPED: investigation-only".

Exit codes follow ADR-035:
    0 - Success (always returns 0, eligibility is in JSON output)
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.modules.investigation_allowlist import (  # noqa: E402  (path set above)
    get_investigation_allowlist_display,
)
from scripts.modules.investigation_allowlist import (  # noqa: E402  (path set above)
    test_file_matches_allowlist as _file_matches_allowlist,
)

_ALLOWLIST_DISPLAY = get_investigation_allowlist_display()

_COMMIT_PATTERN = re.compile(r"^[0-9a-f]{7,40}$")


def _name_status_paths(output: str) -> list[str]:
    """Return every old and new path from git name-status output."""
    paths: list[str] = []
    for line in output.splitlines():
        parts = line.split("\t")
        if len(parts) < 2:
            continue
        paths.extend(path for path in parts[1:] if path)
    return paths


def _run_git(command: list[str]) -> tuple[list[str] | None, str | None]:
    """Run one git path query and fail closed on command errors."""
    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=10,
        check=False,
    )
    if result.returncode != 0:
        detail = result.stderr.strip() or "git command failed"
        return None, detail
    if "--name-status" in command:
        return _name_status_paths(result.stdout), None
    return [line.strip() for line in result.stdout.splitlines() if line.strip()], None


def _changed_files(
    base_ref: str,
    head_ref: str = "",
) -> tuple[list[str] | None, str | None]:
    """Return paths in a fixed range or through HEAD plus the working tree.

    When both base_ref and head_ref are provided (the CI/pre-PR path), the
    diff uses ``git log --first-parent --no-merges`` instead of a plain
    two-dot tree diff.  This ensures that upstream changes introduced by
    merging main into the branch are excluded from the session scope
    (issue #4915).  A plain ``git diff base..head`` compares trees and
    includes every file present in head that differs from base, regardless
    of which commit introduced it.
    """
    range_head = head_ref or "HEAD"

    if head_ref:
        # Use git log --first-parent --no-merges to collect only files
        # changed by the branch's own (non-merge) commits.  Merge commits
        # bring upstream files into the tree but are not session work.
        commands = [
            [
                "git",
                "log",
                "--first-parent",
                "--no-merges",
                "--name-status",
                "--find-renames",
                "--no-ext-diff",
                "--format=",
                f"{base_ref}..{range_head}",
                "--",
            ],
        ]
    else:
        commands = [
            [
                "git",
                "diff",
                "--name-status",
                "--find-renames",
                "--no-ext-diff",
                f"{base_ref}..{range_head}",
                "--",
            ],
            [
                "git",
                "diff",
                "--cached",
                "--name-status",
                "--find-renames",
                "--no-ext-diff",
                "--",
            ],
            [
                "git",
                "diff",
                "--name-status",
                "--find-renames",
                "--no-ext-diff",
                "--",
            ],
            ["git", "ls-files", "--others", "--exclude-standard"],
        ]

    paths: set[str] = set()
    for command in commands:
        found, error = _run_git(command)
        if error:
            return None, error
        paths.update(found or [])
    return sorted(paths), None


def build_parser() -> argparse.ArgumentParser:
    """Build the investigation eligibility CLI parser."""
    parser = argparse.ArgumentParser(
        description="Check whether changed files qualify for investigation-only QA.",
    )
    parser.add_argument(
        "--base-ref",
        default="",
        help="Include committed changes from this session starting commit through HEAD.",
    )
    parser.add_argument(
        "--head-ref",
        default="",
        help="End at this commit and exclude working-tree changes.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.base_ref and not _COMMIT_PATTERN.fullmatch(args.base_ref):
        output = {
            "Eligible": False,
            "ChangedFiles": [],
            "StagedFiles": [],
            "Violations": [],
            "AllowedPaths": _ALLOWLIST_DISPLAY,
            "Error": f"Invalid base ref: {args.base_ref!r}",
        }
        print(json.dumps(output, indent=2))
        return 0

    if args.head_ref and not _COMMIT_PATTERN.fullmatch(args.head_ref):
        output = {
            "Eligible": False,
            "ChangedFiles": [],
            "StagedFiles": [],
            "Violations": [],
            "AllowedPaths": _ALLOWLIST_DISPLAY,
            "Error": f"Invalid head ref: {args.head_ref!r}",
        }
        print(json.dumps(output, indent=2))
        return 0

    if args.head_ref and not args.base_ref:
        output = {
            "Eligible": False,
            "ChangedFiles": [],
            "StagedFiles": [],
            "Violations": [],
            "AllowedPaths": _ALLOWLIST_DISPLAY,
            "Error": "--head-ref requires --base-ref",
        }
        print(json.dumps(output, indent=2))
        return 0

    if args.base_ref:
        changed_files, error = _changed_files(args.base_ref, args.head_ref)
    else:
        changed_files, error = _run_git(
            ["git", "diff", "--cached", "--name-status", "--find-renames", "--no-ext-diff", "--"]
        )
    if error:
        output = {
            "Eligible": False,
            "ChangedFiles": [],
            "StagedFiles": [],
            "Violations": [],
            "AllowedPaths": _ALLOWLIST_DISPLAY,
            "Error": error,
        }
        print(json.dumps(output, indent=2))
        return 0

    changed_files = changed_files or []
    violations = [path for path in changed_files if not _file_matches_allowlist(path)]

    output = {
        "Eligible": len(violations) == 0,
        "ChangedFiles": changed_files,
        "StagedFiles": changed_files,
        "Violations": violations,
        "AllowedPaths": _ALLOWLIST_DISPLAY,
    }

    print(json.dumps(output, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
