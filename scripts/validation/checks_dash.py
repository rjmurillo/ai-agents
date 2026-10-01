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

import os
import re
import sys
from pathlib import Path
from typing import NamedTuple

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from checks_common import _resolve_branch_base_ref, _run_subprocess  # noqa: E402

# The typed contract, package path (evidence.py states why).
_PROJECT_ROOT = _SCRIPT_DIR.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from scripts.validation.evidence import (  # noqa: E402
    REASON_BASE_REF_UNRESOLVED,
    REASON_DIFF_FAILED,
    REASON_ENTRIES_UNREADABLE,
    REASON_VIOLATIONS_FOUND,
    CheckOutcome,
)

_VALIDATOR = "validate_dash_prohibition"
_SCOPE = "markdown files changed on the branch"
_HEAD = "HEAD"

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


def _running_in_ci() -> bool:
    """True under CI (``CI`` or ``GITHUB_ACTIONS`` set to ``true`` or ``1``).

    No shared CI helper exists in ``scripts/validation/`` (searched
    ``def is_ci``, ``def _is_ci``, ``def in_ci``, ``def running_in_ci``,
    ``def is_github_actions``). This mirrors the inline test that
    ``checks_common._refresh_remote_base`` applies at
    ``checks_common.py:410-412``: ``os.environ.get("CI", "").lower() in
    ("true", "1")`` or the same test on ``GITHUB_ACTIONS``.
    """
    return any(
        os.environ.get(name, "").strip().lower() in ("true", "1")
        for name in ("CI", "GITHUB_ACTIONS")
    )


def _report_scan_unavailable(reason: str) -> None:
    """Say the scan could not run: BLOCKED under CI, a warning anywhere else."""
    if _running_in_ci():
        print(f"[BLOCKED] Em/en-dash branch scan: {reason}; no file was examined")
    else:
        print(f"[WARNING] Em/en-dash branch scan skipped: {reason}")


def _is_vendored(path: str) -> bool:
    """True when ``path`` starts with any vendored prefix."""
    return any(path.startswith(prefix) for prefix in _VENDORED_PREFIXES)


class _ScanUnavailable(NamedTuple):
    """Why the branch scan could not run: an evidence reason code and a sentence."""

    reason: str
    detail: str


def _branch_markdown_files(repo_root: Path) -> list[str] | _ScanUnavailable:
    """Resolve branch base and return non-vendored markdown paths to scan.

    Returns a :class:`_ScanUnavailable` when the scan cannot run (no base ref or
    git diff failure). The reason is reported here, as BLOCKED under CI and a
    warning locally; the caller turns it into the matching typed result.
    """
    base_ref = _resolve_branch_base_ref(repo_root)
    if base_ref is None:
        _report_scan_unavailable("no base ref resolved")
        return _ScanUnavailable(REASON_BASE_REF_UNRESOLVED, "no base ref resolved")

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
        _report_scan_unavailable(f"git diff failed: {stderr}")
        return _ScanUnavailable(REASON_DIFF_FAILED, f"git diff failed: {stderr}")

    return [p for p in stdout.splitlines() if p.endswith(".md") and not _is_vendored(p)]


def _unreadable_outcome(relpath: str, exit_code: int) -> CheckOutcome:
    """Type one blob the scan dropped: ``BLOCKED`` with ``entries.unreadable``.

    The caller narrows scope rather than failing the scan, so each dropped path
    prints this line; the aggregate result built in
    :func:`validate_dash_prohibition` carries the same reason and the counts.
    """
    return CheckOutcome.blocked(
        _VALIDATOR,
        reason=REASON_ENTRIES_UNREADABLE,
        scope=_SCOPE,
        detail=(
            f"{relpath} could not be read at HEAD (git show exited {exit_code}); "
            "file skipped, scope narrowed"
        ),
    )


def _find_dash_violations(
    repo_root: Path,
    paths: list[str],
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
            print(_unreadable_outcome(relpath, exit_code).report_line())
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


def _unavailable_outcome(unavailable: _ScanUnavailable) -> CheckOutcome:
    """Type a scan that could not run: ``FAIL`` under CI, ``SKIP`` anywhere else.

    Under CI a checkout that examined nothing must not report green (issue
    #5636, decision D10), so the result blocks. It is ``FAIL`` rather than
    ``BLOCKED`` because ``BLOCKED`` would move the pre-PR exit code from 1 to 3
    on a path that already blocks; ``pre_pr.run_validation`` keeps ``FAIL`` for
    the same reason on a raising validator. The reason code still says the scan
    never ran. Locally the scan is skipped on purpose so a shallow or detached
    checkout does not stop a push, and ``SKIP`` is licensed for every validator.
    """
    if _running_in_ci():
        return CheckOutcome.failed(
            _VALIDATOR, reason=unavailable.reason, scope=_SCOPE, detail=unavailable.detail
        )
    return CheckOutcome.skipped(
        _VALIDATOR,
        reason=unavailable.reason,
        scope=_SCOPE,
        detail=f"{unavailable.detail}; skipped locally, CI blocks this",
    )


def validate_dash_prohibition(repo_root: Path) -> CheckOutcome:
    """Branch-wide em/en-dash check (Issue #1923, REQ-006-AC7).

    Catches U+2014 (em-dash) and U+2013 (en-dash) in any *.md file
    changed on this branch since divergence from the base ref. Complements
    the pre-commit and commit-msg hooks (which only block at commit time)
    by catching dashes that landed before the hooks were installed.

    Vendored paths (node_modules/, .venv/, .serena/cache/) are skipped.
    Test fixtures (tests/hooks/fixtures/) are skipped because they
    intentionally contain dashes to exercise the detection logic.
    .github/instructions/ is NOT skipped (REQ-006-AC4).

    Returns typed evidence (issue #5636). ``PASS`` names how many files were
    examined. A violation is ``FAIL`` with reason ``violations.found``. When
    the scan cannot run (base ref unresolved, or ``git diff`` fails) the result
    is ``FAIL`` under CI and ``SKIP`` locally; see :func:`_unavailable_outcome`.
    A scan that skipped a blob git could not read is ``BLOCKED`` with reason
    ``entries.unreadable``, licensed by name so it does not block (decision D10);
    a ``PASS`` there would certify files nobody read.
    """
    candidate_paths = _branch_markdown_files(repo_root)
    if isinstance(candidate_paths, _ScanUnavailable):
        return _unavailable_outcome(candidate_paths)
    if not candidate_paths:
        print("[PASS] Em/en-dash prohibition (no markdown files on branch)")
        return CheckOutcome.passed(_VALIDATOR, revision=_HEAD, scope=_SCOPE, examined=0)

    violations, skipped = _find_dash_violations(repo_root, candidate_paths)
    examined = len(candidate_paths) - len(skipped)
    if violations:
        _print_dash_violations(violations)
        return CheckOutcome.failed(
            _VALIDATOR,
            reason=REASON_VIOLATIONS_FOUND,
            revision=_HEAD,
            scope=_SCOPE,
            examined=examined,
            findings=len(violations),
            detail="U+2014 or U+2013 in a markdown file changed on the branch",
        )

    if skipped:
        print(
            f"[WARNING] Em/en-dash prohibition ({examined} of "
            f"{len(candidate_paths)} markdown file(s) checked; "
            f"{len(skipped)} unreadable at HEAD, skipped)",
        )
        # BLOCKED, not PASS: the skipped blobs were never examined, so a PASS
        # would certify a scan that did not cover its scope. The policy licenses
        # this one pair, so the gate does not start blocking on it (decision D10).
        return CheckOutcome.blocked(
            _VALIDATOR,
            reason=REASON_ENTRIES_UNREADABLE,
            scope=_SCOPE,
            detail=(
                f"{examined} of {len(candidate_paths)} candidate file(s) examined; "
                f"{len(skipped)} unreadable at HEAD, skipped"
            ),
        )

    print(
        f"[PASS] Em/en-dash prohibition ({len(candidate_paths)} markdown file(s) checked)",
    )
    return CheckOutcome.passed(_VALIDATOR, revision=_HEAD, scope=_SCOPE, examined=examined)
