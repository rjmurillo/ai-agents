"""Tests for machine-readable QA report evidence."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

LIB_DIR = Path(__file__).resolve().parents[1] / ".claude" / "lib"
sys.path.insert(0, str(LIB_DIR))

from qa_report import (  # noqa: E402
    QaBinding,
    load_qa_report,
    non_evidence_paths,
    session_qa_binding,
    validate_qa_report,
)

COMMIT = "a" * 40
SESSION_LOG = ".agents/sessions/2026-08-06-session-10004-memory-index-duplicate.json"


def _write_report(
    path: Path,
    *,
    verdict: str = "PASS",
    session_log: str = SESSION_LOG,
    commit: str = COMMIT,
    extra_frontmatter: str = "",
) -> None:
    path.write_text(
        "---\n"
        f"qaVerdict: {verdict}\n"
        f"qaSessionLog: {session_log}\n"
        f"qaCommit: {commit}\n"
        f"{extra_frontmatter}"
        "---\n"
        "# QA Report\n",
        encoding="utf-8",
    )


def test_loads_passing_report_with_machine_readable_binding(tmp_path: Path) -> None:
    report_path = tmp_path / "report.md"
    _write_report(report_path, extra_frontmatter="title: QA evidence\n")

    report = load_qa_report(report_path)

    assert report.verdict == "PASS"
    assert report.session_log == SESSION_LOG
    assert report.commit == COMMIT


def test_rejects_unreadable_report(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="QA report cannot be read"):
        load_qa_report(tmp_path / "missing.md")


@pytest.mark.parametrize("verdict", ["DEFERRED", "FAIL", "WARN", "UNKNOWN", "pass"])
def test_rejects_every_non_passing_verdict(tmp_path: Path, verdict: str) -> None:
    report_path = tmp_path / "report.md"
    _write_report(report_path, verdict=verdict)

    with pytest.raises(ValueError, match="verdict must be PASS"):
        load_qa_report(report_path)


@pytest.mark.parametrize(
    ("content", "message"),
    [
        ("# QA\n", "missing leading YAML frontmatter"),
        ("---\nqaVerdict: PASS\n", "frontmatter is not closed"),
        (
            "---\nqaVerdict: PASS\nqaSession: 10004\n---\n",
            "frontmatter is missing: qaCommit, qaSessionLog",
        ),
        (
            "---\nqaVerdict: PASS\nqaVerdict: PASS\n"
            f"qaSessionLog: {SESSION_LOG}\nqaCommit: {COMMIT}\n---\n",
            "frontmatter repeats qaVerdict",
        ),
    ],
)
def test_rejects_missing_or_malformed_frontmatter(
    tmp_path: Path,
    content: str,
    message: str,
) -> None:
    report_path = tmp_path / "report.md"
    report_path.write_text(content, encoding="utf-8")

    with pytest.raises(ValueError, match=message):
        load_qa_report(report_path)


@pytest.mark.parametrize(
    "session_log",
    [
        "/absolute/session.json",
        ".agents/sessions/../qa/report.json",
        ".agents\\sessions\\session.json",
        ".agents/sessions/session.md",
        "sessions/session.json",
        "",
    ],
)
def test_rejects_noncanonical_session_identity(
    tmp_path: Path,
    session_log: str,
) -> None:
    report_path = tmp_path / "report.md"
    _write_report(report_path, session_log=session_log)

    with pytest.raises(ValueError, match="canonical .agents/sessions"):
        load_qa_report(report_path)


@pytest.mark.parametrize("commit", ["a" * 39, "a" * 41, "A" * 40, "abcdef1234"])
def test_rejects_non_full_commit(tmp_path: Path, commit: str) -> None:
    report_path = tmp_path / "report.md"
    _write_report(report_path, commit=commit)

    with pytest.raises(ValueError, match="full lowercase 40-character SHA"):
        load_qa_report(report_path)


def test_rejects_unrelated_session(tmp_path: Path) -> None:
    report_path = tmp_path / "report.md"
    _write_report(report_path, session_log=".agents/sessions/unrelated.json")

    with pytest.raises(ValueError, match="unrelated.json"):
        validate_qa_report(
            report_path,
            QaBinding(session_log=SESSION_LOG, commit=COMMIT),
        )


def test_accepts_matching_session_and_commit(tmp_path: Path) -> None:
    report_path = tmp_path / "report.md"
    _write_report(report_path)

    report = validate_qa_report(
        report_path,
        QaBinding(session_log=SESSION_LOG, commit=COMMIT),
    )

    assert report.verdict == "PASS"


def test_rejects_stale_commit(tmp_path: Path) -> None:
    report_path = tmp_path / "report.md"
    _write_report(report_path, commit="b" * 40)

    with pytest.raises(ValueError, match=f"{'b' * 40} != {COMMIT}"):
        validate_qa_report(
            report_path,
            QaBinding(session_log=SESSION_LOG, commit=COMMIT),
        )


def test_extracts_binding_from_episode_comparison_head() -> None:
    binding = session_qa_binding(
        {
            "episodeMetrics": {"comparison": {"head": COMMIT}},
            "endingCommit": "a" * 10,
        },
        session_log=SESSION_LOG,
        resolve_commit=lambda _commit: COMMIT,
    )

    assert binding == QaBinding(session_log=SESSION_LOG, commit=COMMIT)


def test_extracts_binding_from_full_ending_commit() -> None:
    binding = session_qa_binding(
        {"endingCommit": COMMIT},
        session_log=SESSION_LOG,
    )

    assert binding == QaBinding(session_log=SESSION_LOG, commit=COMMIT)


def test_rejects_disagreement_between_comparison_and_ending_commit() -> None:
    with pytest.raises(ValueError, match="different commits"):
        session_qa_binding(
            {
                "episodeMetrics": {"comparison": {"head": COMMIT}},
                "endingCommit": "b" * 40,
            },
            session_log=SESSION_LOG,
        )


def test_resolves_abbreviated_ending_commit_when_episode_head_is_absent() -> None:
    seen: list[str] = []

    def resolve(commit: str) -> str:
        seen.append(commit)
        return COMMIT

    binding = session_qa_binding(
        {"endingCommit": "a" * 10},
        session_log=SESSION_LOG,
        resolve_commit=resolve,
    )

    assert binding == QaBinding(session_log=SESSION_LOG, commit=COMMIT)
    assert seen == ["a" * 10]


def test_rejects_session_log_without_resolvable_full_commit() -> None:
    with pytest.raises(ValueError, match="full 40-character QA commit"):
        session_qa_binding(
            {"endingCommit": "a" * 10},
            session_log=SESSION_LOG,
            resolve_commit=lambda _commit: None,
        )


def test_rejects_abbreviated_commit_without_resolver() -> None:
    with pytest.raises(ValueError, match="full 40-character QA commit"):
        session_qa_binding(
            {"endingCommit": "a" * 10},
            session_log=SESSION_LOG,
        )


def test_rejects_resolver_output_that_is_not_a_full_commit() -> None:
    with pytest.raises(ValueError, match="full 40-character QA commit"):
        session_qa_binding(
            {"endingCommit": "a" * 10},
            session_log=SESSION_LOG,
            resolve_commit=lambda _commit: "still-short",
        )


def test_filters_session_evidence_from_post_qa_changes() -> None:
    assert non_evidence_paths(
        [
            "",
            ".agents/qa/report.md",
            ".agents/sessions/session.json",
            ".agents/memory/episodes/episode.json",
            "scripts/changed.py",
        ]
    ) == ["scripts/changed.py"]
