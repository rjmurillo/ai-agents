"""Lefthook and workflow-YAML tests for scripts.validation.pre_pr.

Split from tests/test_validation_pre_pr.py (issue #4352). Covers:
- validate_lefthook_installed
- validate_workflow_yaml

The ``_is_linked_worktree`` cases went with the helper. Nothing called it once
``validate_lefthook_installed`` stopped downgrading inside a linked worktree
(issue #4789): a shim that names no worktree-specific path is correct for every
checkout, so no checkout needs the exemption the helper existed to grant.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from scripts.validation.pre_pr import (
    validate_workflow_yaml,
)


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
                assert validate_lefthook_installed(tmp_path) is False


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
