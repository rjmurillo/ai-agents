#!/usr/bin/env python3
"""Run the pre-push pytest step for the CI seed job and record whether it finished clean.

The `testmon-seed` job in `.github/workflows/pytest.yml` calls this instead of
branching in YAML (issue #6239). The hook exits 0 only when every partition ran
to completion and passed. Anything else (a failed partition, a budget kill, a
signal) leaves a partial database, so `complete=true` is written to the step
output only on exit 0 and the upload step keys on it. This script itself always
exits 0, so a failing test run shows as a warning and not a red seed job;
`Run Python Tests` owns the pass or fail verdict.

Standard library only: the workflow runs it by path, where `scripts.*` imports
need a sys.path bootstrap this script does not otherwise want.
"""

from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

HOOK_SCRIPT = Path(__file__).resolve().parent / "git_hook_policy.py"
OUTPUT_ENV = "GITHUB_OUTPUT"

Runner = Callable[..., "subprocess.CompletedProcess[bytes]"]


def run_build(root: Path, output_path: Path | None, runner: Runner = subprocess.run) -> int:
    """Run the hook in ``root``; write ``complete=true`` to ``output_path`` on exit 0."""
    result = runner([sys.executable, str(HOOK_SCRIPT), "pytest"], cwd=root, check=False)
    if result.returncode != 0:
        print(f"::warning::the seed run exited {result.returncode}; no database is uploaded")
        return 0
    if output_path is None:
        print(f"::warning::{OUTPUT_ENV} is not set; the clean run cannot be recorded")
        return 0
    with output_path.open("a", encoding="utf-8") as handle:
        handle.write("complete=true\n")
    return 0


def main() -> int:
    raw = os.environ.get(OUTPUT_ENV)
    return run_build(Path.cwd(), Path(raw) if raw else None)


if __name__ == "__main__":  # pragma: no cover - exercised by the workflow job
    sys.exit(main())
