#!/usr/bin/env python3
"""Probe the agent infrastructure a workflow run depends on.

Extracted from ``.github/actions/check-agent-infrastructure/action.yml`` under
ADR-006 (no logic in workflow YAML). Issue #3527.

The composite action this replaces answers one question: can agent workflows
run here? It probes three things and grades them:

* ``ready``: the GitHub CLI is present, authenticated, and Copilot is reachable.
* ``degraded``: the CLI is present and authenticated but Copilot is missing.
* ``unavailable``: anything else.

Every probe is advisory. A missing tool produces a warning annotation and a
summary line, never a non-zero exit, because the caller decides what to do
with a degraded environment. Copilot is reached either as its own binary or
as a ``gh`` extension, and both spellings count.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

_READY = "ready"
_DEGRADED = "degraded"
_UNAVAILABLE = "unavailable"
# A GITHUB_OUTPUT heredoc delimiter must not appear in the value it wraps.
_DELIMITER = "EOF_SUMMARY"


@dataclass
class Probe:
    """The outcome of probing the agent toolchain."""

    github_cli: bool = False
    copilot: bool = False
    auth_valid: bool = False
    summary: list[str] = field(default_factory=list)
    annotations: list[str] = field(default_factory=list)

    @property
    def status(self) -> str:
        """Grade the environment the way the caller's ``if`` conditions expect."""
        if self.github_cli and self.auth_valid and self.copilot:
            return _READY
        if self.github_cli and self.auth_valid:
            return _DEGRADED
        return _UNAVAILABLE


def _first_line(argv: list[str]) -> str | None:
    """Return the first line of a command's output, or None when it fails."""
    sys.stdout.flush()
    completed = subprocess.run(
        argv,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if completed.returncode != 0:
        return None
    return completed.stdout.splitlines()[0] if completed.stdout.splitlines() else ""


def _probe_github_cli(probe: Probe) -> None:
    if shutil.which("gh") is None:
        probe.summary.append("GitHub CLI: NOT FOUND")
        probe.annotations.append("::warning::GitHub CLI not found. Agent workflows require gh.")
        return
    probe.github_cli = True
    version = _first_line(["gh", "--version"]) or "unknown"
    probe.summary.append(f"GitHub CLI: {version}")
    probe.annotations.append(f"::notice::GitHub CLI available ({version})")


def _probe_auth(probe: Probe) -> None:
    if not probe.github_cli:
        probe.summary.append("Authentication: skipped (no gh CLI)")
        return
    login = _first_line(["gh", "api", "user", "-q", ".login"])
    if login is None:
        probe.summary.append("Authentication: FAILED")
        probe.annotations.append(
            "::warning::GitHub API authentication failed. Check the GitHub API token."
        )
        return
    probe.auth_valid = True
    probe.summary.append(f"Authentication: valid (user: {login})")
    probe.annotations.append(f"::notice::GitHub API authenticated as {login}")


def _probe_copilot(probe: Probe) -> None:
    if shutil.which("copilot") is not None:
        probe.copilot = True
        version = _first_line(["copilot", "--version"]) or "unknown"
        probe.summary.append(f"Copilot CLI: {version}")
        probe.annotations.append(f"::notice::Copilot CLI available ({version})")
        return
    if probe.github_cli:
        probed = _first_line(["gh", "copilot", "--version"])
        if probed is not None:
            probe.copilot = True
            version = probed or "unknown"
            probe.summary.append(f"Copilot CLI (via gh extension): {version}")
            probe.annotations.append(
                f"::notice::Copilot CLI available via gh extension ({version})"
            )
            return
    probe.summary.append("Copilot CLI: NOT FOUND")
    probe.annotations.append(
        "::warning::Copilot CLI not available. Configure COPILOT_GITHUB_TOKEN "
        "or install gh copilot extension."
    )


def run_probes() -> Probe:
    """Probe the toolchain and return the graded result."""
    probe = Probe()
    _probe_github_cli(probe)
    _probe_auth(probe)
    _probe_copilot(probe)
    probe.summary.append(f"Overall: {probe.status}")
    return probe


def render_outputs(probe: Probe) -> str:
    """Render the step outputs, escaping any value that could close the heredoc."""
    summary = "\n".join(line.replace(_DELIMITER, _DELIMITER + "_ESCAPED") for line in probe.summary)
    return (
        f"github-cli-available={str(probe.github_cli).lower()}\n"
        f"copilot-available={str(probe.copilot).lower()}\n"
        f"auth-valid={str(probe.auth_valid).lower()}\n"
        f"overall-status={probe.status}\n"
        f"summary<<{_DELIMITER}\n{summary}\n{_DELIMITER}\n"
    )


def main(argv: list[str] | None = None) -> int:
    argparse.ArgumentParser(description=__doc__).parse_args(argv)

    probe = run_probes()
    for annotation in probe.annotations:
        print(annotation)

    print("")
    print("=== Infrastructure Health Check ===")
    for line in probe.summary:
        print(f"  {line}")
    print("==================================")

    body = render_outputs(probe)
    output_path = os.environ.get("GITHUB_OUTPUT")
    if not output_path:
        print(body, end="")
        return 0
    with Path(output_path).open("a", encoding="utf-8") as handle:
        handle.write(body)
    return 0


if __name__ == "__main__":
    sys.exit(main())
