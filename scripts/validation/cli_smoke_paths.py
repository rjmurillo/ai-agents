#!/usr/bin/env python3
"""Single source of truth for the paths that can break plugin loading in a CLI.

REQ-047 (issue #6069). Two consumers read this module so they cannot drift:

- ``git_hook_policy.py`` uses ``HOOK_E2E_GLOBS`` and ``PLUGIN_E2E_GLOBS`` to
  decide whether the lefthook pre-push gates run the local CLI smoke.
- ``.github/workflows/plugin-cli-smoke.yml`` runs this file as a CLI. It diffs
  ``base...head`` and writes ``run=true`` or ``run=false`` to ``GITHUB_OUTPUT``
  using ``SMOKE_PATH_GLOBS``, the union of both tuples. A ``workflow_dispatch``
  event always writes ``run=true``; any other event is a usage error.

``lefthook.yml`` keeps a copy of each tuple as its ``glob:`` filter. A test in
``tests/validation/test_cli_smoke_paths.py`` fails when those copies differ, so
lefthook and CI see one list. Per ADR-006 the decision lives in Python. Matching
uses ``fnmatch`` as ``git_hook_policy._any_glob_match`` does, so ``**`` crosses
directory separators.

Exit codes (ADR-035):
    0 - decision written
    1 - the diff could not be computed (fail closed: no ``run`` output)
    2 - usage error
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from collections.abc import Iterable, Sequence
from fnmatch import fnmatch
from pathlib import Path

EXIT_OK = 0
EXIT_LOGIC = 1
EXIT_USAGE = 2

GIT_TIMEOUT_SECONDS = 60
_FULL_SHA_RE = re.compile(r"[0-9a-f]{40}")

HOOK_E2E_GLOBS: tuple[str, ...] = (
    "build/scripts/generate_hooks.py",
    "src/copilot-cli/hooks/**",
    ".claude/hooks/**",
    ".claude/settings.json",
    "scripts/validation/validate_hook_anchoring.py",
    "tests/e2e/test_cli_hook_e2e.py",
    "tests/e2e/copilot_hook_probe.py",
    "tests/e2e/smoke_skip_policy.py",
)

PLUGIN_E2E_GLOBS: tuple[str, ...] = (
    ".claude-plugin/marketplace.json",
    ".github/plugin/marketplace.json",
    "src/claude/**",
    "src/copilot-cli/**",
    ".claude/skills/**",
    "build/scripts/generate_skills.py",
    "templates/platforms/copilot-cli.yaml",
    "tests/e2e/test_plugin_load_smoke.py",
    "tests/e2e/copilot_hook_probe.py",
    "tests/e2e/smoke_skip_policy.py",
    ".github/workflows/plugin-cli-smoke.yml",
    "scripts/validation/cli_smoke_paths.py",
    "scripts/validation/assert_smoke_ran.py",
    "scripts/validation/smoke_quota_report.py",
    "scripts/validation/assert_trusted_smoke_context.py",
    "scripts/validation/smoke_result.py",
    "tests/integration/test_e2e_install.py",
    "pyproject.toml",
    "uv.lock",
)

# Union in first-seen order: a change to either smoke runs the whole matrix.
SMOKE_PATH_GLOBS: tuple[str, ...] = tuple(dict.fromkeys((*HOOK_E2E_GLOBS, *PLUGIN_E2E_GLOBS)))


class DiffError(RuntimeError):
    """Raised when the changed-file list cannot be computed."""


def changed_files(base: str, head: str, repo_root: Path) -> list[str]:
    """Return files changed between two full SHAs (three-dot diff).

    A full SHA never starts with ``-``, so no value reaches git as an option.
    ``--no-renames`` lists both sides of a rename, so moving a smoke path out of
    the filter still matches its old path.
    """
    for label, value in (("base", base), ("head", head)):
        if not _FULL_SHA_RE.fullmatch(value):
            raise DiffError(f"{label} must be a 40-character lowercase hex commit SHA")
    revision_range = f"{base}...{head}"
    try:
        result = subprocess.run(
            ["git", "-C", str(repo_root), "diff", "--name-only", "--no-renames", revision_range],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=GIT_TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise DiffError(f"git diff did not run: {type(exc).__name__}") from exc
    if result.returncode != 0:
        raise DiffError(f"git diff failed: {result.stderr.strip()}")
    return [line for line in result.stdout.splitlines() if line.strip()]


MAX_LISTED_PATHS = 20


def matched_paths(changed: Iterable[str], globs: Sequence[str] = SMOKE_PATH_GLOBS) -> list[str]:
    """Return the changed paths that match any glob, in diff order."""
    return [p for p in changed if any(fnmatch(p, pattern) for pattern in globs)]


def describe_matches(matched: Sequence[str]) -> str:
    """List up to ``MAX_LISTED_PATHS`` matched paths, then "and N more"."""
    lines = [f"  {path}" for path in matched[:MAX_LISTED_PATHS]]
    extra = len(matched) - MAX_LISTED_PATHS
    if extra > 0:
        lines.append(f"  and {extra} more")
    return "\n".join(lines)


def _emit(run: bool) -> None:
    line = f"run={'true' if run else 'false'}"
    print(line)
    output_path = os.environ.get("GITHUB_OUTPUT")
    if output_path:
        with open(output_path, "a", encoding="utf-8") as handle:
            handle.write(line + "\n")


PULL_REQUEST_EVENT = "pull_request"
DISPATCH_EVENT = "workflow_dispatch"


def _parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--event-name",
        required=True,
        choices=[PULL_REQUEST_EVENT, DISPATCH_EVENT],
        help="The github.event_name. workflow_dispatch always runs the smoke.",
    )
    parser.add_argument("--base", help="Base commit SHA (pull request base).")
    parser.add_argument("--head", help="Head commit SHA (pull request head).")
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path(__file__).resolve().parents[2],
        help="Repository root (default: this checkout).",
    )
    args = parser.parse_args(argv)
    if args.event_name == PULL_REQUEST_EVENT and not (args.base and args.head):
        parser.error("--base and --head are required for pull_request")
    return args


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    if args.event_name == DISPATCH_EVENT:
        _emit(True)
        return EXIT_OK
    try:
        changed = changed_files(args.base, args.head, args.repo_root)
    except DiffError as exc:
        print(f"::error::cli smoke path filter failed closed: {exc}", file=sys.stderr)
        return EXIT_LOGIC
    matched = matched_paths(changed)
    if matched:
        print(f"{len(matched)} changed path(s) match the smoke path filter:")
        print(describe_matches(matched))
    _emit(bool(matched))
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
