#!/usr/bin/env python3
"""Verify every agent verdict file was downloaded before aggregation.

Extracted from the inline ``Validate artifact download`` step in
``.github/workflows/ai-pr-quality-gate.yml`` (ADR-006: no logic in YAML).

For each of the ten quality-gate agents the step checks that
``ai-review-results/<agent>-verdict.txt`` exists. If any are missing it prints
``::error::`` annotations and exits 1; otherwise it confirms all files present.

The agent roster comes from ``quality_gate_agents.QUALITY_GATE_AGENTS`` so the
workflow has a single source of truth. The original block hardcoded the same
ten names in the same order.

Args:
    --results-dir  Directory holding the verdict files (default
                   ``ai-review-results``).

Exit codes (ADR-035):
    0 - all required verdict files are present
    1 - one or more verdict files are missing (logic/validation error)
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
_GITHUB_SCRIPTS = _SCRIPT_DIR.parents[1] / ".github" / "scripts"
sys.path.insert(0, str(_GITHUB_SCRIPTS))

from quality_gate_agents import QUALITY_GATE_AGENTS  # noqa: E402


def find_missing(results_dir: Path) -> list[str]:
    """Return verdict file names that are absent from ``results_dir``."""

    missing: list[str] = []
    for agent in QUALITY_GATE_AGENTS:
        verdict_file = results_dir / f"{agent}-verdict.txt"
        if not verdict_file.exists():
            missing.append(f"{agent}-verdict.txt")
    return missing


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument(
        "--results-dir",
        type=Path,
        default=Path("ai-review-results"),
        help="Directory holding the downloaded verdict files.",
    )
    args = parser.parse_args(argv)

    print("Checking for required verdict files...")
    missing = find_missing(args.results_dir)

    if missing:
        print("::error::Artifact download incomplete - missing files:")
        for name in missing:
            print(f"::error::  - {name}")
        print(
            "::error::This indicates agent review jobs failed or artifacts "
            "were not uploaded"
        )
        return 1

    print("✓ All required verdict files present")
    return 0


if __name__ == "__main__":
    sys.exit(main())
