"""ADR-073 date drift: dated amendments and Decision edits."""

from pathlib import Path

import pytest

from tests.validation.doc_date_drift_helpers import commit_head, drift, make_repo

ADR = ".project-toolkit/architecture/ADR-101-example.md"


def document(body: str, updated: str = "2026-08-20") -> str:
    return f"---\ntitle: Example\ndate: {updated}\nstatus: accepted\n---\n{body}"


@pytest.mark.parametrize(
    "marker",
    [
        "Amended 2026-10-23: clarify the contract.",
        "## Amendment (2026-10-23)",
        "**Status**: Accepted, amended 2026-10-23.",
    ],
)
def test_added_dated_amendment_flags_old_frontmatter(tmp_path: Path, marker: str) -> None:
    root = make_repo(tmp_path, {ADR: document("## Context\nOriginal.\n")})
    commit_head(root, {ADR: document(f"## Context\nOriginal.\n{marker}\n")})
    findings = [f for f in drift(root) if f.rule == "adr-date"]
    assert len(findings) == 1
    assert findings[0].line == 3
    assert findings[0].other_line == 8
    assert findings[0].suggested == "2026-10-23"


def test_an_older_decision_citation_uses_the_commit_day(tmp_path: Path) -> None:
    root = make_repo(tmp_path, {ADR: document("## Decision\nOld choice.\n")})
    commit_head(root, {ADR: document("## Decision\nRecord the 2024-01-01 choice.\n")})
    (finding,) = [f for f in drift(root) if f.rule == "adr-date"]
    assert finding.suggested == "2026-10-24"
    assert finding.other_line == 7


def test_a_month_only_amendment_uses_the_commit_day(tmp_path: Path) -> None:
    root = make_repo(tmp_path, {ADR: document("## Context\nOriginal.\n")})
    commit_head(root, {ADR: document("## Context\nOriginal.\nAmended November 2026.\n")})
    (finding,) = [f for f in drift(root) if f.rule == "adr-date"]
    assert finding.suggested == "2026-10-24"
    assert finding.line == 3


def test_an_older_context_amendment_does_not_move_the_frontmatter(tmp_path: Path) -> None:
    root = make_repo(tmp_path, {ADR: document("## Context\nOriginal.\n")})
    commit_head(root, {ADR: document("## Context\nOriginal.\nAmended 2024-01-01.\n")})
    assert not [f for f in drift(root) if f.rule == "adr-date"]


def test_a_future_decision_deadline_is_not_the_update_date(tmp_path: Path) -> None:
    root = make_repo(tmp_path, {ADR: document("## Decision\nOld choice.\n", "2026-10-24")})
    commit_head(root, {ADR: document("## Decision\nMigrate by 2027-01-01.\n", "2026-10-24")})
    assert not [f for f in drift(root) if f.rule == "adr-date"]


def test_undated_decision_edit_uses_commit_date(tmp_path: Path) -> None:
    root = make_repo(tmp_path, {ADR: document("## Decision\nOld choice.\n")})
    commit_head(root, {ADR: document("## Decision\nNew choice.\n")})
    (finding,) = [f for f in drift(root) if f.rule == "adr-date"]
    assert finding.suggested == "2026-10-24"
    assert finding.other_line == 7


def test_newest_dated_decision_edit_wins(tmp_path: Path) -> None:
    root = make_repo(tmp_path, {ADR: document("## Decision\nOld choice.\n")})
    commit_head(root, {ADR: document("## Decision\nAmended 2026-10-22.\nAmended 2026-10-23.\n")})
    (finding,) = [f for f in drift(root) if f.rule == "adr-date"]
    assert finding.suggested == "2026-10-23"


@pytest.mark.parametrize(
    "body",
    [
        "## Context\nNew context on 2026-10-23.\n",
        "## Decision\nOld choice.\n## Consequences\nNew consequence.\n",
        "## Context\n```\nAmended 2026-10-23\n```\n",
    ],
)
def test_non_decision_edits_and_fenced_markers_are_clean(tmp_path: Path, body: str) -> None:
    root = make_repo(tmp_path, {ADR: document("## Decision\nOld choice.\n")})
    commit_head(root, {ADR: document(body)})
    assert not [f for f in drift(root) if f.rule == "adr-date"]


def test_updated_frontmatter_is_clean(tmp_path: Path) -> None:
    root = make_repo(tmp_path, {ADR: document("## Decision\nOld choice.\n")})
    commit_head(root, {ADR: document("## Decision\nNew choice.\n", "2026-10-24")})
    assert not [f for f in drift(root) if f.rule == "adr-date"]


def test_unchanged_old_amendment_is_clean(tmp_path: Path) -> None:
    old = "## Context\nAmended 2026-10-23.\nOld context.\n"
    root = make_repo(tmp_path, {ADR: document(old)})
    commit_head(root, {ADR: document(old + "More context.\n")})
    assert not [f for f in drift(root) if f.rule == "adr-date"]


def test_legacy_tracked_architecture_root_is_checked(tmp_path: Path) -> None:
    path = ".agents/architecture/ADR-101-example.md"
    root = make_repo(tmp_path, {path: document("## Decision\nOld choice.\n")})
    commit_head(root, {path: document("## Decision\nNew choice.\n")})
    assert [f.rule for f in drift(root)] == ["adr-date"]


def test_reasoned_exception_is_honored(tmp_path: Path) -> None:
    root = make_repo(tmp_path, {ADR: document("## Decision\nOld choice.\n")})
    text = document("## Decision\nNew choice.\n")
    text = text.replace(
        "date: 2026-08-20", "date: 2026-08-20 # doc-date-drift: ignore -- historical record"
    )
    commit_head(root, {ADR: text})
    assert not [f for f in drift(root) if f.rule == "adr-date"]
