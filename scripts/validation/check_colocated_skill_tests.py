#!/usr/bin/env python3
"""Block newly added test files inside customer-shipped skill directories.

Skill tests belong under ``tests/skills/<name>/``, not colocated inside
``.claude/skills/<name>/tests/`` or ``src/copilot-cli/skills/<name>/tests/``.
Colocated tests are copied into customer plugin installs and executed in
consumer CI environments where they should never run.

Exit codes:
    0 - No violations (or only legacy files)
    1 - Newly added colocated test file detected

Issue #4838.
"""

from __future__ import annotations

import argparse
import subprocess
from pathlib import Path, PurePosixPath

# Roots that ship to customers via plugin install.
SHIPPED_SKILL_ROOTS: tuple[str, ...] = (
    ".claude/skills",
    "src/copilot-cli/skills",
    "src/claude/skills",
)


def is_colocated_skill_test(path: str) -> bool:
    """Return True when *path* is a test file inside a shipped skill tree.

    A file qualifies when it sits under ``<root>/<skill>/tests/`` and looks
    like a Python test (``test_*.py`` or ``*_test.py``).
    """
    parts = PurePosixPath(path).parts
    for root in SHIPPED_SKILL_ROOTS:
        root_parts = PurePosixPath(root).parts
        if parts[: len(root_parts)] != root_parts:
            continue
        # Must have at least: root / skill / tests / file
        remaining = parts[len(root_parts):]
        if len(remaining) < 3:
            continue
        # Find "tests" directory anywhere after the skill name
        for _i, segment in enumerate(remaining[1:], start=1):
            if segment == "tests":
                # File is under a tests/ directory inside the skill
                filename = parts[-1]
                if filename.endswith(".py") and (
                    filename.startswith("test_") or filename.endswith("_test.py")
                ):
                    return True
    return False


def existing_on_ref(repo_root: Path, ref: str = "HEAD") -> set[str]:
    """Return paths that already exist on *ref* (legacy allowance).

    In pre-commit mode, HEAD is the right baseline (uncommitted files are new).
    In branch mode, pass the base ref (e.g. origin/main) so that files added
    on the branch are NOT exempted.
    """
    result = subprocess.run(
        ["git", "ls-tree", "-r", "--name-only", ref],
        cwd=repo_root,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if result.returncode != 0:
        return set()
    return set(result.stdout.splitlines())


def check_paths(
    paths: list[str],
    *,
    repo_root: Path,
    allow_existing: bool = True,
    legacy_ref: str = "HEAD",
) -> list[str]:
    """Return paths that violate the colocated-test rule.

    When *allow_existing* is True, files already tracked on *legacy_ref* are
    excluded (legacy tolerance). Use the base ref in branch mode so that
    files added on the branch are still flagged.
    """
    legacy = existing_on_ref(repo_root, legacy_ref) if allow_existing else set()
    violations: list[str] = []
    for path in paths:
        if not path:
            continue
        if is_colocated_skill_test(path):
            if path not in legacy:
                violations.append(path)
    return violations


def staged_additions(repo_root: Path) -> list[str]:
    """Return paths staged as additions (new files)."""
    result = subprocess.run(
        ["git", "diff", "--cached", "--name-only", "--diff-filter=A", "-z"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if result.returncode != 0:
        return []
    return [p for p in result.stdout.split("\0") if p]


def branch_additions(repo_root: Path, base: str = "origin/main") -> list[str]:
    """Return paths added on the branch relative to *base*."""
    result = subprocess.run(
        ["git", "diff", "--name-only", "--diff-filter=A", "-z", f"{base}...HEAD"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if result.returncode != 0:
        return []
    return [p for p in result.stdout.split("\0") if p]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Block colocated skill tests (issue #4838).",
    )
    parser.add_argument(
        "--staged-only",
        action="store_true",
        help="Check only staged additions (pre-commit mode).",
    )
    parser.add_argument(
        "--base",
        default="origin/main",
        help="Base ref for branch-diff mode (default: origin/main).",
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path.cwd(),
        help="Repository root.",
    )
    parser.add_argument(
        "paths",
        nargs="*",
        help="Explicit paths to check (overrides --staged-only/branch mode).",
    )
    args = parser.parse_args(argv)

    if args.paths:
        paths = args.paths
        legacy_ref = "HEAD"
    elif args.staged_only:
        paths = staged_additions(args.repo_root)
        legacy_ref = "HEAD"
    else:
        paths = branch_additions(args.repo_root, args.base)
        legacy_ref = args.base

    violations = check_paths(paths, repo_root=args.repo_root, legacy_ref=legacy_ref)

    if violations:
        print(
            "ERROR: New test files in customer-shipped skill directories.\n"
            "Move them to tests/skills/<skill_name>/ instead.\n"
        )
        for v in violations:
            print(f"  {v}")
        print(
            "\nSee issue #4838. Existing legacy tests are tolerated until migrated."
        )
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
