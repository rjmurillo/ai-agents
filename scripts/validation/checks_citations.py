#!/usr/bin/env python3
"""Typed pre-PR wrappers for the citation and spec-contradiction validators.

Moved out of ``checks_spec.py`` (issue #5636) so each wrapper can report the
typed evidence states without pushing that module past the 500-line ceiling.
``checks_spec`` re-exports these names, so ``from checks_spec import
validate_canonical_citations`` and ``from scripts.validation.pre_pr import ...``
keep working.

Each wrapper runs a sibling script and maps what came back to one
:class:`CheckOutcome`. Before this, all three collapsed every non-pass path to a
bare ``bool``: an absent script, a soft warning, and a clean run were one value.

The soft-warn scripts (``check_canonical_citations.py``, ``spec_contradiction.py
--advisory``) exit 0 even with findings, so the exit code cannot tell a clean run
from a warned one. Their first status line can, and that line is their own
contract, quoted from source:

    check_canonical_citations.format_report:  "[PASS] No uncited mirror-claims found."
                                              f"{label} {n} uncited mirror-claim(s) found."
                                              (label is "[FAIL]" strict, "[WARN]" otherwise)
    check_canonical_citations.main:           "[SKIP] no scan roots present ..."
    spec_contradiction.format_report:         "[PASS] No spec-vs-code contradictions detected."
                                              f"[WARN] {n} spec-vs-code contradiction(s) detected:"

Stricter/looser/different than canonical: a stdout with no recognized status
token and exit 0 is ``BLOCKED`` with reason ``output.malformed``, licensed for
these two validators only, where the old wrapper returned ``True``. That keeps
the push unblocked and makes a silently changed report format countable.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _SCRIPT_DIR.parent.parent
for _path in (_SCRIPT_DIR, _PROJECT_ROOT):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from checks_common import _resolve_branch_base_ref, _run_subprocess  # noqa: E402

from scripts.validation.evidence import (  # noqa: E402
    REASON_ADVISORY_FINDINGS,
    REASON_MALFORMED_OUTPUT,
    REASON_SCRIPT_ABSENT,
    REASON_SCRIPT_FAILED,
    REASON_TREE_ABSENT,
    REASON_VIOLATIONS_FOUND,
    WORKING_TREE,
    CheckOutcome,
)
from scripts.validation.subprocess_runner import classify_subprocess_failure  # noqa: E402

__all__ = [
    "validate_canonical_citations",
    "validate_orchestrator_citations",
    "validate_spec_contradiction",
]

_STATUS_LINE = re.compile(r"^\[(PASS|WARN|FAIL|SKIP)\](?:\s+(\d+)\b)?", re.MULTILINE)

_CANONICAL = "validate_canonical_citations"
_ORCHESTRATOR = "validate_orchestrator_citations"
_CONTRADICTION = "validate_spec_contradiction"


def _read_status(stdout: str) -> tuple[str, int | None]:
    """Return the worst status token in ``stdout`` and its count, or ``("", None)``.

    Worst wins (``WARN``, then ``PASS``, then ``SKIP``), so an early ``[PASS]``
    line cannot hide a later ``[WARN]``. A ``[FAIL]`` token is not read: at exit 0
    it contradicts the exit code, so it falls through as unrecognized.
    """
    found = {m.group(1): m for m in reversed(list(_STATUS_LINE.finditer(stdout)))}
    for status in ("WARN", "PASS", "SKIP"):
        match = found.get(status)
        if match is not None:
            return status, int(match.group(2)) if match.group(2) else None
    return "", None


def _status_outcome(validator: str, scope: str, stdout: str) -> CheckOutcome:
    """Map a soft-warn script's status line to a typed result.

    Called only when the script exited 0. ``[WARN]`` is the finding the exit
    code hides, so it becomes ``FAIL`` with reason ``advisory.findings``.
    """
    status, count = _read_status(stdout)
    if status == "PASS":
        return CheckOutcome.passed(validator, revision=WORKING_TREE, scope=scope)
    if status == "SKIP":
        return CheckOutcome.skipped(
            validator,
            reason=REASON_TREE_ABSENT,
            scope=scope,
            detail="the script found no scan roots",
        )
    if status == "WARN":
        return CheckOutcome.failed(
            validator,
            reason=REASON_ADVISORY_FINDINGS,
            revision=WORKING_TREE,
            scope=scope,
            findings=count or None,
            detail="the script reported findings and exited 0",
        )
    return CheckOutcome.blocked(
        validator,
        reason=REASON_MALFORMED_OUTPUT,
        scope=scope,
        detail="exit 0 with no [PASS], [WARN], or [SKIP] status line to read",
    )


def _print_streams(stdout: str, stderr: str) -> None:
    if stdout.strip():
        print(stdout.strip())
    if stderr.strip():
        print(stderr.strip(), file=sys.stderr)


def validate_canonical_citations(repo_root: Path) -> CheckOutcome:
    """Heuristic check for uncited mirror-claims.

    Soft-warn by default. Set STRICT_CANONICAL_CHECK=1 in the environment
    to upgrade to a hard failure. In soft-warn mode the script exits 0, so this
    wrapper reads its status line: findings are ``FAIL`` with reason
    ``advisory.findings`` (licensed, so the push is not blocked), a clean run is
    ``PASS``, and an absent script is ``SKIP``. A non-zero exit is ``FAIL`` and
    blocks, exactly as the old ``bool(exit_code == 0)`` did.

    See: `.claude/rules/canonical-source-mirror.md` and PR #1887
    retrospective Layer 4.
    """
    scope = "docstrings and top-level comments that claim to mirror a source"
    script = repo_root / "scripts" / "validation" / "check_canonical_citations.py"
    if not script.exists():
        print("[WARNING] check_canonical_citations.py not found (skipping)")
        return CheckOutcome.skipped(
            _CANONICAL,
            reason=REASON_SCRIPT_ABSENT,
            scope=scope,
            detail="scripts/validation/check_canonical_citations.py not present",
        )

    exit_code, stdout, stderr = _run_subprocess(
        [sys.executable, str(script), "--repo-root", str(repo_root)]
    )
    _print_streams(stdout, stderr)

    if exit_code != 0:
        reason = classify_subprocess_failure(exit_code, stderr, default=REASON_VIOLATIONS_FOUND)
        return CheckOutcome.failed(
            _CANONICAL,
            reason=reason,
            revision=WORKING_TREE,
            scope=scope,
            detail=f"check_canonical_citations.py exited {exit_code}",
        )
    return _status_outcome(_CANONICAL, scope, stdout)


def validate_orchestrator_citations(repo_root: Path) -> CheckOutcome:
    """Verify orchestrator prose path citations resolve to real files.

    Wraps ``scripts/validation/check_orchestrator_citations.py``, which fails
    when a backtick path citation in ``.claude/skills/pr-quality-all/SKILL.md``
    points to a file that no longer exists. A stale citation (e.g. the removed
    ``AIReviewCommon.psm1`` reference fixed in PR #1934) sends the next reader
    to a dead pointer. See Issue #1966.

    Fails closed when the validator is absent, matching
    ``validate_agent_catalog``: this gate exits non-zero on a stale citation,
    so a missing script is a gate that cannot run, not a pass (issue #5636).
    The absent case is ``FAIL`` with reason ``script.absent`` rather than
    ``BLOCKED``: ``BLOCKED`` would move the pre-PR exit code from 1 to 3 on a
    path that already blocks, and ``pre_pr.run_validation`` keeps ``FAIL`` for
    the same reason on a raising validator.
    """
    scope = "path citations in .claude/skills/pr-quality-all/SKILL.md"
    script = repo_root / "scripts" / "validation" / "check_orchestrator_citations.py"
    if not script.exists():
        print(
            "[ERROR] check_orchestrator_citations.py absent; the orchestrator "
            "citation gate cannot run. Hard failure: a gate that cannot run is "
            "not a pass.",
            file=sys.stderr,
        )
        return CheckOutcome.failed(
            _ORCHESTRATOR,
            reason=REASON_SCRIPT_ABSENT,
            scope=scope,
            detail="scripts/validation/check_orchestrator_citations.py not present",
        )

    exit_code, stdout, stderr = _run_subprocess(
        [sys.executable, str(script), "--repo-root", str(repo_root)]
    )
    _print_streams(stdout, stderr)
    if exit_code != 0:
        reason = classify_subprocess_failure(exit_code, stderr, default=REASON_VIOLATIONS_FOUND)
        return CheckOutcome.failed(
            _ORCHESTRATOR,
            reason=reason,
            revision=WORKING_TREE,
            scope=scope,
            detail=f"check_orchestrator_citations.py exited {exit_code}",
        )
    return CheckOutcome.passed(_ORCHESTRATOR, revision=WORKING_TREE, scope=scope)


def validate_spec_contradiction(repo_root: Path) -> CheckOutcome:
    """Advisory check for PR-description vs linked-issue vs code contradictions.

    Wraps ``scripts/validation/spec_contradiction.py`` in ``--advisory`` mode,
    so a heuristic false positive never blocks the local pre-PR cycle. The
    script catches the PR #1897 round-7 loop locally (Issue #1894 claimed
    ``model_tier: sonnet`` while the committed agent frontmatter shipped
    ``model: opus``), which CI's "Validate Spec Coverage" gate surfaced only
    after each push. Never blocks; the result is typed (issue #5636): findings
    are ``FAIL`` with reason ``advisory.findings``, a non-zero exit (a
    configuration error under ``--advisory``) is ``BLOCKED`` with reason
    ``script.failed``, and an absent script is ``SKIP``. ``pre_pr_policy``
    licenses each pair by name.

    See Issue #1920 and the retrospective at
    ``.project-toolkit/retrospective/2026-05-08-pr-1897-confident-incorrectness-recurrence.md``.
    """
    scope = "PR description and linked issues against committed agent frontmatter"
    script = repo_root / "scripts" / "validation" / "spec_contradiction.py"
    if not script.exists():
        print("[WARNING] spec_contradiction.py not found (skipping)")
        return CheckOutcome.skipped(
            _CONTRADICTION,
            reason=REASON_SCRIPT_ABSENT,
            scope=scope,
            detail="scripts/validation/spec_contradiction.py not present",
        )

    base_ref = _resolve_branch_base_ref(repo_root)
    cmd = [sys.executable, str(script), "--repo-root", str(repo_root), "--advisory"]
    if base_ref:
        cmd.extend(["--base", base_ref])
    exit_code, stdout, stderr = _run_subprocess(cmd)
    _print_streams(stdout, stderr)
    if exit_code != 0:
        # A fixed reason, not classify_subprocess_failure: that would emit
        # ``timeout`` or ``process.signaled``, which no licence names, and a
        # gate that always passed would start blocking on a timeout.
        return CheckOutcome.blocked(
            _CONTRADICTION,
            reason=REASON_SCRIPT_FAILED,
            scope=scope,
            detail=f"spec_contradiction.py exited {exit_code} under --advisory",
        )
    return _status_outcome(_CONTRADICTION, scope, stdout)
