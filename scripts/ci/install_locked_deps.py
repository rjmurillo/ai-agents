#!/usr/bin/env python3
"""Install Python dependencies from the resolution ``uv.lock`` pins.

Issue #3603. The composite action ran ``uv pip install --system -e ".[dev]"``,
which re-resolves from ``pyproject.toml`` and never reads the lock. The lock
existed and nothing in CI consumed it.

Measured against the lock on 2026-07-28, 30 of 111 packages drifted, including
mypy 2.1.0 to 2.3.0, pytest 9.0.3 to 9.1.1, ruff 0.15.16 to 0.15.22,
coverage 7.13.1 to 7.15.2, and pydantic 2.12.5 to 2.13.4. CI graded every pull
request with different tools than the lock pins, so a tool release could turn a
green branch red with no repository change, and a lint or type regression could
land because the resolver picked an older tool than the contributor ran.

``uv sync --frozen`` is the idiomatic call and is not usable here. It installs
into a project ``.venv``, but 148 steps across 15 workflows invoke ``python``,
``pytest``, ``ruff``, and ``mypy`` bare and depend on the ``--system`` install
being importable. Exporting the lock keeps ``--system`` intact.

``--require-hashes`` is not usable either. ``pyproject.toml`` declares
``[tool.uv] override-dependencies`` for click and mcp. Run from the repository
root, uv injects those hashless overrides and pip refuses with "no hash provided
for click==8.3.3". Run from a neutral directory, the overrides are absent and
resolution fails outright. The export still pins every version exactly, which is
what the acceptance criterion asks for.

The export is platform-universal: it carries markers such as
``pywin32==311 ; sys_platform == 'win32'``, so one export serves both the Linux
and Windows runners. ``--no-emit-project`` excludes the local project, which is
why it is installed separately with ``--no-deps``: installing it normally would
re-resolve the pinned set.

Stdlib only, by necessity. This runs before the dependencies it installs exist.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

EXTRA = "dev"
EXPORT_NAME = "uv-locked-requirements.txt"


def run(command: list[str]) -> None:
    """Run ``command`` and exit with its status when it fails.

    ``check=True`` would raise and print a traceback, which buries the tool's
    own error message in CI output that a contributor has to scroll past.
    """
    print(f"$ {' '.join(command)}", flush=True)
    completed = subprocess.run(command, check=False)
    if completed.returncode != 0:
        sys.exit(completed.returncode)


FALLBACK_TEMP = Path("/tmp")


def _export_path() -> Path:
    """Return the lock-export path, refusing a RUNNER_TEMP we cannot vouch for.

    ``RUNNER_TEMP`` is the only externally-set value that reaches argv here.
    The subprocess calls are list-form with ``shell=False``, so no shell parses
    them and an argument cannot become a command. What it can become is an
    option: a value starting with ``-`` yields an argv entry shaped like a flag
    rather than a path (CWE-88). A relative value is a different failure, an
    export written somewhere the caller did not intend.

    Neither shape is worth guessing at, so both fall back to ``/tmp``, which is
    what an unset ``RUNNER_TEMP`` already produced.
    """
    raw = os.environ.get("RUNNER_TEMP", "")
    candidate = Path(raw)
    if not raw or raw.startswith("-") or not candidate.is_absolute():
        return FALLBACK_TEMP / EXPORT_NAME
    return candidate / EXPORT_NAME


def main(argv: list[str] | None = None) -> int:
    """Install from the lock, or fall back when there is nothing to lock to."""
    root = Path(argv[0]) if argv else Path.cwd()
    print("Installing Python dependencies...")

    if not (root / "pyproject.toml").is_file():
        print("No pyproject.toml found, skipping dependency installation")
        return 0

    if not (root / "uv.lock").is_file():
        # A consumer of this action without a lock still has to work. It gets
        # the previous unpinned behavior rather than a hard failure.
        print("No uv.lock found, falling back to an unpinned resolve")
        run(["uv", "pip", "install", "--system", "-e", ".[dev]"])
        return 0

    export = _export_path()
    run(
        [
            "uv",
            "export",
            "--frozen",
            "--extra",
            EXTRA,
            "--no-emit-project",
            "--output-file",
            str(export),
        ]
    )
    run(["uv", "pip", "install", "--system", "-r", str(export)])
    run(["uv", "pip", "install", "--system", "--no-deps", "-e", "."])
    print("Python dependencies installed from uv.lock")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
