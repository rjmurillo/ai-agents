#!/usr/bin/env python3
"""Detect infrastructure and security-critical file changes.

Analyzes changed files to identify those requiring security agent review.
Returns risk level and matching patterns.

EXIT CODES (ADR-035):
    0 - Detection completed. Without ``--require-security-review`` this is
        the only exit code, so every documented advisory use stays
        non-blocking. With it, also: no CRITICAL finding, or a CRITICAL
        finding covered by a valid security review marker.
    1 - ``--require-security-review`` and a CRITICAL finding has no valid
        marker on the ref.
    3 - ``--require-security-review`` and git could not answer (missing, timed
        out, unreadable). An unanswered marker check never counts as a marker.

SECURITY REVIEW MARKER (issue #5636, decision D9). The marker is the
``/review`` skill's SHA-bound trailer, quoted from
``.claude/skills/review/scripts/validate_review_marker.py``:

    Reviewed-By: /review@<axis1,axis2,...> on <40-or-64-hex-sha>
    Review-Artifact: sha256:<64-hex-digest-of-the-review-report>

    "``/review@`` is a literal prefix. ``<axis-list>`` is one or more
    comma-separated axis stems (``analyst``, ``security``, ...). It MUST be
    non-empty. `` on `` (space-on-space) separates the axis list from the
    reviewed SHA. ``<sha>`` is the git object name of the commit whose review
    state the marker asserts: the reviewed tip."

The marker is an empty single-parent commit whose trailer names its parent.
Its body also carries the review report that the ``Review-Artifact`` digest
covers (issue #6438): a bare trailer proves nothing, because any agent can type
one. The report names the reviewed SHA and one passing row per marker axis.
This script accepts the ref only when that commit shape holds and the trailer
binds the ref's own parent, so any commit landed after ``/review`` moves the
ref to a commit with no binding marker and a new push invalidates the marker.

Stricter/looser/different than canonical: the same commit-shape and SHA
binding rules as ``validate_review_marker.validate_ref``, plus one addition.
The report and digest checks below are the same checks as
``validate_review_marker.check_review_artifact``;
``tests/skills/security-detection/test_security_review_artifact.py`` runs both
on one table of messages and fails when they disagree. The axis list MUST
contain ``security``, because a marker for a review that
never ran the security axis does not review a CRITICAL security surface. This
module reimplements the check rather than importing the review skill, because
each skill ships as a self-contained directory and cannot import a sibling
skill's script at runtime (``.claude/rules/plugin-self-containment.md``).
The scope is the ref only, HEAD by default. The pre-push hook passes each
pushed SHA as ``--ref`` (issue #6076), so a pushed branch is judged by its own
marker, not by the checked-out HEAD's.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

MARKER_TRAILER_KEY = "Reviewed-By"
ARTIFACT_TRAILER_KEY = "Review-Artifact"
REPORT_BEGIN = "--- review report ---"
REPORT_END = "--- end review report ---"
PASSING_VERDICTS = frozenset({"PASS", "COMPLIANT", "WARN", "PARTIAL"})
SECURITY_AXIS = "security"
GIT_TIMEOUT_SECONDS = 15

# Typed result vocabulary for the ``security_review`` object. Mirrored, not
# imported, from ``scripts/validation/evidence.py``: this skill ships as a
# self-contained directory and a consumer install has no ``scripts/`` package
# (``.claude/rules/plugin-self-containment.md``). Canonical source, quoted:
#
#     class EvidenceState(str, Enum):
#         PASS = "PASS"  FAIL = "FAIL"  SKIP = "SKIP"
#         BLOCKED = "BLOCKED"  UNKNOWN = "UNKNOWN"
#     REASON_POLICY_EXEMPT = "policy.exempt"
#     REASON_VIOLATIONS_FOUND = "violations.found"
#     REASON_TOOL_ABSENT = "tool.absent"
#     REASON_TIMEOUT = "timeout"
#     REASON_MALFORMED_OUTPUT = "output.malformed"
#     REASON_LOOKUP_FAILED = "lookup.failed"
#
# ``tests/skills/security-detection/test_typed_vocabulary_parity.py`` fails when
# a value here is not in ``evidence.py``. ``PASS`` carries no reason, as in
# ``CheckOutcome.__post_init__``.
TYPED_RESULT_VOCABULARY = {
    "PASS": "PASS",
    "FAIL": "FAIL",
    "SKIP": "SKIP",
    "BLOCKED": "BLOCKED",
    "UNKNOWN": "UNKNOWN",
    "REASON_POLICY_EXEMPT": "policy.exempt",
    "REASON_VIOLATIONS_FOUND": "violations.found",
    "REASON_TOOL_ABSENT": "tool.absent",
    "REASON_TIMEOUT": "timeout",
    "REASON_MALFORMED_OUTPUT": "output.malformed",
    "REASON_LOOKUP_FAILED": "lookup.failed",
}
_V = TYPED_RESULT_VOCABULARY

# Same pattern as validate_review_marker._MARKER_VALUE_RE.
_MARKER_VALUE_RE = re.compile(
    r"^/review@(?P<axes>[A-Za-z0-9_-]+(?:,[A-Za-z0-9_-]+)*) on "
    r"(?P<sha>[0-9A-Fa-f]{40}|[0-9A-Fa-f]{64})$"
)

_ARTIFACT_VALUE_RE = re.compile(r"^sha256:(?P<digest>[0-9a-f]{64})$")
_REPORT_SHA_RE = re.compile(r"^Reviewed-SHA: (?P<sha>[0-9A-Fa-f]{40}|[0-9A-Fa-f]{64})$")
_REPORT_ROW_RE = re.compile(r"^(?P<axis>[A-Za-z0-9_-]+): (?P<verdict>[A-Z_]+)$")

# Critical patterns - security review REQUIRED
CRITICAL_PATTERNS = [
    r"^\.github/workflows/.*\.(yml|yaml)$",
    r"^\.github/actions/",
    r"^scripts/validation/git_hook_policy\.py$",
    r"^(?:lefthook|\.lefthook|\.config/lefthook)(?:-local)?\.(?:yml|yaml|json|jsonc|toml)$",
    r"^\.husky/",
    r".*/Auth/",
    r".*/Authentication/",
    r".*/Authorization/",
    r".*/Security/",
    r".*/Identity/",
    r".*Auth.*\.(cs|ts|js|py)$",
    r"\.env.*$",
    r".*\.(pem|key|p12|pfx|jks)$",
    r".*secret.*",
    r".*credential.*",
    r".*password.*",
]

# High patterns - security review RECOMMENDED
HIGH_PATTERNS = [
    r"^build/.*\.(ps1|sh|cmd|bat)$",
    r"^scripts/.*\.(ps1|sh)$",
    r"^Makefile$",
    r"^Dockerfile.*$",
    r"^docker-compose.*\.(yml|yaml)$",
    r".*/Controllers/",
    r".*/Endpoints/",
    r".*/Handlers/",
    r".*/Middleware/",
    r"^appsettings.*\.json$",
    r"^web\.config$",
    r"^app\.config$",
    r"^config/.*\.(json|yml|yaml)$",
    r".*\.tf$",
    r".*\.tfvars$",
    r".*\.bicep$",
    r"^nuget\.config$",
    r"^\.npmrc$",
]


def matches_pattern(file_path: str, patterns: list[str]) -> bool:
    """Check if a file path matches any of the given regex patterns."""
    for pattern in patterns:
        if re.search(pattern, file_path, re.IGNORECASE):
            return True
    return False


def get_security_risk_level(file_path: str) -> str:
    """Determine security risk level for a file path."""
    normalized = file_path.replace("\\", "/")
    if matches_pattern(normalized, CRITICAL_PATTERNS):
        return "critical"
    if matches_pattern(normalized, HIGH_PATTERNS):
        return "high"
    return "none"


def get_staged_files() -> list[str]:
    """Get list of staged files from git."""
    try:
        result = subprocess.run(
            ["git", "diff", "--cached", "--name-only"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            return []
        return [f for f in result.stdout.strip().splitlines() if f.strip()]
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return []


def get_files_from_stdin() -> list[str]:
    """Read NUL-delimited file paths without interpreting option-shaped names."""
    return [file_path for file_path in sys.stdin.read().split("\0") if file_path]


def detect_infrastructure(
    changed_files: list[str] | None = None,
    use_git_staged: bool = False,
) -> dict[str, Any]:
    """Analyze files and return security risk findings."""
    if use_git_staged:
        changed_files = get_staged_files()

    if not changed_files:
        return {
            "findings": [],
            "highest_risk": "none",
            "file_count": 0,
        }

    findings = []
    highest_risk = "none"

    for file_path in changed_files:
        risk = get_security_risk_level(file_path)
        if risk != "none":
            findings.append({"File": file_path, "RiskLevel": risk})
            if risk == "critical":
                highest_risk = "critical"
            elif risk == "high" and highest_risk != "critical":
                highest_risk = "high"

    return {
        "findings": findings,
        "highest_risk": highest_risk,
        "file_count": len(changed_files),
    }


class GitReadError(Exception):
    """Git could not answer a marker question.

    ``state`` and ``reason`` type the failure in the evidence vocabulary: a
    missing binary, a spawn error, or a timeout means git never answered
    (``BLOCKED``); output that would not decode means an answer came back and
    could not be trusted (``UNKNOWN``).
    """

    def __init__(self, message: str, *, state: str = "BLOCKED", reason: str = "lookup.failed"):
        super().__init__(message)
        self.state = state
        self.reason = reason


def _git(args: list[str], repo_root: Path) -> str:
    """Run git in ``repo_root`` and return stdout, or raise ``GitReadError``."""
    if shutil.which("git") is None:
        raise GitReadError(
            "git not found on PATH", state=_V["BLOCKED"], reason=_V["REASON_TOOL_ABSENT"]
        )
    try:
        result = subprocess.run(  # subprocess-encoding: strict-ok
            ["git", "-C", str(repo_root), *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=GIT_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as exc:
        raise GitReadError(
            f"git {args[0]} timed out after {GIT_TIMEOUT_SECONDS}s",
            state=_V["BLOCKED"],
            reason=_V["REASON_TIMEOUT"],
        ) from exc
    except UnicodeDecodeError as exc:
        raise GitReadError(
            f"git {args[0]} output was not valid UTF-8",
            state=_V["UNKNOWN"],
            reason=_V["REASON_MALFORMED_OUTPUT"],
        ) from exc
    except OSError as exc:
        raise GitReadError(
            f"git {args[0]} could not run: {exc}",
            state=_V["BLOCKED"],
            reason=_V["REASON_TOOL_ABSENT"],
        ) from exc
    if result.returncode != 0:
        detail = result.stderr.strip() or f"exit {result.returncode}"
        raise GitReadError(f"git {args[0]} failed: {detail}")
    return result.stdout


def _security_marker_axes(values: list[str], parent_sha: str) -> tuple[str, ...] | None:
    """Return the axes of the first trailer value that names ``parent_sha`` and security."""
    for value in values:
        match = _MARKER_VALUE_RE.match(value.strip())
        if match is None:
            continue
        axes = tuple(match.group("axes").split(","))
        if match.group("sha").lower() == parent_sha and SECURITY_AXIS in axes:
            return axes
    return None


def _extract_report(text: str) -> list[str] | None:
    """Return the lines of the single report block in ``text``, or ``None``."""
    lines = [line.rstrip() for line in text.splitlines()]
    begins = [i for i, line in enumerate(lines) if line == REPORT_BEGIN]
    ends = [i for i, line in enumerate(lines) if line == REPORT_END]
    if len(begins) != 1 or len(ends) != 1 or begins[0] > ends[0]:
        return None
    return [line for line in lines[begins[0] + 1 : ends[0]] if line]


def _report_digest(report: list[str]) -> str:
    payload = "".join(f"{line}\n" for line in report).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _report_rows_back_axes(report: list[str], parent_sha: str, axes: tuple[str, ...]) -> bool:
    """Return True when ``report`` names ``parent_sha`` and one passing row per axis."""
    sha_lines = [_REPORT_SHA_RE.match(line) for line in report]
    if [m.group("sha").lower() for m in sha_lines if m] != [parent_sha]:
        return False
    rows = [line for line, m in zip(report, sha_lines, strict=True) if m is None]
    parsed = [_REPORT_ROW_RE.match(line) for line in rows]
    if not all(parsed):
        return False
    verdicts = {m.group("axis"): m.group("verdict") for m in parsed if m}
    return (
        len(verdicts) == len(rows)
        and set(verdicts) == set(axes)
        and all(v in PASSING_VERDICTS for v in verdicts.values())
    )


def check_review_artifact(
    message: str, digest_values: list[str], parent_sha: str, axes: tuple[str, ...]
) -> bool:
    """Return True when the message carries a report that the digest trailer covers."""
    report = _extract_report(message)
    if report is None:
        return False
    digests = [
        m.group("digest") for v in digest_values if (m := _ARTIFACT_VALUE_RE.match(v.strip()))
    ]
    return _report_digest(report) in digests and _report_rows_back_axes(report, parent_sha, axes)


def find_security_review_marker(ref: str, repo_root: Path) -> tuple[bool, str]:
    """Report whether ``ref`` is a marker commit binding its parent with the security axis.

    Returns ``(satisfied, detail)``. Raises ``GitReadError`` when git cannot
    answer, which the caller maps to exit 3 and never treats as satisfied.
    """
    if ref.startswith("-"):
        raise GitReadError(f"invalid ref {ref!r}: refs must not start with '-'")
    head = _git(["rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}"], repo_root).strip()
    parents = _git(["show", "-s", "--format=%P", head], repo_root).split()
    if len(parents) != 1:
        return False, f"{head[:12]} has {len(parents)} parents; a marker is a single-parent commit"
    tree = _git(["show", "-s", "--format=%T", head], repo_root).strip()
    parent_tree = _git(["show", "-s", "--format=%T", parents[0]], repo_root).strip()
    if tree != parent_tree:
        return False, f"{head[:12]} changes files; a marker is an empty commit"
    trailer_format = f"--format=%(trailers:key={MARKER_TRAILER_KEY},valueonly,unfold)"
    values = [
        v for v in _git(["log", "-1", trailer_format, head], repo_root).splitlines() if v.strip()
    ]
    axes = _security_marker_axes(values, parents[0])
    if axes is not None:
        message = _git(["log", "-1", "--format=%B", head], repo_root)
        digest_format = f"--format=%(trailers:key={ARTIFACT_TRAILER_KEY},valueonly,unfold)"
        digests = _git(["log", "-1", digest_format, head], repo_root).splitlines()
        if not check_review_artifact(message, digests, parents[0], axes):
            return False, (
                f"{head[:12]} has a security marker but no valid review report: a bare "
                f"'{MARKER_TRAILER_KEY}' trailer does not show a review ran"
            )
        return True, f"{head[:12]} carries a security review marker binding {parents[0][:12]}"
    return False, (
        f"{head[:12]} has no '{MARKER_TRAILER_KEY}: /review@...{SECURITY_AXIS}... on "
        f"{parents[0][:12]}' trailer"
    )


def _review_result(
    *, required: bool, satisfied: bool, state: str, reason: str, detail: str
) -> dict[str, Any]:
    """Build the ``security_review`` object: the old fields plus the typed pair."""
    return {
        "required": required,
        "satisfied": satisfied,
        "detail": detail,
        "state": state,
        "reason": reason,
    }


def enforce_security_review(result: dict[str, Any], ref: str, repo_root: Path) -> int:
    """Return the exit code for ``--require-security-review`` and annotate ``result``.

    The annotation types every path. No CRITICAL finding is ``SKIP`` with
    ``policy.exempt`` (the review does not apply). A bound marker is ``PASS``.
    A CRITICAL finding without one is ``FAIL`` with ``violations.found``. A git
    read that failed carries its own state and reason and exits 3.
    """
    if result["highest_risk"] != "critical":
        result["security_review"] = _review_result(
            required=False,
            satisfied=True,
            state=_V["SKIP"],
            reason=_V["REASON_POLICY_EXEMPT"],
            detail="no CRITICAL finding",
        )
        return 0
    try:
        satisfied, detail = find_security_review_marker(ref, repo_root)
    except GitReadError as exc:
        result["security_review"] = _review_result(
            required=True, satisfied=False, state=exc.state, reason=exc.reason, detail=str(exc)
        )
        return 3
    result["security_review"] = _review_result(
        required=True,
        satisfied=satisfied,
        state=_V["PASS"] if satisfied else _V["FAIL"],
        reason="" if satisfied else _V["REASON_VIOLATIONS_FOUND"],
        detail=detail,
    )
    return 0 if satisfied else 1


def main() -> int:
    """Entry point."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Detect infrastructure and security-critical file changes",
    )
    file_source = parser.add_mutually_exclusive_group()
    file_source.add_argument(
        "--files",
        nargs="*",
        help="Changed file paths to analyze",
    )
    file_source.add_argument(
        "--use-git-staged",
        action="store_true",
        help="Analyze staged files from git",
    )
    file_source.add_argument(
        "--files-from-stdin",
        action="store_true",
        help="Read NUL-delimited changed file paths from stdin",
    )
    parser.add_argument("--json", action="store_true", help="Output results as JSON")
    parser.add_argument(
        "--require-security-review",
        action="store_true",
        help="Exit 1 on a CRITICAL finding unless --ref carries a security review marker "
        "(exit 3 when git cannot answer). Without this flag the exit code is always 0.",
    )
    parser.add_argument(
        "--ref", default="HEAD", help="Commit whose marker is checked (default: HEAD)"
    )
    parser.add_argument(
        "--repo-root", type=Path, default=None, help="Repository root (default: cwd)"
    )
    args = parser.parse_args()

    changed_files = get_files_from_stdin() if args.files_from_stdin else args.files
    result = detect_infrastructure(
        changed_files=changed_files,
        use_git_staged=args.use_git_staged,
    )

    exit_code = 0
    if args.require_security_review:
        repo_root = (args.repo_root or Path.cwd()).resolve()
        exit_code = enforce_security_review(result, args.ref, repo_root)
        if not args.json:
            _report_exempt(result)

    if args.json:
        print(json.dumps(result, indent=2))
        return exit_code

    if not result["findings"]:
        print("No infrastructure/security files detected.")
        return exit_code

    print("")
    print("=== Security Review Detection ===")
    print("")

    if result["highest_risk"] == "critical":
        print("CRITICAL: Security agent review REQUIRED")
    else:
        print("HIGH: Security agent review RECOMMENDED")

    print("")
    print("Matching files:")

    for finding in result["findings"]:
        level = finding["RiskLevel"].upper()
        print(f"  [{level}] {finding['File']}")

    print("")
    print("Run security agent before implementation:")
    print('  Task(subagent_type="security", prompt="Review infrastructure changes")')
    print("")

    return exit_code if exit_code == 0 else _report_blocked(result, exit_code)


def _report_exempt(result: dict[str, Any]) -> None:
    """Print one typed ``SKIP`` line when the marker check did not apply.

    Without it a push with no CRITICAL finding prints nothing about the check,
    so a machine cannot tell "exempt" from "never ran". Only the exempt state
    prints here: a pass is quiet, and the blocked states print in
    ``_report_blocked``.
    """
    review = result["security_review"]
    if review["state"] == _V["SKIP"]:
        print(
            f"[SKIP] detect_infrastructure reason={review['reason']} "
            f"scope=security review marker on the pushed ref detail={json.dumps(review['detail'])}",
            file=sys.stderr,
        )


def _report_blocked(result: dict[str, Any], exit_code: int) -> int:
    """Print why ``--require-security-review`` blocked and return ``exit_code``.

    The first line has the ``[STATE] validator reason=code scope=... detail=...``
    shape ``CheckOutcome.report_line`` prints, so one grep counts this path with
    the other typed gates.
    """
    review = result["security_review"]
    detail = f"CRITICAL change without a security review marker: {review['detail']}"
    print(
        f"[{review['state']}] detect_infrastructure reason={review['reason']} "
        f"scope=security review marker on the pushed ref detail={json.dumps(detail)}",
        file=sys.stderr,
    )
    print(
        "Run /review with the security axis; it writes the marker commit on PASS.", file=sys.stderr
    )
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
