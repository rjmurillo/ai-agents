"""Machine-readable QA report evidence shared by session validators."""

from __future__ import annotations

import re
import subprocess
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any

from ai_review_common.verdict import extract_verdict

_FULL_COMMIT_PATTERN = re.compile(r"^[0-9a-f]{40}$")
_SHORT_COMMIT_PATTERN = re.compile(r"^[0-9a-f]{7,40}$")
_QA_FIELD_PATTERN = re.compile(
    r"^(qaVerdict|qaSessionLog|qaCommit):[ \t]*(.*?)$"
)
_REQUIRED_FIELDS = frozenset({"qaVerdict", "qaSessionLog", "qaCommit"})
_SESSION_LOG_ROOT = PurePosixPath(".agents/sessions")
QA_EVIDENCE_PREFIXES = (
    ".agents/memory/episodes/",
    ".project-toolkit/qa/",
    ".agents/sessions/",
)


@dataclass(frozen=True, slots=True)
class QaBinding:
    """Session and commit identity that QA evidence must match.

    ``inconsistency`` is not part of that identity. It carries a
    human-readable note about how ``commit`` was selected, set only when the
    session log's two commit fields disagreed and one had to win (ADR-102).
    Callers surface it as a warning; nothing branches on it.
    """

    session_log: str
    commit: str
    inconsistency: str | None = field(default=None, compare=False)


@dataclass(frozen=True, slots=True)
class QaReport:
    """Validated machine-readable fields from a QA report."""

    verdict: str
    session_log: str
    commit: str


def _session_log_relative(session_log: str) -> PurePosixPath:
    session_path = PurePosixPath(session_log)
    try:
        relative = session_path.relative_to(_SESSION_LOG_ROOT)
    except ValueError as exc:
        raise ValueError(
            "QA report session log must be a canonical .agents/sessions/*.json path"
        ) from exc
    if (
        session_path.is_absolute()
        or session_path.as_posix() != session_log
        or not relative.parts
        or ".." in relative.parts
        or session_path.suffix != ".json"
    ):
        raise ValueError(
            "QA report session log must be a canonical .agents/sessions/*.json path"
        )
    return relative


def session_log_identity(path: Path, *, sessions_root: Path) -> str:
    """Map a physical session file to its canonical logical identity."""
    try:
        relative = path.resolve().relative_to(sessions_root.resolve())
    except ValueError as exc:
        raise ValueError(
            f"Session log is outside the configured sessions root: {path}"
        ) from exc
    identity = (_SESSION_LOG_ROOT / PurePosixPath(relative.as_posix())).as_posix()
    _session_log_relative(identity)
    return identity


def resolve_session_log_path(
    session_log: str,
    *,
    sessions_root: Path,
) -> Path:
    """Resolve a canonical logical session identity under a physical root."""
    relative = _session_log_relative(session_log)
    path = (sessions_root.resolve() / Path(*relative.parts)).resolve()
    try:
        path.relative_to(sessions_root.resolve())
    except ValueError as exc:
        raise ValueError("QA report session log escapes the sessions root") from exc
    return path


def _qa_fields(text: str) -> dict[str, str]:
    """Return strict QA fields from leading YAML frontmatter."""
    lines = text.splitlines()
    if not lines or lines[0] != "---":
        raise ValueError("QA report is missing leading YAML frontmatter")
    try:
        closing_index = lines.index("---", 1)
    except ValueError as exc:
        raise ValueError("QA report YAML frontmatter is not closed") from exc

    fields: dict[str, str] = {}
    for line in lines[1:closing_index]:
        match = _QA_FIELD_PATTERN.fullmatch(line)
        if match is None:
            continue
        name, value = match.groups()
        if name in fields:
            raise ValueError(f"QA report frontmatter repeats {name}")
        fields[name] = value

    missing = sorted(_REQUIRED_FIELDS - fields.keys())
    if missing:
        raise ValueError(f"QA report frontmatter is missing: {', '.join(missing)}")
    return fields


def load_qa_report(path: Path) -> QaReport:
    """Load and validate a QA report's machine-readable fields."""
    try:
        fields = _qa_fields(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ValueError(f"QA report cannot be read: {path}") from exc

    verdict = fields["qaVerdict"]
    parsed_verdict = extract_verdict(f"VERDICT: {verdict}")
    if verdict != "PASS" or parsed_verdict != "PASS":
        raise ValueError(f"QA report verdict must be PASS, got {verdict!r}")

    session_log = fields["qaSessionLog"]
    _session_log_relative(session_log)

    commit = fields["qaCommit"]
    if _FULL_COMMIT_PATTERN.fullmatch(commit) is None:
        raise ValueError("QA report commit must be a full lowercase 40-character SHA")

    return QaReport(verdict=verdict, session_log=session_log, commit=commit)


def session_qa_binding(
    data: Mapping[str, Any],
    *,
    session_log: str,
    resolve_commit: Callable[[str], str | None] | None = None,
) -> QaBinding:
    """Extract the exact session-log path and validation commit."""
    episode_metrics = data.get("episodeMetrics")
    comparison = (
        episode_metrics.get("comparison")
        if isinstance(episode_metrics, Mapping)
        else None
    )
    comparison_head = comparison.get("head") if isinstance(comparison, Mapping) else None
    ending_commit = data.get("endingCommit")
    resolved_ending: str | None = None
    if isinstance(ending_commit, str) and _FULL_COMMIT_PATTERN.fullmatch(ending_commit):
        resolved_ending = ending_commit
    if (
        resolved_ending is None
        and resolve_commit is not None
        and isinstance(ending_commit, str)
        and _SHORT_COMMIT_PATTERN.fullmatch(ending_commit)
    ):
        resolved = resolve_commit(ending_commit)
        if isinstance(resolved, str) and _FULL_COMMIT_PATTERN.fullmatch(resolved):
            resolved_ending = resolved

    if isinstance(comparison_head, str) and _FULL_COMMIT_PATTERN.fullmatch(
        comparison_head
    ):
        # comparison.head wins when both fields resolve, and a disagreement is
        # reported rather than rejected (ADR-102, issue #5217). This is not
        # because the two fields naturally diverge: PR #4954 independently
        # documented the endingCommit-follows-comparison.head hand-sync
        # pattern, though that finding was never fixed by a commit, so it
        # does not appear in a HEAD-scoped corpus walk (ADR-102 Measured
        # Incidence: 44 edits, 32 commits, 36 agreeing, all either
        # first-commit creations or unrelated field backfills). That's why
        # the raise is replaced with a diagnostic rather than kept:
        # comparison.head is the field QA rebinding advances past the
        # session's own last authored commit
        # (session-log.schema.json's commitHead field exists to preserve that
        # ownership), while endingCommit advances on its own schedule, a
        # follow-up commit re-pointed after a rebase (.claude/rules/
        # session-logs.md MUST 2 and MUST 3).
        #
        # Both SHAs below have already passed _FULL_COMMIT_PATTERN, so the
        # message cannot carry unvalidated session-log content.
        inconsistency = None
        if resolved_ending is not None and comparison_head != resolved_ending:
            inconsistency = (
                "Session log comparison head and endingCommit are different "
                f"full commit SHAs ({comparison_head} != {resolved_ending}); "
                "binding QA evidence to comparison head"
            )
        return QaBinding(
            session_log=session_log,
            commit=comparison_head,
            inconsistency=inconsistency,
        )
    if resolved_ending is not None:
        return QaBinding(session_log=session_log, commit=resolved_ending)

    raise ValueError("Session log must resolve a full 40-character QA commit")


def validate_qa_report(
    path: Path, expected: QaBinding, *, head: str, repo_root: Path
) -> QaReport:
    """Require a passing QA report bound to the expected session, and not stale.

    ``head`` is the commit to check staleness against (ADR-096). A real
    (non-evidence-path) change between ``report.commit`` and ``head`` is a
    hard failure. A commit range containing only paths under
    ``QA_EVIDENCE_PREFIXES`` (a pure rebind, session-log touch-up, or other
    bookkeeping commit) is not. ``head`` is required, not optional: an
    earlier design let a caller supply no head and silently skip staleness
    checking entirely (issue #5164 round-1 review), which this signature
    makes impossible to construct.
    """
    report = load_qa_report(path)
    if report.session_log != expected.session_log:
        raise ValueError(
            "QA report session log does not match current session: "
            f"{report.session_log} != {expected.session_log}"
        )
    changed = post_qa_code_changes(report.commit, head, repo_root=repo_root)
    if changed:
        raise ValueError(
            "QA report is stale; code changed after its commit: " + ", ".join(changed)
        )
    return report


def non_evidence_paths(paths: list[str]) -> list[str]:
    """Return paths that represent work performed after QA completed."""
    return [
        path
        for path in paths
        if path and not path.startswith(QA_EVIDENCE_PREFIXES)
    ]


def post_qa_code_changes(
    commit: str,
    head: str,
    *,
    repo_root: Path,
) -> list[str]:
    """Return non-evidence paths touched by any commit after QA."""
    ancestor = subprocess.run(
        ["git", "merge-base", "--is-ancestor", commit, head],
        cwd=repo_root,
        check=False,
        stdout=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=10,
    )
    if ancestor.returncode == 1:
        raise ValueError("QA commit is not an ancestor of validation head")
    if ancestor.returncode != 0:
        raise ValueError("Could not verify QA commit ancestry")

    changes = subprocess.run(
        [
            "git",
            "log",
            "--format=",
            "--name-only",
            "--no-renames",
            "-m",
            "-z",
            f"{commit}..{head}",
        ],
        cwd=repo_root,
        check=False,
        stdout=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=10,
    )
    if changes.returncode != 0:
        raise ValueError("Could not inspect commits after QA")
    changed_paths = non_evidence_paths(changes.stdout.split("\0"))
    return list(dict.fromkeys(changed_paths))
