"""Local tooling validation tests for pre-PR checks."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import call, patch


class TestValidateLefthookInstalled:
    """The local hook gate verifies the configured Lefthook runtime through uv."""

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
            ["/bin/uv", "run", "--frozen", "lefthook", "version"],
            cwd=tmp_path,
        )

    def test_passes_when_the_runtime_starts(self, tmp_path: Path) -> None:
        from scripts.validation.pre_pr import validate_lefthook_installed

        self._write_config(tmp_path)
        with patch.dict("os.environ", {"CI": "false", "GITHUB_ACTIONS": "false"}):
            with patch("checks_plugin.shutil.which", return_value="/bin/uv"):
                with patch("checks_plugin._run_subprocess") as mock_run:
                    mock_run.return_value = (0, "OK", "")
                    assert validate_lefthook_installed(tmp_path) is True
        mock_run.assert_called_once_with(
            ["/bin/uv", "run", "--frozen", "lefthook", "version"],
            cwd=tmp_path,
        )

    def test_fails_when_the_runtime_cannot_start(
        self, tmp_path: Path, capsys: Any
    ) -> None:
        from scripts.validation.pre_pr import validate_lefthook_installed

        self._write_config(tmp_path)
        with patch.dict("os.environ", {"CI": "false", "GITHUB_ACTIONS": "false"}):
            with patch("checks_plugin.shutil.which", return_value="/bin/uv"):
                with patch("checks_plugin._run_subprocess", return_value=(1, "", "missing")):
                    assert validate_lefthook_installed(tmp_path) is False

        output = capsys.readouterr()
        assert "Lefthook runtime is unavailable" in output.out
        assert "uv sync --frozen --extra dev" in output.out
