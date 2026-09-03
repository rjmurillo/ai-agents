"""Lefthook and workflow-YAML tests for scripts.validation.pre_pr.

Split from tests/test_validation_pre_pr.py (issue #4352). Covers:
- validate_lefthook_installed
- validate_workflow_yaml
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any
from unittest.mock import call, patch

import pytest

from scripts.validation.pre_pr import (
    validate_workflow_yaml,
)


class TestValidateLefthookInstalled:
    """The local hook gate verifies the configured Lefthook runtime through uv."""

    @staticmethod
    def _write_config(repo_root: Path) -> None:
        (repo_root / "lefthook.yml").write_text("pre-commit: {}\n", encoding="utf-8")

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


class TestValidateWorkflowYaml:
    """Workflow validation raises the shellcheck severity floor to warning (#2374)."""

    def test_returns_true_when_actionlint_missing(self, tmp_path: Path) -> None:
        from scripts.validation.pre_pr import validate_workflow_yaml

        (tmp_path / ".github" / "workflows").mkdir(parents=True)
        with patch("checks_tooling.shutil.which", return_value=None):
            assert validate_workflow_yaml(tmp_path) is True

    def test_returns_true_when_no_workflow_dir(self, tmp_path: Path) -> None:
        from scripts.validation.pre_pr import validate_workflow_yaml

        with patch("checks_tooling.shutil.which", return_value="actionlint"):
            assert validate_workflow_yaml(tmp_path) is True

    def test_passes_shellcheck_severity_warning_env(self, tmp_path: Path) -> None:
        from scripts.validation.pre_pr import validate_workflow_yaml

        wf_dir = tmp_path / ".github" / "workflows"
        wf_dir.mkdir(parents=True)
        (wf_dir / "ci.yml").write_text("name: ci\non: push\n")
        with patch("checks_tooling.shutil.which", return_value="actionlint"):
            with patch("checks_tooling._run_subprocess") as mock_run:
                mock_run.return_value = (0, "", "")
                assert validate_workflow_yaml(tmp_path) is True

            env_kwarg = mock_run.call_args.kwargs["env"]
            assert "--severity=warning" in env_kwarg["SHELLCHECK_OPTS"]

    def test_preserves_existing_shellcheck_opts(self, tmp_path: Path) -> None:

        from scripts.validation.pre_pr import validate_workflow_yaml

        wf_dir = tmp_path / ".github" / "workflows"
        wf_dir.mkdir(parents=True)
        (wf_dir / "ci.yml").write_text("name: ci\non: push\n")
        with patch.dict(os.environ, {"SHELLCHECK_OPTS": "--exclude=SC1091"}, clear=False):
            with patch(
                "checks_tooling.shutil.which", return_value="actionlint"
            ):
                with patch("checks_tooling._run_subprocess") as mock_run:
                    mock_run.return_value = (0, "", "")
                    assert validate_workflow_yaml(tmp_path) is True

                opts = mock_run.call_args.kwargs["env"]["SHELLCHECK_OPTS"]
                assert "--exclude=SC1091" in opts
                assert "--severity=warning" in opts

    def test_fails_when_actionlint_reports_warning(self, tmp_path: Path) -> None:
        from scripts.validation.pre_pr import validate_workflow_yaml

        wf_dir = tmp_path / ".github" / "workflows"
        wf_dir.mkdir(parents=True)
        (wf_dir / "ci.yml").write_text("name: ci\non: push\n")
        with patch("checks_tooling.shutil.which", return_value="actionlint"):
            with patch("checks_tooling._run_subprocess") as mock_run:
                mock_run.return_value = (1, "ci.yml:1:1: SC2034 ... [shellcheck]", "")
                assert validate_workflow_yaml(tmp_path) is False


# ---------------------------------------------------------------------------
# validate_workflow_yaml (actionlint scoping, issue #2346)
# ---------------------------------------------------------------------------


class TestValidateWorkflowYamlScope:
    """actionlint validates workflows only; composite action.yml files under
    .github/actions/ must never be passed to it (issue #2346)."""

    @staticmethod
    def _build_tree(root: Path) -> None:
        workflows = root / ".github" / "workflows"
        workflows.mkdir(parents=True)
        (workflows / "ci.yml").write_text(
            "on: push\njobs:\n  a:\n    runs-on: ubuntu-latest\n    steps: []\n",
            encoding="utf-8",
        )
        actions = root / ".github" / "actions" / "composite"
        actions.mkdir(parents=True)
        # A composite action: actionlint would emit false errors if scanned.
        (actions / "action.yml").write_text(
            "name: composite\nruns:\n  using: composite\n  steps: []\n",
            encoding="utf-8",
        )

    def test_does_not_pass_composite_action_paths(self, tmp_path: Path) -> None:
        self._build_tree(tmp_path)
        with patch("checks_tooling.shutil.which", return_value="/usr/bin/actionlint"):
            with patch("checks_tooling._run_subprocess") as mock_run:
                mock_run.return_value = (0, "", "")
                assert validate_workflow_yaml(tmp_path) is True

        mock_run.assert_called_once()
        command = mock_run.call_args.args[0]
        assert command[0] == "actionlint"
        paths = command[1:]
        # No composite action path is ever handed to actionlint.
        assert all(".github/actions" not in p for p in paths)
        assert not any(p.endswith("action.yml") for p in paths)

    def test_passes_only_workflow_files(self, tmp_path: Path) -> None:
        self._build_tree(tmp_path)
        with patch("checks_tooling.shutil.which", return_value="/usr/bin/actionlint"):
            with patch("checks_tooling._run_subprocess") as mock_run:
                mock_run.return_value = (0, "", "")
                validate_workflow_yaml(tmp_path)

        command = mock_run.call_args.args[0]
        paths = command[1:]
        assert paths, "expected at least one workflow file to be scanned"
        workflows_prefix = str(tmp_path / ".github" / "workflows")
        assert all(p.startswith(workflows_prefix) for p in paths)

    def test_skips_when_actionlint_absent(self, tmp_path: Path) -> None:
        self._build_tree(tmp_path)
        with patch("checks_tooling.shutil.which", return_value=None):
            with patch("checks_tooling._run_subprocess") as mock_run:
                assert validate_workflow_yaml(tmp_path) is True
        mock_run.assert_not_called()
