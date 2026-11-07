#!/usr/bin/env python3
"""Guard the pinned ``@github/copilot`` CLI version (Issue #2630).

REQ-047 (issue #6069) removed the Copilot CLI from the ``ai-review`` action.
The only remaining pin lives in ``.github/cli-smoke/copilot/package.json``, which
Renovate maintains with its lockfile and the smoke installs with ``npm ci``::

    "@github/copilot": "<version>"

The guard also accepts the earlier workflow env form ``COPILOT_CLI_VERSION: '<version>'``.

The guard also accepts the older shell form ``COPILOT_VERSION="<version>"`` so
the same denylist can scan any file that pins the CLI.

Version ``0.0.397`` carries a defect that npm itself flags::

    npm warn deprecated @github/copilot@0.0.397: A bug in this version caused
    invalid session id errors. We've fixed the bug in later versions

On that pin the "Process PR comments for PR" step failed and the job exited
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

# The legacy text pin: COPILOT_VERSION="x.y.z" (shell) or COPILOT_CLI_VERSION: 'x.y.z' (YAML
# env), single or double quoted.
# Anchored to a non-comment line start via ``^`` with ``re.MULTILINE``.
# Leading whitespace and an optional ``export`` keyword are accepted so the
# pattern works inside shell here-docs at any indentation level. This
# prevents the guard from treating an old version cited in a comment (e.g.
# ``# COPILOT_VERSION="0.0.397"  <- known-bad, do not use``) as the live pin.
_PIN_RE = re.compile(
    r"""^[ \t]*(?:export[ \t]+)?COPILOT_(?:CLI_)?VERSION(?:=|:[ \t]*)["']([^"']+)["']""",
    re.MULTILINE,
)

# The package.json pin: "@github/copilot": "x.y.z" under dependencies. This is a text
# match, not a JSON parse: a file without that key yields no match and fails the guard,
# and a "@github/copilot" key anywhere else in the file (for example devDependencies)
# also matches, so the exactly-one-pin check below still applies.
_MANIFEST_PIN_RE = re.compile(r"""\"@github/copilot\"[ \t]*:[ \t]*\"([^\"]+)\"""")

# Accept semver-ish versions: x.y.z with an optional -prerelease suffix
# (npm publishes tags such as 1.0.62-2). Match the shapes this action pins.
_VERSION_RE = re.compile(r"^\d+\.\d+\.\d+(?:-[0-9A-Za-z.]+)?$")

# The default target is the Copilot CLI manifest (the name predates the move out of the
# workflow); ``check_action`` accepts a manifest, a workflow, or an action file.
_DEFAULT_ACTION = (
    Path(__file__).resolve().parents[2] / ".github" / "cli-smoke" / "copilot" / "package.json"
)


class VersionPinError(ValueError):
    """Raised when the Copilot CLI pin is missing or ambiguous in the target file."""


def is_parseable(version: str) -> bool:
    """Return True when ``version`` matches the accepted semver shape."""
    return bool(_VERSION_RE.match(version))


def is_known_bad(version: str) -> bool:
    """Return True when ``version`` is on the known-bad list."""
    return version in KNOWN_BAD_VERSIONS


def extract_pinned_version(action_path: Path) -> str:
    """Extract the pinned Copilot CLI version from a manifest, workflow, or action file.

    Raises ``VersionPinError`` when no pin is present so a silently dropped pin
    fails the guard rather than passing vacuously.

    Also raises ``VersionPinError`` when multiple pins are found. In a shell file the
    last assignment wins, and in a manifest a duplicate key is ambiguous, so checking
    only the first match could pass a known-bad pin that is still installed.
    Requiring exactly one pin avoids this ambiguity.
    """
    text = action_path.read_text(encoding="utf-8")
    pin_re = _MANIFEST_PIN_RE if action_path.suffix == ".json" else _PIN_RE
    matches = pin_re.findall(text)
    if not matches:
        raise VersionPinError(f"no Copilot CLI pin found in {action_path}")
    if len(matches) > 1:
        raise VersionPinError(
            f"multiple Copilot CLI pins found in {action_path}: {matches}. "
            f"Remove duplicates to avoid ambiguity."
        )
    # re.Pattern.findall returns list[Any]; the single capture group is a str.
    # Cast keeps mypy's no-any-return happy once MYPYPATH lets this module be
    # followed from checks_tooling (Issue #2876).
    return str(matches[0])


def check_action(action_path: Path) -> int:
    """Validate the pin in ``action_path`` and return an exit code."""
    if not action_path.is_absolute():
        repo_root = Path(__file__).resolve().parents[2]
        try:
            resolved_path = (repo_root / action_path).resolve()
            resolved_path.relative_to(repo_root)
            action_path = resolved_path
        except (ValueError, RuntimeError) as exc:
            print(
                f"::error::Path traversal attempt detected: {action_path} ({type(exc).__name__})",
                file=sys.stderr,
            )
            return EXIT_LOGIC

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
            f"::error::Copilot CLI pin '{version}' is not a parseable version "
            f"(expected x.y.z[-prerelease])",
            file=sys.stderr,
        )
        return EXIT_LOGIC

    if is_known_bad(version):
        print(
            f"::error::Copilot CLI pin '{version}' is on the known-bad list "
            f"(Issue #2630: invalid session id defect). Bump to a fixed release.",
            file=sys.stderr,
        )
        return EXIT_LOGIC

    print(f"Copilot CLI pin OK: {version}")
    return EXIT_OK


def main(argv: list[str] | None = None) -> int:
    """CLI entry point."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--action",
        type=Path,
        default=_DEFAULT_ACTION,
        help="path to the file that pins the Copilot CLI version",
    )
    args = parser.parse_args(argv)
    return check_action(args.action)


if __name__ == "__main__":
    raise SystemExit(main())
