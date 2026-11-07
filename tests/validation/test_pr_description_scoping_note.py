"""The scoping note tells authors that paths outside a change heading go unchecked (#6506)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from scripts.github_core.api import RepoInfo
from scripts.validation import pr_description
from scripts.validation.pr_description import scoping_note

HEADED = "## Changes\nUpdated `scripts/a.py`.\n"
UNHEADED = "Updated `scripts/a.py` in passing.\n"
NOTE_MARKER = "only paths under it can raise"


def test_note_names_the_narrowing_when_a_change_heading_exists() -> None:
    body = "## Changes\nUpdated `scripts/a.py`.\n\n## Notes\nSee `scripts/b.py`."
    assert "only paths under it can raise" in scoping_note(body)


def test_no_note_without_a_change_heading() -> None:
    assert scoping_note("Updated `scripts/a.py` in passing.") == ""


def test_no_note_for_an_empty_description() -> None:
    assert scoping_note("") == ""


def _run_pr_mode(body: str, capsys: pytest.CaptureFixture[str]) -> str:
    data = {
        "title": "fix: x",
        "body": body,
        "files": [{"path": "scripts/a.py"}],
        "labels": [],
        "base_ref": "main",
        "default_branch": "main",
    }
    with (
        patch.object(pr_description, "fetch_pr_data", return_value=data),
        patch.object(pr_description, "get_repo_info", return_value=RepoInfo(owner="o", repo="r")),
    ):
        pr_description.main(["--pr-number", "1"])
    return capsys.readouterr().out


def _run_local_mode(body: str, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> str:
    body_file = tmp_path / "body.md"
    body_file.write_text(body, encoding="utf-8")
    with patch.object(pr_description, "get_local_diff_files", return_value=["scripts/a.py"]):
        pr_description.run_local(str(body_file), "origin/main")
    return capsys.readouterr().out


def test_pr_mode_prints_the_note_with_a_change_heading(capsys: pytest.CaptureFixture[str]) -> None:
    assert NOTE_MARKER in _run_pr_mode(HEADED, capsys)


def test_pr_mode_prints_no_note_without_a_change_heading(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert NOTE_MARKER not in _run_pr_mode(UNHEADED, capsys)


def test_local_mode_prints_the_note_with_a_change_heading(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert NOTE_MARKER in _run_local_mode(HEADED, tmp_path, capsys)


def test_local_mode_prints_no_note_without_a_change_heading(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert NOTE_MARKER not in _run_local_mode(UNHEADED, tmp_path, capsys)
