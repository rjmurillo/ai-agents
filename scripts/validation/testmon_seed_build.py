#!/usr/bin/env python3
"""Run the pre-push pytest step for the CI seed job and record whether it finished clean.

The `testmon-seed` job in `.github/workflows/pytest.yml` calls this instead of
branching in YAML (issue #6239). The hook exits 0 only when every partition ran
to completion and passed. Anything else (a failed partition, a budget kill, a
signal) leaves a partial database, so `complete=true` is written to the step
output only on exit 0 and the upload step keys on it. No failure is hidden: the
script exits with the hook's failure code (a signal, reported as a negative code,
becomes 1), so a failing test, a budget kill or a signal turns the seed job red.
The job is outside `test-result` needs, so a red seed never changes
`Run Python Tests`.

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
    """Run the hook in ``root``; write ``complete=true`` on exit 0; return the failure code.

    Returns 0 only for a clean run that was recorded. A nonzero hook code is
    returned as is (negative codes become 1), and nothing is written, so the
    upload step skips.
    """
    returncode = runner(
        [sys.executable, str(HOOK_SCRIPT), "pytest"], cwd=root, check=False
    ).returncode
    if returncode != 0:
        print(f"::error::the seed run exited {returncode}; no database is uploaded")
        return returncode if returncode > 0 else 1
    if output_path is None:
        print(f"::error::{OUTPUT_ENV} is not set; the clean run cannot be recorded")
        return 1
    with output_path.open("a", encoding="utf-8") as handle:
        handle.write("complete=true\n")
    return 0


def main() -> int:
    raw = os.environ.get(OUTPUT_ENV)
    return run_build(Path.cwd(), Path(raw) if raw else None)


if __name__ == "__main__":  # pragma: no cover - exercised by the workflow job
    sys.exit(main())
