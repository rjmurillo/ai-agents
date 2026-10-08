#!/usr/bin/env python3
"""Single source of truth for the paths that can break plugin loading in a CLI.

REQ-047 (issue #6069). Two consumers read this module so they cannot drift:

- ``git_hook_policy.py`` uses ``HOOK_E2E_GLOBS`` and ``PLUGIN_E2E_GLOBS`` to
  decide whether the lefthook pre-push gates run the local CLI smoke.
- ``.github/workflows/cli-smoke.yml`` runs this file as a CLI. It diffs
  ``base...head`` and writes ``run=true`` or ``run=false`` to ``GITHUB_OUTPUT``
  using ``SMOKE_PATH_GLOBS``, the union of both tuples.

``lefthook.yml`` keeps a copy of each tuple as its ``glob:`` filter. A test in
``tests/validation/test_cli_smoke_paths.py`` fails when those copies differ from
the tuples below, so lefthook and CI see one list. Per ADR-006 the decision
lives in Python, not in workflow YAML.

Matching uses ``fnmatch`` exactly as ``git_hook_policy._any_glob_match`` does,
so ``**`` crosses directory separators.

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
)

PLUGIN_E2E_GLOBS: tuple[str, ...] = (
    ".claude-plugin/marketplace.json",
    "src/claude/**",
    "src/copilot-cli/**",
    ".claude/skills/**",
    "build/scripts/generate_skills.py",
    "templates/platforms/copilot-cli.yaml",
    "tests/e2e/test_plugin_load_smoke.py",
    "tests/e2e/copilot_hook_probe.py",
    ".github/workflows/cli-smoke.yml",
    "scripts/validation/cli_smoke_paths.py",
)

# Union in first-seen order. The CI filter uses this, so a change that affects
# either smoke runs the whole matrix.
SMOKE_PATH_GLOBS: tuple[str, ...] = tuple(dict.fromkeys((*HOOK_E2E_GLOBS, *PLUGIN_E2E_GLOBS)))


class DiffError(RuntimeError):
    """Raised when the changed-file list cannot be computed."""


def matches_any(changed: Iterable[str], globs: Sequence[str]) -> bool:
    """Return True when any changed path matches any glob."""
    return any(fnmatch(path, pattern) for path in changed for pattern in globs)


def should_run(changed: Iterable[str]) -> bool:
    """Return True when any changed path can affect plugin loading."""
    return matches_any(changed, SMOKE_PATH_GLOBS)


def _require_sha(label: str, value: str) -> str:
    if not _FULL_SHA_RE.fullmatch(value):
        raise DiffError(f"{label} must be a 40-character lowercase hex commit SHA")
    return value


def changed_files(base: str, head: str, repo_root: Path) -> list[str]:
    """Return files changed between ``base`` and ``head`` (three-dot diff).

    Both revisions must be full SHAs, which also keeps a value that starts with
    ``-`` from reaching git as an option.
    """
    revision_range = f"{_require_sha('base', base)}...{_require_sha('head', head)}"
    try:
        result = subprocess.run(
            ["git", "-C", str(repo_root), "diff", "--name-only", revision_range],
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


def _emit(run: bool) -> None:
    line = f"run={'true' if run else 'false'}"
    print(line)
    output_path = os.environ.get("GITHUB_OUTPUT")
    if output_path:
        with open(output_path, "a", encoding="utf-8") as handle:
            handle.write(line + "\n")


def _parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--base", help="Base commit SHA (pull request base).")
    parser.add_argument("--head", help="Head commit SHA (pull request head).")
    parser.add_argument(
        "--always",
        action="store_true",
        help="Skip the diff and emit run=true (workflow_dispatch).",
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path(__file__).resolve().parents[2],
        help="Repository root (default: this checkout).",
    )
    args = parser.parse_args(argv)
    if not args.always and not (args.base and args.head):
        parser.error("--base and --head are required unless --always is set")
    return args


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    if args.always:
        _emit(True)
        return EXIT_OK
    try:
        changed = changed_files(args.base, args.head, args.repo_root)
    except DiffError as exc:
        print(f"::error::cli smoke path filter failed closed: {exc}", file=sys.stderr)
        return EXIT_LOGIC
    _emit(should_run(changed))
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
