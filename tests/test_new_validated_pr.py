"""Tests for new_validated_pr.py PR creation wrapper."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

from scripts.github_core.repo import get_repo_root
from scripts.new_validated_pr import SKILL_RELPATH, _run_web_mode, main

REPO_ROOT = Path(__file__).resolve().parents[1]


def _fake_repo_with_skill(root: Path) -> Path:
    """Create a repo-shaped tree containing the dispatch target."""
    skill = root / SKILL_RELPATH
    skill.parent.mkdir(parents=True, exist_ok=True)
    skill.write_text("")
    return skill


class TestGetRepoRoot:
    @patch("scripts.github_core.repo.subprocess.run")
    def test_returns_path_on_success(self, mock_run: MagicMock) -> None:
        mock_run.return_value = MagicMock(returncode=0, stdout="/fake/repo\n")
        result = get_repo_root()
        assert result == Path("/fake/repo")

    @patch("scripts.github_core.repo.subprocess.run")
    def test_returns_none_on_failure(self, mock_run: MagicMock) -> None:
        mock_run.return_value = MagicMock(returncode=128, stdout="")
        assert get_repo_root() is None


class TestDispatchTargetExists:
    """Reads the real tree instead of a mocked repo root.

    Every other test in this file points the repo root at an empty tmp_path, so
    the dispatch target is missing by construction and exit 2 is the expected
    result. That shape stayed green for the whole time the wrapper pointed at
    New-PR.ps1, which PR #1144 deleted during the PowerShell to Python
    migration. Mocking the filesystem cannot detect a dispatch target that
    stopped existing, so this test does not mock it.
    """

    def test_dispatch_target_exists_in_this_repo(self) -> None:
        target = REPO_ROOT / SKILL_RELPATH
        assert target.is_file(), f"wrapper dispatches to a missing script: {target}"

    def test_dispatch_target_is_the_expected_script(self) -> None:
        """Pin the identity, not just the existence.

        Existence alone is a weak guard: repointing SKILL_RELPATH at any other
        real script in the same directory, say close_pr.py, keeps the existence
        assertion green while the wrapper silently dispatches to the wrong
        command. Restating the literal here is the point rather than a
        duplication smell, because the pair catches both failures: this test
        fails on a wrong target, and the existence test fails on a deleted one.
        """
        assert SKILL_RELPATH == Path(".claude/skills/github/scripts/pr/new_pr.py")

    def test_dispatch_target_is_not_powershell(self) -> None:
        assert SKILL_RELPATH.suffix == ".py", "ADR-042: new scripts are Python"


class TestWebMode:
    """Covers the `--web` branch, which dispatches to gh rather than to a script.

    This path was extracted into _run_web_mode during the complexity refactor
    and had no coverage at the time, so nothing would have caught a mistake in
    the extraction.
    """

    @patch.dict(os.environ, {"CI": "true", "DISPLAY": ":0"}, clear=True)
    def test_refuses_in_ci(self) -> None:
        assert _run_web_mode("main") == 2

    @patch.dict(os.environ, {"GITHUB_ACTIONS": "true", "DISPLAY": ":0"}, clear=True)
    def test_refuses_under_github_actions(self) -> None:
        assert _run_web_mode("main") == 2

    @patch.dict(os.environ, {}, clear=True)
    def test_refuses_when_headless(self) -> None:
        assert _run_web_mode("main") == 2

    @patch("scripts.new_validated_pr.subprocess.run")
    @patch.dict(os.environ, {"DISPLAY": ":0"}, clear=True)
    def test_invokes_gh_with_base(self, mock_run: MagicMock) -> None:
        mock_run.return_value = MagicMock(returncode=0)
        assert _run_web_mode("develop") == 0
        assert mock_run.call_args[0][0] == [
            "gh", "pr", "create", "--web", "--base", "develop",
        ]

    @patch("scripts.new_validated_pr.subprocess.run")
    @patch.dict(os.environ, {"DISPLAY": ":0"}, clear=True)
    def test_omits_base_when_empty(self, mock_run: MagicMock) -> None:
        mock_run.return_value = MagicMock(returncode=0)
        _run_web_mode("")
        assert mock_run.call_args[0][0] == ["gh", "pr", "create", "--web"]

    @patch("scripts.new_validated_pr.subprocess.run")
    @patch.dict(os.environ, {"DISPLAY": ":0"}, clear=True)
    def test_propagates_gh_exit_code(self, mock_run: MagicMock) -> None:
        mock_run.return_value = MagicMock(returncode=7)
        assert _run_web_mode("main") == 7

    @patch("scripts.new_validated_pr.subprocess.run")
    @patch("scripts.new_validated_pr.shutil.which", return_value="/usr/bin/gh")
    @patch("scripts.new_validated_pr.get_repo_root", return_value=Path("/fake"))
    @patch.dict(os.environ, {"DISPLAY": ":0"}, clear=True)
    def test_main_routes_web_without_requiring_a_title(
        self, _repo: MagicMock, _which: MagicMock, mock_run: MagicMock,
    ) -> None:
        mock_run.return_value = MagicMock(returncode=0)
        assert main(["--web"]) == 0
        assert mock_run.call_args[0][0][:4] == ["gh", "pr", "create", "--web"]


class TestMain:
    @patch("scripts.new_validated_pr.get_repo_root", return_value=None)
    def test_exits_2_when_not_git_repo(self, _mock: MagicMock) -> None:
        assert main(["--title", "test"]) == 2

    @patch("scripts.new_validated_pr.shutil.which", return_value=None)
    @patch("scripts.new_validated_pr.get_repo_root", return_value=Path("/repo"))
    def test_exits_2_when_gh_not_found(self, _repo: MagicMock, _which: MagicMock) -> None:
        assert main(["--title", "test"]) == 2

    @patch("scripts.new_validated_pr.shutil.which", return_value="/usr/bin/gh")
    @patch("scripts.new_validated_pr.get_repo_root", return_value=Path("/repo"))
    def test_exits_2_when_no_title(self, _repo: MagicMock, _which: MagicMock) -> None:
        assert main([]) == 2

    @patch("scripts.new_validated_pr.subprocess.run")
    @patch("scripts.new_validated_pr.shutil.which", return_value="/usr/bin/gh")
    @patch("scripts.new_validated_pr.get_repo_root")
    def test_exits_2_when_skill_not_found(
        self, mock_root: MagicMock, _which: MagicMock, _run: MagicMock, tmp_path: Path
    ) -> None:
        mock_root.return_value = tmp_path
        assert main(["--title", "test: title"]) == 2


@patch("scripts.new_validated_pr.shutil.which", return_value="/usr/bin/gh")
@patch("scripts.new_validated_pr.get_repo_root")
class TestDispatch:
    """Success path. None of this was covered before."""

    @staticmethod
    def _run(
        mock_root: MagicMock, tmp_path: Path, argv: list[str], returncode: int = 0
    ) -> tuple[int, list[str]]:
        skill = _fake_repo_with_skill(tmp_path)
        mock_root.return_value = tmp_path
        with patch("scripts.new_validated_pr.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=returncode)
            exit_code = main(argv)
            assert mock_run.call_args is not None
            command = list(mock_run.call_args[0][0])
        assert command[1] == str(skill)
        return exit_code, command

    def test_invokes_the_python_skill_with_the_current_interpreter(
        self, mock_root: MagicMock, _which: MagicMock, tmp_path: Path
    ) -> None:
        exit_code, command = self._run(mock_root, tmp_path, ["--title", "fix: t"])
        assert exit_code == 0
        assert command[0] == sys.executable

    def test_does_not_invoke_powershell(
        self, mock_root: MagicMock, _which: MagicMock, tmp_path: Path
    ) -> None:
        _, command = self._run(mock_root, tmp_path, ["--title", "fix: t"])
        assert "pwsh" not in command
        assert not any(arg.endswith(".ps1") for arg in command)

    def test_passes_title_and_default_base(
        self, mock_root: MagicMock, _which: MagicMock, tmp_path: Path
    ) -> None:
        _, command = self._run(mock_root, tmp_path, ["--title", "fix: t"])
        assert command[command.index("--title") + 1] == "fix: t"
        assert command[command.index("--base") + 1] == "main"

    def test_omits_optional_flags_when_unset(
        self, mock_root: MagicMock, _which: MagicMock, tmp_path: Path
    ) -> None:
        _, command = self._run(mock_root, tmp_path, ["--title", "fix: t"])
        for flag in ("--head", "--body", "--body-file", "--draft", "--skip-validation"):
            assert flag not in command

    def test_forwards_every_optional_flag(
        self, mock_root: MagicMock, _which: MagicMock, tmp_path: Path
    ) -> None:
        _, command = self._run(
            mock_root,
            tmp_path,
            [
                "--title", "fix: t", "--base", "release", "--head", "topic",
                "--body", "text", "--body-file", "b.md", "--draft",
                "--skip-validation", "--audit-reason", "hotfix",
            ],
        )
        assert command[command.index("--base") + 1] == "release"
        assert command[command.index("--head") + 1] == "topic"
        assert command[command.index("--body") + 1] == "text"
        assert command[command.index("--body-file") + 1] == "b.md"
        assert command[command.index("--audit-reason") + 1] == "hotfix"
        assert "--draft" in command
        assert "--skip-validation" in command

    def test_audit_reason_is_dropped_without_skip_validation(
        self, mock_root: MagicMock, _which: MagicMock, tmp_path: Path
    ) -> None:
        _, command = self._run(
            mock_root, tmp_path, ["--title", "fix: t", "--audit-reason", "hotfix"]
        )
        assert "--audit-reason" not in command

    def test_propagates_a_nonzero_exit_code(
        self, mock_root: MagicMock, _which: MagicMock, tmp_path: Path
    ) -> None:
        exit_code, _ = self._run(mock_root, tmp_path, ["--title", "fix: t"], returncode=1)
        assert exit_code == 1
