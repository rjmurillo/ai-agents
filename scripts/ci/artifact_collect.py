#!/usr/bin/env python3
"""Collect recently modified artifacts from agent directories.

Replaces the bash 'Collect recent artifacts' block in
artifact-insight-scanner.yml (ADR-006).

ENV:
  SCAN_DEPTH_DAYS - number of days to look back (default: 7)
  RUNNER_TEMP     - directory for intermediate files (default: ".")
  GITHUB_OUTPUT   - path to step output file

Outputs:
  artifact_file  - path to file listing artifacts (one per line)
  artifact_count - number of artifacts found

EXIT CODES (ADR-035):
  0 - collection complete (zero artifacts is still success)
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


def write_github_output(key: str, value: str) -> None:
    """Append key=value to GITHUB_OUTPUT; fall back to stdout."""
    path = os.environ.get("GITHUB_OUTPUT", "")
    if path:
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(f"{key}={value}\n")
    else:
        print(f"{key}={value}")


def collect_artifacts(scan_depth_days: int) -> list[str]:
    """Return sorted-unique list of recently modified artifact paths."""
    import time

    cutoff = time.time() - scan_depth_days * 86400

    dirs_and_patterns: list[tuple[str, str]] = [
        (".agents/sessions", "*.md"),
        (".agents/sessions", "*.json"),
        (".agents/retrospective", "*.md"),
        (".agents/planning", "*.md"),
        (".agents/critique", "*.md"),
        (".agents/scratch", "*.md"),
    ]

    found: set[str] = set()
    for directory, pattern in dirs_and_patterns:
        base = Path(directory)
        if not base.is_dir():
            continue
        for p in base.rglob(pattern):
            try:
                if p.stat().st_mtime >= cutoff:
                    found.add(str(p))
            except OSError:
                pass

    return sorted(found)


def run(argv: list[str] | None = None) -> int:  # noqa: ARG001
    """Collect artifacts and set outputs."""
    scan_depth_days = int(os.environ.get("SCAN_DEPTH_DAYS", "7"))
    runner_temp = os.environ.get("RUNNER_TEMP", ".")
    print(f"Collecting artifacts modified in last {scan_depth_days} days...")

    artifact_file = Path(runner_temp) / "artifact-list.txt"
    artifacts = collect_artifacts(scan_depth_days)

    artifact_file.write_text("\n".join(artifacts) + ("\n" if artifacts else ""), encoding="utf-8")
    artifact_count = len(artifacts)

    write_github_output("artifact_file", str(artifact_file))
    write_github_output("artifact_count", str(artifact_count))
    print(f"Found {artifact_count} artifacts to scan")

    if artifact_count == 0:
        print(f"::notice::No recent artifacts found within {scan_depth_days} days")

    return 0


def main() -> int:
    """Entry point."""
    return run()


if __name__ == "__main__":
    sys.exit(main())
