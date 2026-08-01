#!/usr/bin/env python3
"""Whole-repo taste-lint error-count ratchet (issue #3779).

``taste_lints.py`` exits 10 when it finds an error-severity violation, and
nothing in the repository has ever read that. ``run_taste_advisory`` in
``scripts/validation/git_hook_policy.py`` captures the exit code, prints
"findings are advisory", and returns 0; no workflow calls the linter at all. So
the ``error`` severity is decorative, and every commit touching a large file
prints an error the author correctly learns to ignore. That is the same training
signal that teaches people to ignore the naming and complexity rules riding in
the same output.

Existing debt is recorded in ``taste_count_baseline.txt``, measured with the
linter itself rather than a reimplementation of it. This freezes the total and
blocks growth, the same shape ``ruff_count_ratchet.py`` uses for lint debt.
Every currently-failing file keeps passing on day one and no contributor's
existing work breaks, but the count can only fall.

Scope is git-TRACKED files. The linter's own ``--directory`` mode walks the
filesystem with ``os.walk`` and no exclusions, so it would count untracked
scratch, nested worktrees, and vendored caches that happen to be on disk. That
is the phantom-count failure ``ruff_count_ratchet.py`` was written to avoid.

Every tracked path is passed in, not a filtered subset: ``run_lint`` already
skips anything outside its scannable-extension set, so filtering here would
duplicate that list and let the two drift.

Stdlib only: this runs by path in CI and must not depend on the project's
import graph.

Exit codes (AGENTS.md contract):
    0 - ok (count == baseline, or --update records a decrease)
    1 - regression (count != baseline, or baseline raised vs --base-ref)
    2 - config error (baseline missing or malformed, bad args)
    3 - external error (the linter could not run)
"""

from __future__ import annotations

import json
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.ci.count_ratchet import (
    EXIT_CONFIG,
    EXIT_EXTERNAL,
    EXIT_OK,
    EXIT_REGRESSION,
    build_parser,
    chunk,
    run,
    tracked_files,
)

__all__ = [
    "EXIT_CONFIG",
    "EXIT_EXTERNAL",
    "EXIT_OK",
    "EXIT_REGRESSION",
    "current_count",
    "main",
]

_BASELINE_PATH = Path(__file__).with_name("taste_count_baseline.txt")

_LINTER = Path(".claude/skills/taste-lints/scripts/taste_lints.py")

# taste_lints.py exit contract: 0 clean, 1 script error, 10 violations found.
# Only 0 and 10 mean the scan produced a trustworthy count.
_EXIT_CLEAN = 0
_EXIT_VIOLATIONS = 10


def current_count(repo_root: Path) -> int | None:
    """Total tracked-file error-severity violations, or None if the scan failed.

    Returning None rather than 0 on any failure is load-bearing. A zero from a
    crashed linter would look like a clean tree, and ``--update`` would write
    that zero into the baseline and permanently disarm the gate.
    """
    files = tracked_files(repo_root, ("*",))
    if files is None:
        return None
    if not files:
        return 0

    total = 0
    for batch in chunk(files):
        try:
            proc = subprocess.run(
                [sys.executable, str(_LINTER), "--format", "json", "--", *batch],
                cwd=repo_root,
                capture_output=True,
                text=True,
                errors="replace",
                encoding="utf-8",
                check=False,
            )
        except (FileNotFoundError, OSError) as exc:
            sys.stderr.write(f"taste-lints could not be launched: {exc}\n")
            return None
        if proc.returncode not in (_EXIT_CLEAN, _EXIT_VIOLATIONS):
            sys.stderr.write(f"taste-lints exited {proc.returncode}, which is not a scan result\n")
            sys.stderr.write(proc.stderr)
            return None
        try:
            report = json.loads(proc.stdout)
        except json.JSONDecodeError as exc:
            sys.stderr.write(f"taste-lints emitted unparseable JSON: {exc}\n")
            return None
        count = report.get("error_count")
        if not isinstance(count, int):
            sys.stderr.write("taste-lints report has no integer error_count\n")
            return None
        total += count
    return total


def list_violations(repo_root: Path) -> list[str] | None:
    """Return a human-readable line per error-severity violation, or None.

    Used by the ratchet to show WHICH violations are present on regression so
    contributors do not need a separate run to find them (issue #3902).
    """
    files = tracked_files(repo_root, ("*",))
    if files is None:
        return None
    if not files:
        return []

    lines: list[str] = []
    for batch in chunk(files):
        try:
            proc = subprocess.run(
                [sys.executable, str(_LINTER), "--format", "json", "--", *batch],
                cwd=repo_root,
                capture_output=True,
                text=True,
                errors="replace",
                encoding="utf-8",
                check=False,
            )
        except (FileNotFoundError, OSError):
            return None
        if proc.returncode not in (_EXIT_CLEAN, _EXIT_VIOLATIONS):
            return None
        try:
            report = json.loads(proc.stdout)
        except json.JSONDecodeError:
            return None
        for finding in report.get("findings", []):
            if not isinstance(finding, dict):
                continue
            if finding.get("severity") != "error":
                continue
            path = finding.get("path", "?")
            rule = finding.get("rule", "?")
            msg = finding.get("message", "")
            lines.append(f"{path}: [{rule}] {msg}")
    return lines


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser(
        "Whole-repo taste-lint error-count ratchet (issue #3779).", _BASELINE_PATH
    )
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)
    return run(
        args,
        label="taste count ratchet",
        counter=current_count,
        scan_error="taste-lints failed to run",
        regression_advice=(
            "New error-severity taste violations cannot merge. Fix them, or add a "
            "reasoned `# taste-lint: ignore <rule>` comment in the first 10 lines "
            "of the file explaining why the rule does not apply (issue #3779)."
        ),
        lister=list_violations,
    )


if __name__ == "__main__":
    sys.exit(main())
