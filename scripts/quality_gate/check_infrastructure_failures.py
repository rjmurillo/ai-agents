#!/usr/bin/env python3
"""Detect agent infrastructure failures and add the label, best-effort.

Extracted from the inline ``Check for infrastructure failures and add label``
step in ``.github/workflows/ai-pr-quality-gate.yml`` (ADR-006: no logic in
YAML). Issue #328: add an ``infrastructure-failure`` label when an agent's
retry logic is exhausted.

The step reads, for each of the ten quality-gate agents,
``ai-review-results/<agent>-infrastructure-failure.txt`` and
``ai-review-results/<agent>-retry-count.txt``. When any agent's infra flag is
``true`` it emits a ``::notice::`` per agent, then tries to add the
``infrastructure-failure`` label via the gh CLI.

This is best-effort. The workflow step is ``continue-on-error: true`` and the
original block exited 0 even when gh auth failed or the label add failed. This
script preserves that: it returns 0 in every non-config path.

Integration-point note (release-it rule): the gh calls are bounded with a
``--gh-timeout`` (default 60s) that the original lacked. A timeout is logged as
a ``::warning::`` and does not fail the step.

Input env vars:
    GH_TOKEN, PR_NUMBER, GITHUB_REPOSITORY - consumed by the gh CLI.

Args:
    --results-dir  Directory holding the infra/retry files (default
                   ``ai-review-results``).
    --gh-timeout   gh subprocess timeout in seconds (default 60).

Exit codes (ADR-035):
    0 - detection ran (label add is best-effort; failures do not fail the step)
    1 - unsafe results directory
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

try:
    from .path_utils import REPOSITORY_ROOT, resolve_workspace_path
except ImportError:  # pragma: no cover - script execution path
    from path_utils import REPOSITORY_ROOT, resolve_workspace_path

_GITHUB_SCRIPTS = REPOSITORY_ROOT / ".github" / "scripts"
sys.path.insert(0, str(_GITHUB_SCRIPTS))

from quality_gate_agents import QUALITY_GATE_AGENTS  # noqa: E402

_LABEL = "infrastructure-failure"


@dataclass(frozen=True)
class InfraFinding:
    """One agent's infrastructure-failure detection result."""

    agent: str
    retry_count: int


def _read_raw(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return None


def _read_retry_count(results_dir: Path, agent: str) -> int:
    """Return the trimmed retry count, or 0 when empty/missing/non-numeric."""

    raw = _read_raw(results_dir / f"{agent}-retry-count.txt")
    if not raw:
        return 0
    try:
        return int(raw.strip())
    except ValueError:
        return 0


def detect_failures(results_dir: Path) -> list[InfraFinding]:
    """Return findings for agents whose infra flag file is ``true``."""

    findings: list[InfraFinding] = []
    for agent in QUALITY_GATE_AGENTS:
        raw_flag = _read_raw(results_dir / f"{agent}-infrastructure-failure.txt")
        if raw_flag is None:
            continue
        flag = raw_flag.strip() if raw_flag else "false"
        if flag == "true":
            findings.append(
                InfraFinding(agent=agent, retry_count=_read_retry_count(results_dir, agent))
            )
    return findings


def _gh_authenticated(timeout: float) -> bool:
    """Return True when ``gh auth status`` exits 0 within the timeout."""

    try:
        result = subprocess.run(
            ["gh", "auth", "status"],
            timeout=timeout,
            capture_output=True,
            check=False,
        )
    except subprocess.TimeoutExpired:
        print("::warning::gh auth status timed out")
        return False
    except FileNotFoundError:
        print("::warning::gh CLI not found, cannot add label")
        return False
    return result.returncode == 0


def _add_label(pr_number: str, repository: str, timeout: float) -> None:
    """Add the infrastructure-failure label, best-effort (never raises)."""

    try:
        result = subprocess.run(
            ["gh", "pr", "edit", pr_number, "--repo", repository, "--add-label", _LABEL],
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired:
        print("::warning::Adding infrastructure-failure label timed out")
        return
    except FileNotFoundError:
        print("::warning::gh CLI not found, cannot add label")
        return
    if result.returncode != 0:
        print(
            f"::warning::Failed to add infrastructure-failure label "
            f"(exit code: {result.returncode})"
        )
    else:
        print("Successfully added infrastructure-failure label")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument(
        "--results-dir",
        type=Path,
        default=Path("ai-review-results"),
        help="Directory holding the infra/retry files.",
    )
    parser.add_argument(
        "--gh-timeout",
        type=float,
        default=60.0,
        help="gh subprocess timeout in seconds (release-it: bound the call).",
    )
    args = parser.parse_args(argv)

    try:
        results_dir = resolve_workspace_path(args.results_dir, "results-dir")
    except ValueError as exc:
        print(f"::error::{exc}", file=sys.stderr)
        return 1

    findings = detect_failures(results_dir)

    for finding in findings:
        print(
            f"::notice::Infrastructure failure detected for {finding.agent} "
            f"agent (retries: {finding.retry_count})"
        )

    if not findings:
        print("No infrastructure failures detected")
        return 0

    print("::warning::Infrastructure failures detected - adding infrastructure-failure label")
    attempts = ", ".join(f"{f.agent}: {f.retry_count} retries" for f in findings)
    print(f"Retry attempts: {attempts}")

    pr_number = os.environ.get("PR_NUMBER", "").strip()
    repository = os.environ.get("GITHUB_REPOSITORY", "").strip()
    if not pr_number or not repository:
        print("::warning::PR_NUMBER or GITHUB_REPOSITORY is missing, cannot add label")
        return 0

    if not _gh_authenticated(args.gh_timeout):
        print("::warning::gh CLI authentication failed, cannot add label")
        return 0

    _add_label(pr_number, repository, args.gh_timeout)
    return 0


if __name__ == "__main__":
    sys.exit(main())
