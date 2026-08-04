"""Local tooling validation tests for pre-PR checks."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import call, patch


class TestValidateLefthookInstalled:
    """The local hook gate delegates to Lefthook through uv."""

    @staticmethod
    def _write_config(repo_root: Path) -> None:
        (repo_root / "lefthook.yml").write_text("pre-commit: {}\n", encoding="utf-8")

    def test_skipped_under_github_actions(self, tmp_path: Path) -> None:
        import pytest

        from scripts.validation.pre_pr import MissingScriptSkip, validate_lefthook_installed

        with patch.dict("os.environ", {"GITHUB_ACTIONS": "true"}, clear=False):
            with pytest.raises(MissingScriptSkip):
                validate_lefthook_installed(tmp_path)

    def test_skipped_under_ci(self, tmp_path: Path) -> None:
        import pytest

        from scripts.validation.pre_pr import MissingScriptSkip, validate_lefthook_installed

        with patch.dict("os.environ", {"CI": "1", "GITHUB_ACTIONS": "false"}):
            with pytest.raises(MissingScriptSkip):
                validate_lefthook_installed(tmp_path)

    def test_not_skipped_when_ci_is_false(self, tmp_path: Path) -> None:
        from scripts.validation.pre_pr import validate_lefthook_installed

        self._write_config(tmp_path)
        with patch.dict("os.environ", {"CI": "false", "GITHUB_ACTIONS": "false"}):
            with patch("checks_plugin.shutil.which", return_value="/bin/uv"):
                with patch("checks_plugin._run_subprocess", return_value=(0, "OK", "")):
                    assert validate_lefthook_installed(tmp_path) is True

    def test_missing_config_fails_closed(self, tmp_path: Path) -> None:
        from scripts.validation.pre_pr import validate_lefthook_installed

        with patch.dict("os.environ", {"CI": "false", "GITHUB_ACTIONS": "false"}):
            assert validate_lefthook_installed(tmp_path) is False

    def test_missing_uv_fails_closed(self, tmp_path: Path, capsys: Any) -> None:
        from scripts.validation.pre_pr import validate_lefthook_installed

        self._write_config(tmp_path)
        with patch.dict("os.environ", {"CI": "false", "GITHUB_ACTIONS": "false"}):
            with patch("checks_plugin.shutil.which", return_value=None):
                assert validate_lefthook_installed(tmp_path) is False

        output = capsys.readouterr()
        assert "uv is unavailable" in output.err
        assert "Lefthook jobs run through uv" in output.err

    def test_direct_lefthook_does_not_bypass_missing_uv(self, tmp_path: Path) -> None:
        from scripts.validation.pre_pr import validate_lefthook_installed

        self._write_config(tmp_path)

        def locate_tool(tool: str) -> str | None:
            return None if tool == "uv" else "/bin/lefthook"

        with patch.dict("os.environ", {"CI": "false", "GITHUB_ACTIONS": "false"}):
            with patch(
                "checks_plugin.shutil.which", side_effect=locate_tool
            ) as mock_which:
                with patch("checks_plugin._run_subprocess") as mock_run:
                    assert validate_lefthook_installed(tmp_path) is False

        assert mock_which.call_args_list == [call("uv")]
        mock_run.assert_not_called()

    def test_uses_uv_to_match_configured_hook_runtime(self, tmp_path: Path) -> None:
        from scripts.validation.pre_pr import validate_lefthook_installed

        self._write_config(tmp_path)
        with patch.dict("os.environ", {"CI": "false", "GITHUB_ACTIONS": "false"}):
            with patch("checks_plugin.shutil.which", return_value="/bin/uv") as mock_which:
                with patch(
                    "checks_plugin._run_subprocess", return_value=(0, "OK", "")
                ) as mock_run:
                    assert validate_lefthook_installed(tmp_path) is True

        assert mock_which.call_args_list == [call("uv")]
        mock_run.assert_called_once_with(
            ["/bin/uv", "run", "--frozen", "lefthook", "check-install"],
            cwd=tmp_path,
        )

    def test_passes_when_check_install_exits_zero(self, tmp_path: Path) -> None:
        from scripts.validation.pre_pr import validate_lefthook_installed

        self._write_config(tmp_path)
        with patch.dict("os.environ", {"CI": "false", "GITHUB_ACTIONS": "false"}):
            with patch("checks_plugin.shutil.which", return_value="/bin/uv"):
                with patch("checks_plugin._run_subprocess") as mock_run:
                    mock_run.return_value = (0, "OK", "")
                    assert validate_lefthook_installed(tmp_path) is True
        mock_run.assert_called_once_with(
            ["/bin/uv", "run", "--frozen", "lefthook", "check-install"],
            cwd=tmp_path,
        )

    def test_fails_when_check_install_exits_nonzero(
        self, tmp_path: Path, capsys: Any
    ) -> None:
        from scripts.validation.pre_pr import validate_lefthook_installed

        self._write_config(tmp_path)
        with patch.dict("os.environ", {"CI": "false", "GITHUB_ACTIONS": "false"}):
            with patch("checks_plugin.shutil.which", return_value="/bin/uv"):
                with patch("checks_plugin._run_subprocess", return_value=(1, "", "missing")):
                    with patch("checks_plugin._is_linked_worktree", return_value=False):
                        assert validate_lefthook_installed(tmp_path) is False

        output = capsys.readouterr()
        assert (
            "uv run --frozen lefthook install --reset-hooks-path" in output.out
        )
        assert "uv run --frozen lefthook check-install" in output.out

    def test_warns_not_fails_in_linked_worktree(
        self, tmp_path: Path, capsys: Any
    ) -> None:
        from scripts.validation.pre_pr import validate_lefthook_installed

        self._write_config(tmp_path)
        with patch.dict("os.environ", {"CI": "false", "GITHUB_ACTIONS": "false"}):
            with patch("checks_plugin.shutil.which", return_value="/bin/uv"):
                with patch("checks_plugin._run_subprocess", return_value=(1, "", "missing")):
                    with patch("checks_plugin._is_linked_worktree", return_value=True):
                        assert validate_lefthook_installed(tmp_path) is True

        output = capsys.readouterr()
        assert (
            "uv run --frozen lefthook install --reset-hooks-path" in output.out
        )
        assert "uv run --frozen lefthook check-install" in output.out


class TestIsLinkedWorktree:
    """The git-hooks gate downgrades to a warning in a linked worktree (#2374)."""

    def test_true_when_git_dir_differs_from_common_dir(self, tmp_path: Path) -> None:
        from scripts.validation.pre_pr import _is_linked_worktree

        with patch("checks_plugin.shutil.which", return_value="git"):
            with patch("checks_plugin._run_subprocess") as mock_run:
                mock_run.return_value = (
                    0,
                    "/repo/.git/worktrees/wt\n/repo/.git\n",
                    "",
                )
                assert _is_linked_worktree(tmp_path) is True

    def test_false_when_git_dir_equals_common_dir(self, tmp_path: Path) -> None:
        from scripts.validation.pre_pr import _is_linked_worktree

        with patch("checks_plugin.shutil.which", return_value="git"):
            with patch("checks_plugin._run_subprocess") as mock_run:
                mock_run.return_value = (0, "/repo/.git\n/repo/.git\n", "")
                assert _is_linked_worktree(tmp_path) is False

    def test_false_when_git_missing(self, tmp_path: Path) -> None:
        from scripts.validation.pre_pr import _is_linked_worktree

        with patch("checks_plugin.shutil.which", return_value=None):
            assert _is_linked_worktree(tmp_path) is False

    def test_false_when_rev_parse_fails(self, tmp_path: Path) -> None:
        from scripts.validation.pre_pr import _is_linked_worktree

        with patch("checks_plugin.shutil.which", return_value="git"):
            with patch("checks_plugin._run_subprocess") as mock_run:
                mock_run.return_value = (128, "", "fatal: not a git repository")
                assert _is_linked_worktree(tmp_path) is False

    def test_false_when_output_malformed(self, tmp_path: Path) -> None:
        from scripts.validation.pre_pr import _is_linked_worktree

        with patch("checks_plugin.shutil.which", return_value="git"):
            with patch("checks_plugin._run_subprocess") as mock_run:
                mock_run.return_value = (0, "only-one-line\n", "")
                assert _is_linked_worktree(tmp_path) is False

    def test_relative_paths_are_anchored_to_repo_root(
        self, tmp_path: Path, monkeypatch: Any
    ) -> None:
        from scripts.validation.pre_pr import _is_linked_worktree

        repo = tmp_path / "repo"
        repo.mkdir()
        common = repo / "common"
        common.mkdir()
        (repo / ".git").symlink_to(common, target_is_directory=True)
        outside = tmp_path / "outside"
        outside.mkdir()
        (outside / ".git").mkdir()
        monkeypatch.chdir(outside)

        with patch("checks_plugin.shutil.which", return_value="git"):
            with patch("checks_plugin._run_subprocess") as mock_run:
                mock_run.return_value = (0, ".git\ncommon\n", "")
                assert _is_linked_worktree(repo) is False

        command = mock_run.call_args.args[0]
        assert "--path-format=absolute" not in command
