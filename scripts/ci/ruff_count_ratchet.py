#!/usr/bin/env python3
"""Whole-repo ruff count ratchet: fail only when the total violation count grows.

Issue #2993, regression guard option C. This complements the diff-scoped
``scripts/ci/ruff_ratchet.py`` (which lints only the changed files and so lets a
contributor inherit latent debt the moment they touch a shared file). This gate
freezes the whole-repo violation total in ``ruff_count_baseline.txt`` and fails a
run only when the count INCREASES. A decrease is allowed and can lower the
baseline with ``--update``, so the pre-existing debt drains monotonically and can
never climb back.

Stdlib only: this runs by path in CI (``python scripts/ci/ruff_count_ratchet.py``)
and must not depend on the project's import graph.

Exit codes (AGENTS.md contract):
    0 - ok (count <= baseline)
    1 - regression (count > baseline)
    2 - config error (baseline missing or malformed, bad args)
    3 - external error (ruff could not run)
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path

EXIT_OK = 0
EXIT_REGRESSION = 1
EXIT_CONFIG = 2
EXIT_EXTERNAL = 3

_BASELINE_PATH = Path(__file__).with_name("ruff_count_baseline.txt")
_EXCLUDE = ".wt"


def current_count(repo_root: Path) -> int | None:
    """Total whole-repo ruff violations, or None when ruff could not run.

    Uses ``json-lines`` so the count is one violation per output line, robust
    across ruff output-format changes. ruff exits 1 when violations exist and 0
    when clean; both are valid. Any other exit code is an environment failure.
    """
    try:
        proc = subprocess.run(
            ["ruff", "check", ".", "--exclude", _EXCLUDE, "--output-format", "json-lines"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )
    except (FileNotFoundError, OSError) as exc:
        sys.stderr.write(f"ruff could not be launched: {exc}\n")
        return None
    if proc.returncode not in (0, 1):
        sys.stderr.write(proc.stderr)
        return None
    return sum(1 for line in proc.stdout.splitlines() if line.strip())


def read_baseline(path: Path) -> int | None:
    """Baseline integer, or None when the file is missing or not an integer."""
    try:
        return int(path.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return None


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Whole-repo ruff violation-count ratchet (issue #2993)."
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path.cwd(),
        help="Repository root (default: current working directory).",
    )
    parser.add_argument(
        "--baseline",
        type=Path,
        default=_BASELINE_PATH,
        help="Baseline count file (default: alongside this script).",
    )
    parser.add_argument(
        "--update",
        action="store_true",
        help="Lower the baseline to the current count when the count improved.",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)

    baseline = read_baseline(args.baseline)
    if baseline is None:
        print(f"error: baseline missing or malformed: {args.baseline}", file=sys.stderr)
        return EXIT_CONFIG

    count = current_count(args.repo_root.resolve())
    if count is None:
        print("error: ruff failed to run", file=sys.stderr)
        return EXIT_EXTERNAL

    if count > baseline:
        print(
            f"ruff count ratchet: REGRESSION. {count} violations > baseline {baseline} "
            f"(+{count - baseline}). New ruff violations cannot merge; fix them or, if "
            f"they are unavoidable, coordinate a baseline change (issue #2993).",
            file=sys.stderr,
        )
        return EXIT_REGRESSION

    if count < baseline:
        message = f"ruff count ratchet: improved {baseline} -> {count} (-{baseline - count})."
        if args.update:
            args.baseline.write_text(f"{count}\n", encoding="utf-8")
            message += " Baseline lowered."
        else:
            message += " Run with --update to lower the baseline."
        print(message)
        return EXIT_OK

    print(f"ruff count ratchet: OK (count == baseline {baseline}).")
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
