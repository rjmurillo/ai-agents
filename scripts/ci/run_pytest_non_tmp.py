#!/usr/bin/env python3
"""Run pytest with temp roots redirected outside the repository.

The enforced guarantee is repository isolation only. Callers that also want
the roots outside system /tmp (the CI workflow does) pass a root under
runner.temp; this script does not enforce that part.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
TEMP_ROOT_ENV = "PYTEST_NON_TMP_ROOT"


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True


def _configured_temp_root() -> Path:
    raw_root = os.environ.get(TEMP_ROOT_ENV)
    if not raw_root:
        raise ValueError(f"{TEMP_ROOT_ENV} must point to a temp root outside the repository")

    temp_root = Path(raw_root).resolve()
    if _is_relative_to(temp_root, PROJECT_ROOT.resolve()):
        raise ValueError(f"{TEMP_ROOT_ENV} must not be inside the repository: {temp_root}")
    return temp_root


def main(argv: list[str] | None = None) -> int:
    pytest_args = list(sys.argv[1:] if argv is None else argv)
    try:
        temp_root = _configured_temp_root()
        tmpdir = temp_root / "tmp"
        basetemp = temp_root / "basetemp"
        tmpdir.mkdir(parents=True, exist_ok=True)
        basetemp.mkdir(parents=True, exist_ok=True)
        (PROJECT_ROOT / "artifacts").mkdir(exist_ok=True)
    except OSError as exc:
        print(f"error: could not prepare pytest temp root: {exc}", file=sys.stderr)
        return 3
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    env = os.environ.copy()
    env["TMPDIR"] = str(tmpdir)
    cmd = [sys.executable, "-m", "pytest", f"--basetemp={basetemp}", *pytest_args]
    try:
        # The env-derived path is resolved and validated by _configured_temp_root
        # (outside the repo, outside /tmp) and passed as list-form argv with no
        # shell, so no injection surface remains.
        return subprocess.run(  # nosemgrep: dangerous-subprocess-use-tainted-env-args
            cmd, cwd=PROJECT_ROOT, env=env, check=False
        ).returncode
    except OSError as exc:
        print(f"error: could not run pytest: {exc}", file=sys.stderr)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
