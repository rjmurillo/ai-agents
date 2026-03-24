"""Tests for test_workflow_locally.py."""

import json
import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from test_helpers import make_completed_process

# Ensure importability
_project_root = Path(__file__).resolve().parents[3]
_lib_dir = _project_root / ".claude" / "lib"
_scripts_dir = _project_root / ".claude" / "skills" / "github" / "scripts"
for _p in (str(_lib_dir), str(_scripts_dir)):
    if _p not in sys.path:
        sys.path.insert(0, _p)


@pytest.fixture
def _import_module():
    import importlib
    mod_name = "test_workflow_locally"
    if mod_name in sys.modules:
        del sys.modules[mod_name]
    return importlib.import_module(mod_name)


class TestCheckPrerequisites:
    """Tests for prerequisite checking in main()."""

    def test_all_present(self, _import_module, tmp_path):
        mod = _import_module
        wf_dir = tmp_path / ".github" / "workflows"
        wf_dir.mkdir(parents=True)
        (wf_dir / "pester-tests.yml").write_text("on: push")

        def which_side(cmd):
            return f"/usr/bin/{cmd}"

        def fake_run(cmd, **kwargs):
            if cmd[0] == "act" and cmd[1] == "--version":
                return make_completed_process(stdout="act 0.2.0")
            if cmd[0] == "docker":
                return make_completed_process()
            if cmd[0] == "gh":
                return make_completed_process(stdout="token")
            return make_completed_process()

        with (
            patch("shutil.which", side_effect=which_side),
            patch("subprocess.run", side_effect=fake_run),
            patch("test_workflow_locally._get_repo_root", return_value=str(tmp_path)),
        ):
            rc = mod.main(["--workflow", "pester-tests"])
        assert rc == 0

    def test_act_missing(self, _import_module):
        mod = _import_module
        with patch("shutil.which", return_value=None):
            rc = mod.main(["--workflow", "pester-tests"])
        assert rc == 2

    def test_docker_missing(self, _import_module):
        mod = _import_module

        def which_side(name):
            if name == "docker":
                return None
            return f"/usr/bin/{name}"

        with (
            patch("shutil.which", side_effect=which_side),
            patch("subprocess.run", return_value=make_completed_process(stdout="act 0.2.0")),
        ):
            rc = mod.main(["--workflow", "pester-tests"])
        assert rc == 2

    def test_docker_not_running(self, _import_module):
        mod = _import_module

        def which_side(cmd):
            return f"/usr/bin/{cmd}"

        with (
            patch("shutil.which", side_effect=which_side),
            patch("subprocess.run", side_effect=[
                make_completed_process(stdout="act 0.2.0"),  # act --version
                make_completed_process(returncode=1, stderr="Cannot connect"),  # docker info
            ]),
        ):
            rc = mod.main(["--workflow", "pester-tests"])
        assert rc == 2


class TestResolveWorkflowPath:
    """Tests for workflow path resolution in main()."""

    def test_short_name(self, _import_module, tmp_path):
        mod = _import_module
        wf_dir = tmp_path / ".github" / "workflows"
        wf_dir.mkdir(parents=True)
        (wf_dir / "pester-tests.yml").write_text("on: push")

        def which_side(cmd):
            return f"/usr/bin/{cmd}"

        def fake_run(cmd, **kwargs):
            if cmd[0] == "act" and cmd[1] == "--version":
                return make_completed_process(stdout="act 0.2.0")
            if cmd[0] == "docker":
                return make_completed_process()
            if cmd[0] == "gh":
                return make_completed_process(stdout="token")
            return make_completed_process()

        with (
            patch("shutil.which", side_effect=which_side),
            patch("subprocess.run", side_effect=fake_run),
            patch("test_workflow_locally._get_repo_root", return_value=str(tmp_path)),
        ):
            rc = mod.main(["--workflow", "pester-tests"])
        assert rc == 0

    def test_unknown_name(self, _import_module, tmp_path):
        mod = _import_module

        def which_side(cmd):
            return f"/usr/bin/{cmd}"

        with (
            patch("shutil.which", side_effect=which_side),
            patch("subprocess.run", side_effect=[
                make_completed_process(stdout="act 0.2.0"),
                make_completed_process(),
            ]),
            patch("test_workflow_locally._get_repo_root", return_value=str(tmp_path)),
        ):
            rc = mod.main(["--workflow", "nonexistent"])
        assert rc == 1

    def test_yml_extension(self, _import_module, tmp_path):
        mod = _import_module
        wf_dir = tmp_path / ".github" / "workflows"
        wf_dir.mkdir(parents=True)
        (wf_dir / "custom.yml").write_text("on: push")

        def which_side(cmd):
            return f"/usr/bin/{cmd}"

        def fake_run(cmd, **kwargs):
            if cmd[0] == "act" and cmd[1] == "--version":
                return make_completed_process(stdout="act 0.2.0")
            if cmd[0] == "docker":
                return make_completed_process()
            if cmd[0] == "gh":
                return make_completed_process(stdout="token")
            return make_completed_process()

        with (
            patch("shutil.which", side_effect=which_side),
            patch("subprocess.run", side_effect=fake_run),
            patch("test_workflow_locally._get_repo_root", return_value=str(tmp_path)),
        ):
            rc = mod.main(["--workflow", "custom.yml"])
        assert rc == 0


class TestTestWorkflowLocally:
    def test_prerequisites_fail(self, _import_module):
        mod = _import_module
        with patch("shutil.which", return_value=None):
            rc = mod.main(["--workflow", "pester-tests"])
        assert rc == 2

    def test_workflow_not_found(self, _import_module, tmp_path):
        mod = _import_module

        def which_side(cmd):
            return f"/usr/bin/{cmd}"

        with (
            patch("shutil.which", side_effect=which_side),
            patch("subprocess.run", side_effect=[
                make_completed_process(stdout="act 0.2.0"),
                make_completed_process(),
            ]),
            patch("test_workflow_locally._get_repo_root", return_value=str(tmp_path)),
        ):
            rc = mod.main(["--workflow", "nonexistent-workflow"])
        assert rc == 1

    def test_success_execution(self, _import_module, tmp_path):
        mod = _import_module
        wf_dir = tmp_path / ".github" / "workflows"
        wf_dir.mkdir(parents=True)
        (wf_dir / "pester-tests.yml").write_text("on: push")

        def which_side(cmd):
            return f"/usr/bin/{cmd}"

        def fake_run(cmd, **kwargs):
            if cmd[0] == "act" and cmd[1] == "--version":
                return make_completed_process(stdout="act 0.2.0")
            if cmd[0] == "docker":
                return make_completed_process()
            if cmd[0] == "gh":
                return make_completed_process(stdout="token")
            return make_completed_process()

        with (
            patch("shutil.which", side_effect=which_side),
            patch("subprocess.run", side_effect=fake_run),
            patch("test_workflow_locally._get_repo_root", return_value=str(tmp_path)),
        ):
            rc = mod.main(["--workflow", "pester-tests"])
        assert rc == 0
