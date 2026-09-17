#!/usr/bin/env python3
"""Branch-wide em/en-dash prohibition check for the pre-PR runner.

Extracted from ``scripts/validation/pre_pr.py`` (issue #2223). Holds the
detection regex, the vendored-path skip list, and the helpers that resolve the
branch base, list changed markdown files, read the HEAD blob, and report
violations. ``validate_dash_prohibition`` is the public entry point.

Behavior-preserving move: each function is identical to its previous definition
in ``pre_pr.py``. ``pre_pr`` re-exports ``validate_dash_prohibition`` (and the
module-level helpers) so existing imports keep working.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from checks_common import _resolve_branch_base_ref, _run_subprocess  # noqa: E402

# Compiled detection regex. Uses Unicode escape sequences so this source
# file does not contain U+2014 or U+2013 itself (Issue #1923, REQ-006).
_DASH_RE = re.compile("[\u2013\u2014]")


# Paths skipped by the branch-wide dash scan and (via _markdown_lint_targets
# in checks_tooling.py, which shares this predicate) the markdown-lint target
# builder:
# - node_modules/, .venv/, .serena/cache/: vendored content (REQ-006-AC5)
# - tests/hooks/fixtures/: test fixtures intentionally contain U+2014/U+2013
#   to exercise the detection logic; flagging them would fail every PR that
#   touches the dash-guard test suite
# - worktrees/, .agent-scratch/, .scratch/: untracked agent-session scratch
#   trees, not authored source. The changed-path union in
#   checks_changed_paths.py includes untracked files, so a sibling session's
#   scratch tree lands in the markdown-lint target list; at scale (4000+
#   files) markdownlint-cli2 v0.23.1 exits 249 with no findings, and the
#   caller's canned MD040/MD033 hint then misreports the cause (issue #4892).
_VENDORED_PREFIXES = (
    "node_modules/",
    ".venv/",
    ".serena/cache/",
    "tests/hooks/fixtures/",
    "worktrees/",
    ".agent-scratch/",
    ".scratch/",
)


def _is_vendored(path: str) -> bool:
    """True when ``path`` starts with any vendored prefix."""
    return any(path.startswith(prefix) for prefix in _VENDORED_PREFIXES)


def _branch_markdown_files(repo_root: Path) -> list[str] | None:
    """Resolve branch base and return non-vendored markdown paths to scan.

    Returns None when the scan cannot run (no base ref or git diff failure);
    callers treat None as fail-open (pass without scanning).
    """
    base_ref = _resolve_branch_base_ref(repo_root)
    if base_ref is None:
        print("[WARNING] Em/en-dash branch scan skipped: no base ref resolved")
        return None

    exit_code, stdout, stderr = _run_subprocess(
        [
            "git",
            "-C",
            str(repo_root),
            "diff",
            "--name-only",
            "--diff-filter=ACMR",
            f"{base_ref}...HEAD",
        ],
        timeout=30,
    )
    if exit_code != 0:
        print(
            f"[WARNING] Em/en-dash branch scan skipped: git diff failed: {stderr}",
        )
        return None

    return [
        p for p in stdout.splitlines() if p.endswith(".md") and not _is_vendored(p)
    ]


def _find_dash_violations(
    repo_root: Path, paths: list[str],
) -> tuple[list[tuple[str, int]], list[str]]:
    """Read each committed path and return (path, line_num) hits.

    Reads file content from the HEAD commit via ``git show HEAD:<path>``
    rather than the working tree. The list of paths comes from
    ``git diff <base>...HEAD --name-only``, so the scan target must be
    the HEAD blob to match the diff scope. Reading the working tree
    instead would give wrong answers when the working tree differs from
    HEAD (uncommitted edits, partial staging, or a fresh checkout that
    has not yet pulled the branch).

    Returns ``(violations, skipped)``. ``skipped`` holds every candidate
    path whose ``git show`` call did not exit 0 (missing object in the
    local clone, a path that resolves to a directory, an I/O error);
    `_branch_markdown_files` already filters out deletions via
    ``--diff-filter=ACMR``, so a non-zero exit here is unexpected rather
    than routine. The caller narrows scope rather than failing the whole
    scan, because a `git diff`-listed path that cannot be read is not
    actionable for the dash check, but the narrowing itself MUST be
    visible (`.claude/rules/ci-scripts.md` MUST 12): a blocking gate that
    silently examines fewer files than it claims can pass a branch that
    still carries a violation in the file it dropped.
    """
    violations: list[tuple[str, int]] = []
    skipped: list[str] = []
    for relpath in paths:
        exit_code, stdout, _ = _run_subprocess(
            ["git", "-C", str(repo_root), "show", f"HEAD:{relpath}"],
            timeout=10,
        )
        if exit_code != 0:
            skipped.append(relpath)
            print(
                f"[WARNING] Em/en-dash scan: {relpath} could not be read at "
                f"HEAD (git show exited {exit_code}); file skipped, scope "
                "narrowed",
            )
            continue
        violations.extend(
            (relpath, line_num)
            for line_num, line in enumerate(stdout.splitlines(), start=1)
            if _DASH_RE.search(line)
        )
    return violations, skipped


def _print_dash_violations(violations: list[tuple[str, int]]) -> None:
    """Emit the structured failure block for branch-wide dash violations."""
    print("[FAIL] Em/en-dash prohibition violated")
    print("  Files containing U+2014 (em-dash) or U+2013 (en-dash):")
    for path, line_num in violations:
        print(f"    {path}:{line_num}")
    print("  Fix: replace U+2014 with comma, period, or colon;")
    print("       U+2013 with hyphen in numeric ranges;")
    print("       or restructure the sentence.")
    print(
        "  Rule: .claude/rules/universal.md MUST NOT entry 4 (Refs #1923).",
    )


def validate_dash_prohibition(repo_root: Path) -> bool:
    """Branch-wide em/en-dash check (Issue #1923, REQ-006-AC7).

    Catches U+2014 (em-dash) and U+2013 (en-dash) in any *.md file
    changed on this branch since divergence from the base ref. Complements
    the pre-commit and commit-msg hooks (which only block at commit time)
    by catching dashes that landed before the hooks were installed.

    Vendored paths (node_modules/, .venv/, .serena/cache/) are skipped.
    Test fixtures (tests/hooks/fixtures/) are skipped because they
    intentionally contain dashes to exercise the detection logic.
    .github/instructions/ is NOT skipped (REQ-006-AC4).

    Returns True (pass) when no violations are found OR when the scan
    cannot run (fail open). Returns False on any violation.
    """
    candidate_paths = _branch_markdown_files(repo_root)
    if candidate_paths is None:
        return True
    if not candidate_paths:
        print("[PASS] Em/en-dash prohibition (no markdown files on branch)")
        return True

    violations, skipped = _find_dash_violations(repo_root, candidate_paths)
    if violations:
        _print_dash_violations(violations)
        return False

    if skipped:
        examined = len(candidate_paths) - len(skipped)
        print(
            f"[PASS] Em/en-dash prohibition ({examined} of "
            f"{len(candidate_paths)} markdown file(s) checked; "
            f"{len(skipped)} unreadable at HEAD, skipped)",
        )
        return True

    print(
        f"[PASS] Em/en-dash prohibition ({len(candidate_paths)} markdown file(s) checked)",
    )
    return True
