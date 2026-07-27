"""Tests for active execution plan closeout warnings."""

from __future__ import annotations

from pathlib import Path

from scripts.validation.active_plan_closeout import (
    active_plan_warnings,
    issue_refs,
    validate_active_plan_closeout,
)


def write_active_plan(repo_root: Path, name: str, body: str) -> Path:
    """Create an active plan fixture."""
    path = repo_root / ".agents" / "plans" / "active" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    return path


def test_warns_when_every_tracking_issue_is_closed(tmp_path: Path) -> None:
    write_active_plan(
        tmp_path,
        "closed.md",
        "# Plan\n\nRelated: #101 and https://github.com/rjmurillo/ai-agents/issues/102\n",
    )

    warnings = active_plan_warnings(
        tmp_path,
        issue_state_lookup=lambda issue: "CLOSED",
    )

    assert [warning.format() for warning in warnings] == [
        ".agents/plans/active/closed.md: #101, #102 closed. Move the plan to "
        "completed/ or abandoned/."
    ]


def test_does_not_warn_when_any_tracking_issue_is_open(tmp_path: Path) -> None:
    write_active_plan(tmp_path, "mixed.md", "# Plan\n\nRelated: #101 and #102\n")

    warnings = active_plan_warnings(
        tmp_path,
        issue_state_lookup=lambda issue: "OPEN" if issue == 102 else "CLOSED",
    )

    assert warnings == []


def test_missing_or_unknown_tracking_issue_does_not_warn(tmp_path: Path) -> None:
    write_active_plan(tmp_path, "unknown.md", "# Plan\n\nRelated: #101\n")
    write_active_plan(tmp_path, "no-refs.md", "# Plan\n\nNo issue link yet.\n")

    warnings = active_plan_warnings(
        tmp_path,
        issue_state_lookup=lambda issue: None,
    )

    assert warnings == []


def test_issue_refs_are_unique_and_sorted() -> None:
    markdown = "Related: #3, #2, #3 and https://github.com/a/b/issues/1"

    assert issue_refs(markdown) == (1, 2, 3)


def test_validator_is_advisory_when_warning_exists(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    write_active_plan(tmp_path, "closed.md", "# Plan\n\nRelated: #101\n")
    monkeypatch.setattr(
        "scripts.validation.active_plan_closeout.gh_issue_state",
        lambda issue, repo: "CLOSED",
    )

    assert validate_active_plan_closeout(tmp_path) is True

    captured = capsys.readouterr()
    assert "[WARNING] Active execution plans have closed tracking issues:" in captured.out
    assert ".agents/plans/active/closed.md: #101 closed." in captured.out
