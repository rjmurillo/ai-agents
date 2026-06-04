#!/usr/bin/env python3
"""Run the test suite and record a status + summary for the QA agent.

Extracted from the inline ``Run pytest`` step in
``.github/workflows/ai-pr-quality-gate.yml`` (ADR-006: no logic in YAML).
Issue #77: the QA agent runs via Copilot CLI with no shell access, so the
workflow executes pytest first and passes the result as agent context.

Behavior reproduced from the original pwsh block:

* If Python and ``pyproject.toml`` are both available, run pytest, preferring
  ``uv run pytest --tb=short -q`` and falling back to
  ``python -m pytest --tb=short -q``. The exit code is the primary signal:
  0 -> ``pytest_status=PASS``, non-zero -> ``pytest_status=FAIL``.
* The summary is the LAST output line matching ``passed|failed|error``, or
  ``No test summary available`` when no such line exists.
* On an execution error (the runner could not be launched),
  ``pytest_status=ERROR`` and the summary is the error message with newlines
  collapsed to spaces.
* When Python or ``pyproject.toml`` is absent, ``pytest_status=SKIPPED`` and the
  summary is ``Python test environment not available``.

Integration-point note (release-it rule): the pytest subprocess is bounded with
a ``--timeout`` (default 540s, inside the job's 10-minute budget) that the
original lacked; a timeout records ``pytest_status=ERROR``.

Input env vars:
    GITHUB_OUTPUT - path to the GitHub Actions output file.

Exit codes (ADR-035):
    0 - status and summary written (the step is continue-on-error; a test
        failure does NOT fail this step, matching the original)
    2 - GITHUB_OUTPUT is not set (config error)
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

_SUMMARY_PATTERN = re.compile(r"passed|failed|error")
_NO_SUMMARY = "No test summary available"


def summary_line(output: str) -> str:
    """Return the last line matching passed|failed|error, or a default."""

    matches = [line for line in output.split("\n") if _SUMMARY_PATTERN.search(line)]
    if not matches:
        return _NO_SUMMARY
    return matches[-1].strip()


def build_pytest_command() -> list[str]:
    """Return ``uv run pytest`` when uv is on PATH, else ``python -m pytest``."""

    args = ["--tb=short", "-q"]
    if shutil.which("uv"):
        return ["uv", "run", "pytest", *args]
    return [sys.executable, "-m", "pytest", *args]


def environment_ready(project_root: Path) -> bool:
    """Return True when Python and pyproject.toml are both available."""

    python_available = shutil.which("python") is not None or shutil.which("python3") is not None
    return python_available and (project_root / "pyproject.toml").is_file()


def run_pytest(command: list[str], timeout: float) -> tuple[str, str]:
    """Run pytest, returning ``(status, summary)``.

    Status is PASS/FAIL by exit code, or ERROR when the runner cannot launch or
    times out.
    """

    try:
        result = subprocess.run(
            command,
            timeout=timeout,
            capture_output=True,
            text=True,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return "ERROR", f"pytest timed out after {timeout}s"
    except OSError as exc:
        return "ERROR", str(exc).replace("\n", " ")

    output = (result.stdout or "") + (result.stderr or "")
    print(output)
    status = "PASS" if result.returncode == 0 else "FAIL"
    return status, summary_line(output)


def write_outputs(output_path: Path, status: str, summary: str) -> None:
    """Append ``pytest_status`` and ``pytest_summary`` to the output file."""

    with output_path.open("a", encoding="utf-8") as handle:
        handle.write(f"pytest_status={status}\n")
        handle.write(f"pytest_summary={summary}\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument(
        "--project-root",
        type=Path,
        default=Path.cwd(),
        help="Directory containing pyproject.toml.",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=540.0,
        help="pytest subprocess timeout in seconds (release-it: bound the call).",
    )
    args = parser.parse_args(argv)

    if environment_ready(args.project_root):
        status, summary = run_pytest(build_pytest_command(), args.timeout)
    else:
        status, summary = "SKIPPED", "Python test environment not available"

    github_output = os.environ.get("GITHUB_OUTPUT")
    if not github_output:
        print("error: GITHUB_OUTPUT is not set", file=sys.stderr)
        return 2

    write_outputs(Path(github_output), status, summary)
    return 0


if __name__ == "__main__":
    sys.exit(main())
