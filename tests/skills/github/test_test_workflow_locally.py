"""Tests for test_workflow_locally.py."""

import json
import os
from unittest.mock import patch, MagicMock

import pytest

from test_helpers import make_completed_process


@pytest.fixture
def _import_module():
    import importlib
    import sys
    mod_name = "test_workflow_locally"
    if mod_name in sys.modules:
        del sys.modules[mod_name]
    return importlib.import_module(mod_name)


class TestCheckPrerequisites:
    def test_all_present(self, _import_module):
        mod = _import_module
        with (
            patch("shutil.which", return_value="/usr/bin/act"),
            patch("subprocess.run") as mock_run,
        ):
            mock_run.return_value = make_completed_process()
            errors = mod._check_prerequisites()

        assert errors == []

    def test_act_missing(self, _import_module):
        mod = _import_module

        def which_side(name):
            if name == "act":
                return None
            return f"/usr/bin/{name}"

        with (
            patch("shutil.which", side_effect=which_side),
            patch("subprocess.run") as mock_run,
        ):
            mock_run.return_value = make_completed_process()
            errors = mod._check_prerequisites()

        assert any("act" in e for e in errors)

    def test_docker_missing(self, _import_module):
        mod = _import_module

        def which_side(name):
            if name == "docker":
                return None
            return f"/usr/bin/{name}"

        with patch("shutil.which", side_effect=which_side):
            errors = mod._check_prerequisites()

        assert any("Docker" in e for e in errors)

    def test_docker_not_running(self, _import_module):
        mod = _import_module
        with (
            patch("shutil.which", return_value="/usr/bin/tool"),
            patch("subprocess.run") as mock_run,
        ):
            mock_run.return_value = make_completed_process(
                returncode=1, stderr="Cannot connect"
            )
            errors = mod._check_prerequisites()

        assert any("running" in e.lower() for e in errors)


class TestResolveWorkflowPath:
    def test_short_name(self, _import_module, tmp_path):
        mod = _import_module
        wf_dir = tmp_path / ".github" / "workflows"
        wf_dir.mkdir(parents=True)
        (wf_dir / "pester-tests.yml").write_text("on: push")

        result = mod._resolve_workflow_path("pester-tests", str(tmp_path))
        assert result is not None
        assert result.endswith("pester-tests.yml")

    def test_unknown_name(self, _import_module, tmp_path):
        mod = _import_module
        result = mod._resolve_workflow_path("nonexistent", str(tmp_path))
        assert result is None

    def test_yml_extension(self, _import_module, tmp_path):
        mod = _import_module
        wf_dir = tmp_path / ".github" / "workflows"
        wf_dir.mkdir(parents=True)
        (wf_dir / "custom.yml").write_text("on: push")

        result = mod._resolve_workflow_path("custom.yml", str(tmp_path))
        assert result is not None


class TestTestWorkflowLocally:
    def test_prerequisites_fail(self, _import_module):
        mod = _import_module
        with patch.object(
            mod, "_check_prerequisites",
            return_value=["act not found"],
        ):
            result = mod.test_workflow_locally("pester-tests")

        assert result["Success"] is False
        assert result["ExitCode"] == 2

    def test_workflow_not_found(self, _import_module):
        mod = _import_module
        with (
            patch.object(mod, "_check_prerequisites", return_value=[]),
            patch("subprocess.run") as mock_run,
        ):
            mock_run.return_value = make_completed_process(
                stdout="/tmp/repo"
            )
            result = mod.test_workflow_locally("nonexistent-workflow")

        assert result["Success"] is False
        assert result["ExitCode"] == 1

    def test_success_execution(self, _import_module, tmp_path):
        mod = _import_module
        wf_dir = tmp_path / ".github" / "workflows"
        wf_dir.mkdir(parents=True)
        (wf_dir / "pester-tests.yml").write_text("on: push")

        call_count = [0]

        def run_side(cmd, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                return make_completed_process(stdout=str(tmp_path))
            return make_completed_process()

        with (
            patch.object(mod, "_check_prerequisites", return_value=[]),
            patch("subprocess.run", side_effect=run_side),
        ):
            result = mod.test_workflow_locally("pester-tests")

        assert result["Success"] is True
        assert result["ExitCode"] == 0
