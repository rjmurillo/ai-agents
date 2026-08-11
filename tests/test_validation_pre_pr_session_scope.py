"""Pre-PR session scope regression tests."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import patch

from scripts.validation.pre_pr import validate_session_end


def _write_validator(repo_root: Path) -> None:
    scripts = repo_root / "scripts"
    scripts.mkdir()
    (scripts / "validate_session_json.py").write_text("", encoding="utf-8")


def test_session_newness_is_computed_from_head(tmp_path: Path) -> None:
    sessions = tmp_path / ".agents" / "sessions"
    sessions.mkdir(parents=True)
    path = ".agents/sessions/2025-12-01-session-1.json"
    (tmp_path / path).write_text("{}", encoding="utf-8")
    _write_validator(tmp_path)

    def fake_run(command: list[str], **_kwargs: Any) -> tuple[int, str, str]:
        if "diff" in command:
            return 0, f"{path}\0", ""
        if "rev-parse" in command:
            return 0, f"{'c' * 40}\n", ""
        return 0, "", ""

    with patch(
        "checks_tooling._resolve_branch_base_ref",
        return_value="origin/main",
    ), patch("checks_tooling._run_subprocess", side_effect=fake_run), patch(
        "checks_tooling.new_session_logs",
        return_value=set(),
    ) as new_session_logs_mock:
        assert validate_session_end(tmp_path) is True

    new_session_logs_mock.assert_called_once_with(
        [path],
        tmp_path,
        compare_ref="HEAD",
    )


def test_missing_worktree_copy_of_branch_session_fails_closed(
    tmp_path: Path,
) -> None:
    _write_validator(tmp_path)
    path = ".agents/sessions/2025-12-01-session-1.json"
    seen: list[list[str]] = []

    def fake_run(command: list[str], **_kwargs: Any) -> tuple[int, str, str]:
        seen.append(command)
        if "diff" in command:
            return 0, f"{path}\0", ""
        if "rev-parse" in command:
            return 0, f"{'c' * 40}\n", ""
        return 1, "", "session log does not exist"

    with patch(
        "checks_tooling._resolve_branch_base_ref",
        return_value="origin/main",
    ), patch("checks_tooling._run_subprocess", side_effect=fake_run), patch(
        "checks_tooling.new_session_logs",
        return_value={path},
    ):
        assert validate_session_end(tmp_path) is False

    assert seen[-1][1].endswith("validate_session_json.py")
    assert seen[-1][-2:] == ["--validation-head", "c" * 40]
