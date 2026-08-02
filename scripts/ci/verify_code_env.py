#!/usr/bin/env python3
"""Verify the development toolchain a CI job just set up.

Extracted from ``.github/actions/setup-code-env/action.yml`` under ADR-006
(no logic in workflow YAML). Issue #3532.

Only one check can fail the job: ``lefthook check-install``, and only when the
caller asked for both git hooks and Python. Everything else is reporting. A
missing optional tool prints nothing and is not an error, because this action
is used by jobs that deliberately enable only part of the toolchain.
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys

# The module name is interpolated into a pwsh -Command string, so it is
# constrained to an allowlist rather than escaped (CWE-78).
_MODULE_NAME = re.compile(r"\A[A-Za-z][A-Za-z0-9-]*\Z")
_HEADER = "=== Setup Verification ==="
_COMPLETE = (
    "[PASS] Setup complete. Development tools ready: Node.js, markdownlint-cli2, "
    "Python (if enabled), GitHub CLI (if available), Pester (if enabled), "
    "git hooks (if configured)."
)


def _run(argv: list[str]) -> subprocess.CompletedProcess[str]:
    sys.stdout.flush()
    return subprocess.run(
        argv,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def verify_lefthook() -> int:
    """Run the one check that can fail the job. Returns its exit code."""
    completed = _run(["uv", "run", "--frozen", "--extra", "dev", "lefthook", "check-install"])
    print(completed.stdout, end="")
    if completed.returncode != 0:
        print(
            f"[FAIL] Lefthook installation verification failed (exit code {completed.returncode})"
        )
        return completed.returncode
    print("[PASS] Lefthook installation verified")
    return 0


def _module_version(name: str) -> str | None:
    """Return an installed PowerShell module's version, or None."""
    if not _MODULE_NAME.match(name):
        raise ValueError(f"unsupported module name: {name!r}")
    if shutil.which("pwsh") is None:
        return None
    completed = _run(
        [
            "pwsh",
            "-NoProfile",
            "-Command",
            f"(Get-Module -ListAvailable -Name {name} | Select-Object -First 1).Version.ToString()",
        ]
    )
    if completed.returncode != 0:
        return None
    version = completed.stdout.strip()
    return version or None


def report_tools(*, python: bool, pester: bool) -> None:
    """Print the availability report. Nothing here can fail the job."""
    if shutil.which("npx") is not None:
        print("[PASS] npx is available")
        # --help may return non-zero; the call warms the npx cache either way.
        _run(["npx", "markdownlint-cli2@0.23.1", "--help"])
        print("[PASS] markdownlint-cli2 is installed")

    if shutil.which("gh") is not None:
        print("[PASS] GitHub CLI is available for workflow monitoring")

    if python:
        if shutil.which("python3") is not None:
            python_version = _run(["python3", "--version"]).stdout.strip()
            print(f"[PASS] {python_version} is installed")
        if shutil.which("ruff") is not None:
            print("[PASS] ruff is available for Python linting")
        if shutil.which("pytest") is not None:
            print("[PASS] pytest is available for Python testing")

    if pester:
        pester_version = _module_version("Pester")
        if pester_version:
            print(f"[PASS] Pester {pester_version} is installed")

    yaml_version = _module_version("powershell-yaml")
    if yaml_version:
        print(f"[PASS] powershell-yaml {yaml_version} is installed")


def _enabled(name: str) -> bool:
    return os.environ.get(name) == "true"


def main(argv: list[str] | None = None) -> int:
    argparse.ArgumentParser(description=__doc__).parse_args(argv)

    git_hooks = _enabled("ENABLE_GIT_HOOKS")
    python = _enabled("ENABLE_PYTHON")
    pester = _enabled("ENABLE_PESTER")

    print("")
    print(_HEADER)

    if git_hooks and python:
        code = verify_lefthook()
        if code != 0:
            return code

    autofix = os.environ.get("SKIP_AUTOFIX", "0")
    print(f"SKIP_AUTOFIX: {autofix} (0=enabled, 1=disabled)")
    print("")

    report_tools(python=python, pester=pester)

    print("")
    print(_COMPLETE)
    return 0


if __name__ == "__main__":
    sys.exit(main())
