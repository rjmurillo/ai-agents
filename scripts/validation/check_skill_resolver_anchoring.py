#!/usr/bin/env python3
"""Fail when a SKILL.md script-path resolver can select a stale out-of-repo copy.

Skills that shell out to helper scripts embed a resolver that walks candidate
roots until one contains the scripts directory. Two properties make such a
resolver unsafe, and both are mechanically checkable:

1. A repo-relative candidate root (a bare ``.claude``) only resolves when the
   process cwd happens to be the repository root. Invoked from any
   subdirectory the probe misses, the loop falls through, and a copy under
   ``~/.copilot/installed-plugins`` or ``~/.claude/plugins/cache`` wins
   instead. That copy can be arbitrarily old. When the resolved script is a
   safety gate, the gate silently runs a stale implementation.

   The fix is to anchor the repo-relative rung on ``git rev-parse
   --show-toplevel`` so it resolves from anywhere inside the worktree.

2. An out-of-repo candidate root that is ordered ahead of the in-repo rung
   wins even when the repository copy is present and current.

This guard exists because the failure is invisible at runtime: the resolver
fails open, prints nothing, and returns a path that looks plausible. Nothing
downstream can tell a current copy from a month-old one.

Companion to check_skill_md_exec_portability.py, which verifies that skills do
not hard-code ``.claude/skills`` exec paths. This one verifies that the
resolver replacing those hard-coded paths is itself correctly anchored.

Exit codes:
    0 - no unanchored resolvers
    1 - at least one violation
    2 - usage or I/O error
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path

SCAN_ROOTS = ("src/copilot-cli/skills", ".claude/skills")

# A resolver is a shell function whose body walks candidate roots. Match any
# shell function header and decide by body content rather than by name: an
# earlier version keyed on names ending in "dir" and silently missed
# resolve_pr_review_config(), which carries the identical defect.
RESOLVER_HEADER = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*\(\)\s*\{")

# A repo-relative candidate root: a bare quoted ".claude" or "./.claude" that
# is not preceded by a variable expansion or an absolute anchor.
BARE_RELATIVE_ROOT = re.compile(r"""^\s*["']\.{1,2}/?\.?claude["']?\s*\\?\s*$""")
BARE_RELATIVE_INLINE = re.compile(r"""(?<![\w/$}])["']\.claude["']""")

# An in-repo candidate root already anchored on the worktree root.
IN_REPO_ROOT = re.compile(r"\$\{?(?:repo_root|REPO_ROOT|toplevel)\}?/\.claude")

# Anchoring that makes a repo-relative rung safe from any cwd.
ANCHORED = re.compile(r"git\s+rev-parse\s+--show-toplevel")

# Candidate roots that live outside the repository.
OUT_OF_REPO = re.compile(r"\$\{?HOME\b|~/\.(?:copilot|claude)\b")


@dataclass(frozen=True)
class Violation:
    path: Path
    line: int
    function: str
    kind: str
    detail: str

    def render(self) -> str:
        return (
            f"{self.path}:{self.line}: {self.function}(): {self.kind}\n"
            f"    {self.detail}"
        )


def _function_blocks(lines: list[str]) -> list[tuple[str, int, int]]:
    """Return (name, start_index, end_index) for each shell function body.

    Brace depth is tracked so a nested block does not truncate the body early.
    An unterminated function runs to end of file rather than being dropped,
    because silently skipping input is the failure mode this guard exists to
    prevent.
    """
    blocks: list[tuple[str, int, int]] = []
    index = 0
    total = len(lines)
    while index < total:
        match = RESOLVER_HEADER.match(lines[index])
        if not match:
            index += 1
            continue
        name = match.group(1)
        depth = lines[index].count("{") - lines[index].count("}")
        cursor = index + 1
        while cursor < total and depth > 0:
            depth += lines[cursor].count("{") - lines[cursor].count("}")
            cursor += 1
        blocks.append((name, index, min(cursor, total)))
        index = cursor
    return blocks


def check_file(path: Path) -> list[Violation]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:  # pragma: no cover - surfaced to caller
        raise SystemExit(f"error: cannot read {path}: {exc}") from exc

    violations: list[Violation] = []

    for name, start, end in _function_blocks(lines):
        body = lines[start:end]
        anchored = any(ANCHORED.search(line) for line in body)

        first_out_of_repo: int | None = None
        for offset, line in enumerate(body):
            if OUT_OF_REPO.search(line):
                first_out_of_repo = offset
                break

        # Locate the in-repo rung in either form: a bare relative ".claude" or
        # an anchored "$repo_root/.claude". Ordering is a property of the
        # resolver regardless of which form the in-repo rung takes, so it must
        # be evaluated even when anchoring is already correct.
        first_in_repo: int | None = None
        for offset, line in enumerate(body):
            if BARE_RELATIVE_ROOT.match(line.strip()) or IN_REPO_ROOT.search(line):
                first_in_repo = offset
                break

        if (
            first_out_of_repo is not None
            and first_in_repo is not None
            and first_out_of_repo < first_in_repo
        ):
            violations.append(
                Violation(
                    path=path,
                    line=start + first_in_repo + 1,
                    function=name,
                    kind="out-of-repo candidate ordered before in-repo copy",
                    detail=(
                        f"an out-of-repo root at body line "
                        f"{start + first_out_of_repo + 1} is probed first, so an "
                        "installed copy wins even when the repository copy is "
                        "present and current."
                    ),
                )
            )

        for offset, line in enumerate(body):
            stripped = line.strip()
            is_bare = bool(
                BARE_RELATIVE_ROOT.match(stripped) or BARE_RELATIVE_INLINE.search(line)
            )
            if not is_bare:
                continue

            if not anchored:
                violations.append(
                    Violation(
                        path=path,
                        line=start + offset + 1,
                        function=name,
                        kind="unanchored repo-relative candidate root",
                        detail=(
                            'bare ".claude" resolves only when cwd is the repo '
                            "root; from a subdirectory this rung is skipped and "
                            "a stale out-of-repo copy wins. Anchor it on "
                            '"$(git rev-parse --show-toplevel)/.claude".'
                        ),
                    )
                )

    return violations


def iter_skill_files(repo_root: Path) -> list[Path]:
    found: list[Path] = []
    for scan_root in SCAN_ROOTS:
        base = repo_root / scan_root
        if not base.is_dir():
            continue
        found.extend(sorted(base.rglob("SKILL.md")))
    return found


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=".", help="repository root")
    parser.add_argument("paths", nargs="*", help="explicit SKILL.md paths")
    args = parser.parse_args(argv)

    repo_root = Path(args.repo_root).resolve()

    if args.paths:
        targets = [Path(p) for p in args.paths]
    else:
        targets = iter_skill_files(repo_root)

    if not targets:
        # An empty scan is indistinguishable from a clean scan, so refuse to
        # report success. This guard was written after a green run that had
        # simply never opened the relevant files.
        print(
            "error: no SKILL.md files found; refusing to report success on an "
            f"empty scan (repo root: {repo_root})",
            file=sys.stderr,
        )
        return 2

    violations: list[Violation] = []
    for target in targets:
        violations.extend(check_file(target))

    if violations:
        print("Skill resolver anchoring violations:\n")
        for violation in violations:
            print(violation.render())
            print()
        print(f"{len(violations)} violation(s) across {len(targets)} SKILL.md file(s).")
        return 1

    print(f"Resolver anchoring OK. {len(targets)} SKILL.md file(s) scanned.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
