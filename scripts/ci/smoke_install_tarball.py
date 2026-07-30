#!/usr/bin/env python3
"""Install CLI tarball into a temp directory and run ai-agents init.

Replaces the PowerShell 'Install tarball and run init' block in
cli-smoke.yml (ADR-006).

ENV:
  TARBALL       - absolute path to the packed tarball
  GITHUB_OUTPUT - path to the step output file

Outputs:
  demo - absolute path to the demo directory

EXIT CODES (ADR-035):
  0 - install and init succeeded
  N - subprocess returned N
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path


def write_github_output(key: str, value: str) -> None:
    """Append key=value to GITHUB_OUTPUT; fall back to stdout."""
    path = os.environ.get("GITHUB_OUTPUT", "")
    if path:
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(f"{key}={value}\n")
    else:
        print(f"{key}={value}")


def run(argv: list[str] | None = None) -> int:  # noqa: ARG001
    """Install the tarball and run ai-agents init."""
    tarball = os.environ.get("TARBALL", "")
    if not tarball:
        print("::error::TARBALL env var is required")
        return 1

    work_dir = tempfile.mkdtemp(prefix="smoke-")
    print(f"Working directory: {work_dir}")

    def _run(cmd: list[str]) -> int:
        result = subprocess.run(cmd, cwd=work_dir, check=False)
        return result.returncode

    rc = _run(["npm", "init", "-y"])
    if rc != 0:
        print(f"::error::npm init exited {rc}")
        return rc

    rc = _run(["npm", "install", "--silent", tarball])
    if rc != 0:
        print(f"::error::npm install exited {rc}")
        return rc

    demo_dir = Path(work_dir) / "demo"
    demo_dir.mkdir()

    rc = _run(
        ["npm", "exec", "--yes", "--package", tarball, "--", "ai-agents", "init", "demo", "--yes"]
    )
    if rc != 0:
        print(f"::error::ai-agents init exited {rc}")
        return rc

    write_github_output("demo", str(demo_dir))
    print(f"Installed to {demo_dir}")
    return 0


def main() -> int:
    """Entry point."""
    return run()


if __name__ == "__main__":
    sys.exit(main())
