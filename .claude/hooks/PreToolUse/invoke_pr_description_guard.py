#!/usr/bin/env python3
"""Block git push when the open PR description does not match the diff.

Thin adapter over :mod:`push_guard_base`. Activates whenever the push
changeset is non-empty (glob ``*``) and runs
``scripts/validation/pr_description.py`` in CI mode against the active
PR. Real CRITICAL mismatches (file mentioned but not in diff) block the
push. Tooling failures (missing gh, no PR open, timeout, OSError) all
fail-open so a temporary infrastructure problem never wedges the user.

Hook Type: PreToolUse
Exit Codes (Claude Hook Semantics, exempt from ADR-035):
    0 = Allow (clean validator, no PR for branch, gh missing, timeout,
        OSError, or empty changeset)
    2 = Block (validator reported CRITICAL mismatches, or config error)
"""

from __future__ import annotations

import shutil
import subprocess
import sys

from _bootstrap import ensure_plugin_paths

ensure_plugin_paths()

from push_guard_base import run_guard  # noqa: E402
from hook_utilities import get_project_directory  # noqa: E402

GUARD_NAME = "pr-description"
GLOBS = ["*"]
GH_TIMEOUT = 10
VALIDATOR_TIMEOUT = 60
VALIDATOR_PATH = "scripts/validation/pr_description.py"


def _discover_pr_number(project_dir: str) -> int | None:
    """Return the PR number for the current branch, or None on any failure.

    Uses ``gh pr view`` against the local HEAD. The fail-open semantics are
    intentional: a brand-new branch with no PR open yet, a missing gh
    binary, or a transient gh failure must NOT block the push. The guard
    only exists to catch mismatches once a PR is open and authored.
    """
    if shutil.which("gh") is None:
        print(
            f"[{GUARD_NAME}] gh CLI not on PATH; allowing push (fail-open)",
            file=sys.stderr,
        )
        return None
    try:
        proc = subprocess.run(
            ["gh", "pr", "view", "--json", "number", "-q", ".number"],
            capture_output=True,
            text=True,
            timeout=GH_TIMEOUT,
            shell=False,
            check=False,
            cwd=project_dir,
        )
    except subprocess.TimeoutExpired:
        print(
            f"[{GUARD_NAME}] gh pr view timed out after {GH_TIMEOUT}s; "
            f"allowing push (fail-open)",
            file=sys.stderr,
        )
        return None
    except (FileNotFoundError, OSError) as exc:
        print(
            f"[{GUARD_NAME}] gh pr view failed to invoke: {exc}; "
            f"allowing push (fail-open)",
            file=sys.stderr,
        )
        return None
    if proc.returncode != 0:
        # Distinguish the common failure modes so on-call can act on the
        # real cause: no-PR-yet, auth, network, or generic.
        stderr_text = (proc.stderr or "").strip()
        stderr_lower = stderr_text.lower()
        first_line = stderr_text.splitlines()[0] if stderr_text else "non-zero exit"
        if "no pull requests found" in stderr_lower or "no commits between" in stderr_lower:
            cause = "no PR found for current branch"
        elif "authent" in stderr_lower or "not logged" in stderr_lower or "token" in stderr_lower:
            cause = "gh auth failure"
        elif "network" in stderr_lower or "could not resolve" in stderr_lower or "timed out" in stderr_lower:
            cause = "gh network failure"
        else:
            cause = "gh pr view failed"
        print(
            f"[{GUARD_NAME}] {cause} ({first_line}); allowing push (fail-open)",
            file=sys.stderr,
        )
        return None
    raw = proc.stdout.strip()
    if not raw:
        print(
            f"[{GUARD_NAME}] gh pr view returned empty PR number; "
            f"allowing push (fail-open)",
            file=sys.stderr,
        )
        return None
    try:
        return int(raw)
    except ValueError:
        print(
            f"[{GUARD_NAME}] gh pr view returned non-numeric PR number "
            f"{raw!r}; allowing push (fail-open)",
            file=sys.stderr,
        )
        return None


def _parse_critical_lines(stdout: str) -> list[str]:
    """Extract CRITICAL violation blocks from validator stdout.

    Validator format (see scripts/validation/pr_description.py
    print_results):

        [CRITICAL] <issue_type>
          File: <path>
          <message>

    Each block becomes one violation entry that preserves the file path
    and message so the user can act without rerunning the validator.
    """
    violations: list[str] = []
    lines = stdout.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.startswith("[CRITICAL]"):
            block = [line.rstrip()]
            j = i + 1
            while j < len(lines) and (
                lines[j].startswith("  ") or lines[j].startswith("\t")
            ):
                stripped = lines[j].rstrip()
                if stripped:
                    block.append(stripped)
                j += 1
            violations.append(" ".join(block))
            i = j
            continue
        i += 1
    return violations


def _validate(_matching: list[str], _all_changed: list[str]) -> list[str]:
    project_dir = get_project_directory()

    pr_num = _discover_pr_number(project_dir)
    if pr_num is None:
        return []

    try:
        proc = subprocess.run(
            [
                sys.executable,
                VALIDATOR_PATH,
                "--pr-number",
                str(pr_num),
                "--ci",
            ],
            capture_output=True,
            text=True,
            timeout=VALIDATOR_TIMEOUT,
            shell=False,
            check=False,
            cwd=project_dir,
        )
    except subprocess.TimeoutExpired:
        print(
            f"[{GUARD_NAME}] {VALIDATOR_PATH} timed out after "
            f"{VALIDATOR_TIMEOUT}s; allowing push (fail-open)",
            file=sys.stderr,
        )
        return []
    except (FileNotFoundError, OSError) as exc:
        print(
            f"[{GUARD_NAME}] {VALIDATOR_PATH} failed to invoke: {exc}; "
            f"allowing push (fail-open)",
            file=sys.stderr,
        )
        return []

    if proc.returncode == 0:
        return []

    if proc.returncode == 2:
        stderr_first = (proc.stderr or "").strip().splitlines()
        reason = stderr_first[0] if stderr_first else "config error"
        return [f"{VALIDATOR_PATH}: config error - {reason}"]

    # rc == 1: CRITICAL mismatch
    violations = _parse_critical_lines(proc.stdout)
    if not violations:
        # Validator returned 1 but stdout did not match the [CRITICAL]
        # parse shape. Surface a generic violation rather than fail-open;
        # the user can rerun the validator locally for full output.
        violations = [
            f"{VALIDATOR_PATH} reported critical issues "
            f"(rc=1, see local run for detail)"
        ]
    violations.append(
        f"Update the PR description to mention only files actually in "
        f"the diff (run {VALIDATOR_PATH} --pr-number {pr_num} for details)."
    )
    return violations


def main() -> int:
    # include_deletions=True: pr_description.py compares the description
    # against the FULL PR diff (including deletions), so this guard must
    # fire on deletion-only pushes too. The validator never reads the
    # listed paths.
    return run_guard(_validate, GLOBS, GUARD_NAME, include_deletions=True)


if __name__ == "__main__":
    sys.exit(main())
