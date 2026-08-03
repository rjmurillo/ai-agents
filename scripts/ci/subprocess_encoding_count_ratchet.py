"""Subprocess encoding convention count ratchet (issue #4261).

Counts calls to subprocess.run / subprocess.Popen / subprocess.check_output /
subprocess.check_call that use text mode (text= or encoding=) but omit errors=.
The count must not exceed the baseline. Improvements are allowed; regressions
block. The baseline may only fall.

Stdlib only: this runs by path in CI and must not depend on the project's
import graph.

Exit codes (AGENTS.md contract):
    0 - ok (count <= baseline)
    1 - regression (count > baseline, or baseline raised vs --base-ref)
    2 - config error (baseline missing or malformed, bad args)
    3 - external error (checker could not run)
"""

from __future__ import annotations

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

_BASELINE_PATH = Path(__file__).with_name("subprocess_encoding_count_baseline.txt")
_CHECKER = Path("scripts/validation/check_subprocess_encoding.py")
_FIXTURE_PREFIX = "tests/hooks/fixtures/"


def current_count(repo_root: Path) -> int | None:
    """Total subprocess encoding violations, or None if the checker failed."""
    py_files = tracked_files(repo_root, ("*.py", "**/*.py"))
    if py_files is None:
        return None

    # Filter out fixture exemptions and non-existent files
    py_files = [
        f for f in py_files
        if not f.startswith(_FIXTURE_PREFIX) and (repo_root / f).is_file()
    ]
    if not py_files:
        return 0

    checker = repo_root / _CHECKER
    if not checker.is_file():
        sys.stderr.write(f"Checker not found: {checker}\n")
        return None

    result = subprocess.run(
        [sys.executable, str(checker), *[str(repo_root / f) for f in py_files]],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=repo_root,
    )
    # Exit 0 = clean, exit 1 = violations found (both are valid counts)
    if result.returncode not in (0, 1):
        sys.stderr.write(
            f"Checker exited {result.returncode}:\n{result.stderr}\n"
        )
        return None

    # Count lines containing "uses text mode but omits errors="
    return sum(
        1 for line in result.stdout.splitlines()
        if "uses text mode but omits errors=" in line
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser(
        "Subprocess encoding convention count ratchet (issue #4261).",
        _BASELINE_PATH,
    )
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)
    return run(
        args,
        label="subprocess encoding count ratchet",
        counter=current_count,
        scan_error="check_subprocess_encoding.py failed to run",
        regression_advice=(
            "New subprocess calls that use text= or encoding= must also pass "
            "errors= (issue #4261). Add errors=\"replace\" to the call, or "
            "errors=\"strict\" if a decode failure is an error condition."
        ),
    )


if __name__ == "__main__":
    raise SystemExit(main())

