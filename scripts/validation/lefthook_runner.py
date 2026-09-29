#!/usr/bin/env python3
"""Resolve and run Lefthook for the generated Git hook shims (issue #5431).

`lefthook.yml` sets ``lefthook: python3 scripts/validation/lefthook_runner.py``.
Lefthook bakes that string into ``.git/hooks/*`` as::

    elif test -n "python3 scripts/validation/lefthook_runner.py"
    then
      python3 scripts/validation/lefthook_runner.py "$@"

The ``test -n "<literal>"`` is always true (verified against a generated
shim), so no fallback below it in the shim ever runs. This program owns the
fallback instead: it tries the pinned runtime first, then a locally installed
binary, then fails with a diagnosis.

Resolution order:

1. ``uv run --frozen lefthook`` when a ``version`` probe exits 0. The probe
   separates "uv cannot resolve Lefthook" from "a hook job failed", because
   both surface as a non-zero exit from the real run.
2. ``lefthook`` on PATH, then ``node_modules/.bin/lefthook`` in the repo.
3. No candidate: print a diagnosis to stderr and exit 3.

``LEFTHOOK_BIN`` is handled by the shim before this program runs, so it is not
read here. Bypass switches stay forbidden by ADR-086 and are not offered.

Exit codes: the child's exit status when a runner started, 3 (external) when no
runner is available.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path

EXIT_UNAVAILABLE = 3
PROBE_TIMEOUT_SECONDS = 60
_UV_RUNNER = ("uv", "run", "--frozen", "lefthook")
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
REPAIR_COMMAND = "uv sync --frozen --extra dev"

DIAGNOSIS = f"""\
lefthook_runner: Lefthook itself is unavailable. Your change is not the cause.
Tried: 'uv run --frozen lefthook version' (failed or uv missing), then
'lefthook' on PATH and node_modules/.bin/lefthook (not found).
Bypassing the hook (--no-verify, LEFTHOOK=0, LEFTHOOK_BIN, LEFTHOOK_EXCLUDE)
is forbidden by ADR-086. Repair the runtime instead:
  1. Restore the locked environment while online: {REPAIR_COMMAND}
  2. Or install a Lefthook binary onto PATH, then retry the git command.
"""


def _uv_is_ready() -> bool:
    """Return True when ``uv run --frozen lefthook version`` exits 0."""
    if shutil.which("uv") is None:
        return False
    try:
        probe = subprocess.run(
            [*_UV_RUNNER, "version"],
            capture_output=True,
            timeout=PROBE_TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return probe.returncode == 0


def _local_binary(project_root: Path) -> str | None:
    """Return a Lefthook binary from PATH or the repo's node_modules, else None."""
    on_path = shutil.which("lefthook")
    if on_path is not None:
        return on_path
    return shutil.which("lefthook", path=str(project_root / "node_modules" / ".bin"))


def resolve_command(project_root: Path = _PROJECT_ROOT) -> list[str] | None:
    """Return the argv prefix that runs Lefthook, or None when none works."""
    if _uv_is_ready():
        return list(_UV_RUNNER)
    binary = _local_binary(project_root)
    return [binary] if binary is not None else None


def main(argv: Sequence[str] | None = None) -> int:
    """Run Lefthook with ``argv`` through the first working runner."""
    arguments = list(sys.argv[1:] if argv is None else argv)
    command = resolve_command()
    if command is None:
        sys.stderr.write(DIAGNOSIS)
        return EXIT_UNAVAILABLE
    try:
        return subprocess.run([*command, *arguments], check=False).returncode
    except OSError as error:
        sys.stderr.write(f"lefthook_runner: cannot start {command[0]}: {error}\n{DIAGNOSIS}")
        return EXIT_UNAVAILABLE


if __name__ == "__main__":
    sys.exit(main())
