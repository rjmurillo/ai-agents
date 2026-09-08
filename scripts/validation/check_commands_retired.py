#!/usr/bin/env python3
"""Fail when a user-invocable command comes back under a plugin root.

ADR-064 makes skills the single user-invocable surface. Issue #5632 converted
every command in ``.claude/commands/`` into a skill and deleted the
command-to-skill bridge (``build/scripts/generate_commands.py``) that mirrored
them into ``src/copilot-cli/skills/``.

That deletion is what this guard protects. A ``.md`` file placed under a plugin
root's ``commands/`` directory now loads in Claude Code exactly as it did
before, because the harness still reads that directory, while nothing mirrors it
to Copilot, nothing evaluates it, and the skill validators never see it. The
result is a surface that works for one harness and silently does not exist for
the other, which is the asymmetry ADR-064 exists to remove. Nothing else in the
repository would report it: the skill gates enumerate ``skills/`` trees, and a
directory nobody scans produces no finding.

Exit codes follow ADR-035: ``0`` no commands found, ``1`` at least one command
found, ``2`` a configuration error (a plugin root that is not a directory).

The scan is over tracked files at ``HEAD`` plus the index, not a directory walk,
per ``.claude/rules/ci-scripts.md`` MUST 9: an untracked scratch file under a
``commands/`` directory is not a shipped command and must not fail the build,
while a staged one must, because the next commit ships it.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

# Plugin roots per .claude/rules/plugin-self-containment.md. Each installs
# standalone, so a command under any of them is a shipped surface.
PLUGIN_ROOTS: tuple[str, ...] = (".claude", "src/claude", "src/copilot-cli")

# Files a commands/ directory may legitimately still hold. Both are agent
# instruction entrypoints read by the harness, never user-invocable commands.
ALLOWED_BASENAMES: frozenset[str] = frozenset({"AGENTS.md", "CLAUDE.md"})

EXIT_OK = 0
EXIT_VIOLATION = 1
EXIT_CONFIG = 2


def _tracked_paths(repo_root: Path) -> list[str]:
    """Return paths tracked at HEAD or staged in the index, POSIX-normalized."""
    result = subprocess.run(
        ["git", "ls-files", "-z", "--cached", "--"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(f"git ls-files failed: {result.stderr.strip()}")
    return [entry for entry in result.stdout.split("\0") if entry]


def find_commands(repo_root: Path) -> list[str]:
    """Return every tracked command Markdown file under a plugin root."""
    prefixes = tuple(f"{root}/commands/" for root in PLUGIN_ROOTS)
    found = [
        path
        for path in _tracked_paths(repo_root)
        if path.startswith(prefixes)
        and path.endswith(".md")
        and Path(path).name not in ALLOWED_BASENAMES
    ]
    return sorted(found)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path.cwd(),
        help="Repository root to scan (default: current directory).",
    )
    args = parser.parse_args(argv)

    repo_root: Path = args.repo_root
    if not repo_root.is_dir():
        print(f"Not a directory: {repo_root}", file=sys.stderr)
        return EXIT_CONFIG

    try:
        violations = find_commands(repo_root)
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return EXIT_CONFIG

    scanned = len(PLUGIN_ROOTS)
    if violations:
        print(
            f"{len(violations)} command file(s) found across {scanned} plugin root(s). "
            "ADR-064 makes skills the single user-invocable surface:",
            file=sys.stderr,
        )
        for path in violations:
            print(f"  {path}", file=sys.stderr)
        print(
            "Move each one to <root>/skills/<name>/SKILL.md. The command-to-skill "
            "bridge is gone, so a command here ships to Claude Code and to nothing "
            "else.",
            file=sys.stderr,
        )
        return EXIT_VIOLATION

    print(f"No commands: 0 command file(s) across {scanned} plugin root(s) (ADR-064).")
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
