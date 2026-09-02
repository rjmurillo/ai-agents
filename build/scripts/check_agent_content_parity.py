#!/usr/bin/env python3
"""Content-parity gate: .claude/agents/ must match src/claude/.

validate_install_parity.py catches drift only at PR time (co-change in a
diff). It does not detect content divergence that already exists on disk.
This script compares the two hand-maintained copies byte-for-byte and fails
if any shared filename disagrees.

The two trees are hand-maintained siblings; neither is the generator source.
GENERATOR-FILES.md, line 35: 'src/claude/ is a hand-maintained copy, not a
generator output'. REQ-003-010 forbids generators from writing under
.claude/. Editing a shared agent means updating both copies manually.

Files present in one tree but absent from the other are reported as missing.
Files listed in ALLOWED_ONLY_IN_CLAUDE or ALLOWED_ONLY_IN_SRC are exempt
(they serve tree-specific purposes and have no sibling).

CLI::

    python3 build/scripts/check_agent_content_parity.py
    python3 build/scripts/check_agent_content_parity.py --format json

EXIT CODES
----------
0 - trees are byte-identical for all shared files
1 - one or more files differ or are missing
2 - configuration error (tree not found)
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Files that legitimately exist only in .claude/agents/ and have no sibling
# in src/claude/. Empty since issue #5493: the sole entry was CLAUDE.md, a
# claude-mem stub that the Claude Code plugin loader registered as a
# dispatchable subagent. It was deleted rather than exempted. Leaving the
# exemption in place would have let the stub return silently, so an empty set
# is the point, not an oversight.
ALLOWED_ONLY_IN_CLAUDE: frozenset[str] = frozenset()

# Files that legitimately exist only in src/claude/ and have no sibling
# in .claude/agents/. These are plugin-specific resources.
#
# AGENTS.md is here for the same reason CLAUDE.md is not above. The two copies
# were byte-identical, and the .claude/agents/ one registered as the agent
# named `project-toolkit:AGENTS` (issue #5493). src/claude/ has no agents/
# subdirectory, so the surviving copy is never scanned by the loader.
ALLOWED_ONLY_IN_SRC: frozenset[str] = frozenset(
    {
        "AGENTS.md",
        "claude-instructions.template.md",
    }
)


def _find_repo_root(start: Path) -> Path:
    here = start.resolve()
    for candidate in [here, *here.parents]:
        if (candidate / "pyproject.toml").exists():
            return candidate
    msg = f"Could not find repo root from {start}"
    raise FileNotFoundError(msg)


def _compare_trees(
    claude_dir: Path,
    src_dir: Path,
) -> tuple[list[str], list[str], list[str]]:
    """Return (diffs, missing_from_src, missing_from_claude).

    diffs: filenames present in both trees but with different content.
    missing_from_src: in .claude/agents/ but not src/claude/ (excl. exemptions).
    missing_from_claude: in src/claude/ but not .claude/agents/ (excl. exemptions).
    """
    claude_files = {p.name for p in claude_dir.glob("*.md")}
    src_files = {p.name for p in src_dir.glob("*.md")}

    shared = claude_files & src_files
    only_claude = claude_files - src_files - ALLOWED_ONLY_IN_CLAUDE
    only_src = src_files - claude_files - ALLOWED_ONLY_IN_SRC

    diffs: list[str] = []
    for name in sorted(shared):
        if (claude_dir / name).read_bytes() != (src_dir / name).read_bytes():
            diffs.append(name)

    return diffs, sorted(only_claude), sorted(only_src)


def _print_text_report(
    diffs: list[str],
    missing_from_src: list[str],
    missing_from_claude: list[str],
    claude_count: int,
    src_count: int,
    total_issues: int,
) -> None:
    print(
        f"Examined {claude_count} files in .claude/agents/, "
        f"{src_count} files in src/claude/."
    )
    if diffs:
        print(f"\nContent mismatch ({len(diffs)} files):")
        for name in diffs:
            print(f"  DIFF: {name}")
    if missing_from_src:
        print(f"\nMissing from src/claude/ ({len(missing_from_src)} files):")
        for name in missing_from_src:
            print(f"  MISSING: {name}")
    if missing_from_claude:
        print(f"\nMissing from .claude/agents/ ({len(missing_from_claude)} files):")
        for name in missing_from_claude:
            print(f"  MISSING: {name}")
    if total_issues == 0:
        print("OK: trees are byte-identical for all shared files.")
    else:
        print(f"\nFAIL: {total_issues} parity issue(s) detected.")


def _resolve_dirs(repo_root: Path) -> tuple[Path, Path, int]:
    """Return (claude_dir, src_dir, error_code). error_code 0 = OK, 2 = fail."""
    claude_dir = repo_root / ".claude" / "agents"
    src_dir = repo_root / "src" / "claude"
    for d in (claude_dir, src_dir):
        if not d.is_dir():
            print(f"ERROR: directory not found: {d}", file=sys.stderr)
            return claude_dir, src_dir, 2
    return claude_dir, src_dir, 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--format", choices=["text", "json"], default="text")
    parser.add_argument("--repo-root", type=Path, default=None)
    args = parser.parse_args(argv)

    try:
        repo_root = args.repo_root or _find_repo_root(Path.cwd())
    except FileNotFoundError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    claude_dir, src_dir, err = _resolve_dirs(repo_root)
    if err:
        return err

    diffs, missing_from_src, missing_from_claude = _compare_trees(claude_dir, src_dir)

    total_issues = len(diffs) + len(missing_from_src) + len(missing_from_claude)
    claude_count = len(list(claude_dir.glob("*.md")))
    src_count = len(list(src_dir.glob("*.md")))

    if args.format == "json":
        report = {
            "diffs": diffs,
            "missing_from_src": missing_from_src,
            "missing_from_claude": missing_from_claude,
            "total_issues": total_issues,
            "files_examined": {"claude_agents": claude_count, "src_claude": src_count},
        }
        print(json.dumps(report, indent=2))
    else:
        _print_text_report(
            diffs, missing_from_src, missing_from_claude, claude_count, src_count, total_issues
        )

    return 1 if total_issues > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
