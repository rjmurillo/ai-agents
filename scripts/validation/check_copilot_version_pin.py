#!/usr/bin/env python3
"""Guard the pinned ``@github/copilot`` CLI version (Issue #2630).

The PR Maintenance workflow drives its AI steps through the composite action
``.github/actions/ai-review/action.yml``, which pins the Copilot CLI with a
shell line of the form::

    COPILOT_VERSION="<version>"

Version ``0.0.397`` carries a defect that npm itself flags::

    npm warn deprecated @github/copilot@0.0.397: A bug in this version caused
    invalid session id errors. We've fixed the bug in later versions

On that pin the "Process PR comments for PR" step fails and the job exits
non-zero (observed 2026-06-17 while processing PR #2624).

This module extracts the pinned version from the action and fails when it is
missing, unparseable, or on the known-bad list. The seed known-bad entry is
``0.0.397``. Wire it into the pre-push hook and CI so a regression to a
defective pin is caught at the author's terminal rather than at the next
scheduled run.

ADR-006 keeps the logic here (a testable Python module) rather than inside the
workflow YAML. ADR-042 mandates Python for new scripts.

Exit codes (ADR-035):
    0 - pin is parseable and not known-bad
    1 - pin missing, unparseable, or known-bad (logic failure)
    2 - the target action file does not exist (config failure)
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

EXIT_OK = 0
EXIT_LOGIC = 1
EXIT_CONFIG = 2

# Versions known to break the AI steps. Append, never delete: a version that
# was once defective stays defective. Seed entry is the Issue #2630 defect.
KNOWN_BAD_VERSIONS: frozenset[str] = frozenset({"0.0.397"})

# The shell pin: COPILOT_VERSION="x.y.z" (single or double quoted).
_PIN_RE = re.compile(r"""COPILOT_VERSION=["']([^"']+)["']""")

# Accept semver-ish versions: x.y.z with an optional -prerelease suffix
# (npm publishes tags such as 1.0.62-2). Match the shapes this action pins.
_VERSION_RE = re.compile(r"^\d+\.\d+\.\d+(?:-[0-9A-Za-z.]+)?$")

_DEFAULT_ACTION = (
    Path(__file__).resolve().parents[2]
    / ".github"
    / "actions"
    / "ai-review"
    / "action.yml"
)


class VersionPinError(ValueError):
    """Raised when no ``COPILOT_VERSION`` pin is found in the action file."""


def is_parseable(version: str) -> bool:
    """Return True when ``version`` matches the accepted semver shape."""
    return bool(_VERSION_RE.match(version))


def is_known_bad(version: str) -> bool:
    """Return True when ``version`` is on the known-bad list."""
    return version in KNOWN_BAD_VERSIONS


def extract_pinned_version(action_path: Path) -> str:
    """Extract the pinned ``COPILOT_VERSION`` from the action file.

    Raises ``VersionPinError`` when no pin is present so a silently dropped pin
    fails the guard rather than passing vacuously.
    """
    text = action_path.read_text(encoding="utf-8")
    match = _PIN_RE.search(text)
    if not match:
        raise VersionPinError(
            f"no COPILOT_VERSION pin found in {action_path}"
        )
    return match.group(1)


def check_action(action_path: Path) -> int:
    """Validate the pin in ``action_path`` and return an exit code."""
    if not action_path.exists():
        print(f"::error::action file not found: {action_path}", file=sys.stderr)
        return EXIT_CONFIG

    try:
        version = extract_pinned_version(action_path)
    except VersionPinError as exc:
        print(f"::error::{exc}", file=sys.stderr)
        return EXIT_LOGIC

    if not is_parseable(version):
        print(
            f"::error::COPILOT_VERSION '{version}' is not a parseable version "
            f"(expected x.y.z[-prerelease])",
            file=sys.stderr,
        )
        return EXIT_LOGIC

    if is_known_bad(version):
        print(
            f"::error::COPILOT_VERSION '{version}' is on the known-bad list "
            f"(Issue #2630: invalid session id defect). Bump to a fixed release.",
            file=sys.stderr,
        )
        return EXIT_LOGIC

    print(f"COPILOT_VERSION pin OK: {version}")
    return EXIT_OK


def main(argv: list[str] | None = None) -> int:
    """CLI entry point."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--action",
        type=Path,
        default=_DEFAULT_ACTION,
        help="path to the ai-review composite action.yml",
    )
    args = parser.parse_args(argv)
    return check_action(args.action)


if __name__ == "__main__":
    raise SystemExit(main())
