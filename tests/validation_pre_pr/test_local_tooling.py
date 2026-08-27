"""Local tooling validation tests for pre-PR checks."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest


class TestValidateLefthookInstalled:
    """The local hook gate reads the shared hook shims, not lefthook's checksum.

    ``lefthook check-install`` answers whether the recorded config checksum is
    current, not whether any hook file is usable: measured on lefthook 2.1.10 it
    exits 0 with ``.git/hooks`` deleted outright. The gate now delegates to
    ``scripts/maintenance/install_lefthook_worktree_safe.py --check``, which owns
    the shim contract and reads the files themselves (issue #4789).
    """

    @staticmethod
    def _write_repo(repo_root: Path) -> Path:
        """Create the two files the gate requires: the config and the installer."""
        (repo_root / "lefthook.yml").write_text("pre-commit: {}\n", encoding="utf-8")
        installer = (
            repo_root / "scripts" / "maintenance" / "install_lefthook_worktree_safe.py"
        )
        installer.parent.mkdir(parents=True, exist_ok=True)
        installer.write_text("print('stub')\n", encoding="utf-8")
        return installer

    def test_skipped_under_github_actions(self, tmp_path: Path) -> None:
        from scripts.validation.pre_pr import MissingScriptSkip, validate_lefthook_installed

        with patch.dict("os.environ", {"GITHUB_ACTIONS": "true"}, clear=False):
            with pytest.raises(MissingScriptSkip):
                validate_lefthook_installed(tmp_path)

    def test_skipped_under_ci(self, tmp_path: Path) -> None:
        from scripts.validation.pre_pr import MissingScriptSkip, validate_lefthook_installed

        with patch.dict("os.environ", {"CI": "1", "GITHUB_ACTIONS": "false"}):
            with pytest.raises(MissingScriptSkip):
                validate_lefthook_installed(tmp_path)

    def test_not_skipped_when_ci_is_false(self, tmp_path: Path) -> None:
        from scripts.validation.pre_pr import validate_lefthook_installed

        self._write_repo(tmp_path)
        with patch.dict("os.environ", {"CI": "false", "GITHUB_ACTIONS": "false"}):
            with patch("checks_plugin._run_subprocess", return_value=(0, "OK", "")):
                assert validate_lefthook_installed(tmp_path) is True

    def test_missing_config_fails_closed(self, tmp_path: Path) -> None:
        from scripts.validation.pre_pr import validate_lefthook_installed

        with patch.dict("os.environ", {"CI": "false", "GITHUB_ACTIONS": "false"}):
            assert validate_lefthook_installed(tmp_path) is False

    def test_missing_installer_script_skips(self, tmp_path: Path) -> None:
        from scripts.validation.pre_pr import MissingScriptSkip, validate_lefthook_installed

        installer = self._write_repo(tmp_path)
        installer.unlink()
        with patch.dict("os.environ", {"CI": "false", "GITHUB_ACTIONS": "false"}):
            with patch("checks_plugin._run_subprocess") as mock_run:
                with pytest.raises(MissingScriptSkip):
                    validate_lefthook_installed(tmp_path)

        mock_run.assert_not_called()

    def test_delegates_to_the_shim_installer_in_check_mode(self, tmp_path: Path) -> None:
        from scripts.validation.pre_pr import validate_lefthook_installed

        installer = self._write_repo(tmp_path)
        with patch.dict("os.environ", {"CI": "false", "GITHUB_ACTIONS": "false"}):
            with patch(
                "checks_plugin._run_subprocess", return_value=(0, "OK", "")
            ) as mock_run:
                assert validate_lefthook_installed(tmp_path) is True

        mock_run.assert_called_once_with(
            ["python3", str(installer), "--check", "--repo-root", str(tmp_path)],
            cwd=tmp_path,
        )

    def test_fails_when_the_shim_check_exits_nonzero(
        self, tmp_path: Path, capsys: Any
    ) -> None:
        from scripts.validation.pre_pr import validate_lefthook_installed

        self._write_repo(tmp_path)
        with patch.dict("os.environ", {"CI": "false", "GITHUB_ACTIONS": "false"}):
            with patch(
                "checks_plugin._run_subprocess",
                return_value=(1, "", "[FAIL] pre-commit bakes in an absolute '/.venv/' path"),
            ):
                assert validate_lefthook_installed(tmp_path) is False

        assert "bakes in an absolute '/.venv/' path" in capsys.readouterr().err

    def test_linked_worktree_gets_no_exemption(self, tmp_path: Path) -> None:
        """The #2374 leniency is gone: shared hooks make every checkout the victim."""
        from scripts.validation.pre_pr import validate_lefthook_installed

        self._write_repo(tmp_path)
        with patch.dict("os.environ", {"CI": "false", "GITHUB_ACTIONS": "false"}):
            with patch("checks_plugin._run_subprocess", return_value=(1, "", "diverged")):
                with patch("checks_plugin._is_linked_worktree", return_value=True):
                    assert validate_lefthook_installed(tmp_path) is False


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
