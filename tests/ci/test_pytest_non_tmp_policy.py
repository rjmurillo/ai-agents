#!/usr/bin/env python3
"""Regression tests for the non-/tmp pytest full-suite path."""

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest import mock

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _load_module(name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_non_tmp_runner_rejects_missing_temp_root(monkeypatch, capsys):
    runner = _load_module("run_pytest_non_tmp", PROJECT_ROOT / "scripts/ci/run_pytest_non_tmp.py")
    monkeypatch.delenv("PYTEST_NON_TMP_ROOT", raising=False)

    rc = runner.main([])

    assert rc == 2
    assert (
        "PYTEST_NON_TMP_ROOT must point to a temp root outside the repository"
        in capsys.readouterr().err
    )


def test_non_tmp_runner_rejects_temp_root_inside_repository(monkeypatch, capsys):
    runner = _load_module("run_pytest_non_tmp", PROJECT_ROOT / "scripts/ci/run_pytest_non_tmp.py")
    monkeypatch.setenv("PYTEST_NON_TMP_ROOT", str(PROJECT_ROOT / ".pytest_cache" / "ci-non-tmp"))

    rc = runner.main([])

    assert rc == 2
    assert "must not be inside the repository" in capsys.readouterr().err


def test_non_tmp_runner_invokes_pytest_with_external_temp_roots(monkeypatch, tmp_path):
    runner = _load_module("run_pytest_non_tmp", PROJECT_ROOT / "scripts/ci/run_pytest_non_tmp.py")
    temp_root = tmp_path / "ci-temp"
    monkeypatch.setenv("PYTEST_NON_TMP_ROOT", str(temp_root))

    completed = SimpleNamespace(returncode=0)
    with mock.patch.object(runner.subprocess, "run", return_value=completed) as run:
        rc = runner.main(["tests/test_log_session_end_skip.py", "-q"])

    assert rc == 0
    cmd = run.call_args.args[0]
    env = run.call_args.kwargs["env"]
    assert cmd[:3] == [sys.executable, "-m", "pytest"]
    assert f"--basetemp={temp_root / 'basetemp'}" in cmd
    assert env["TMPDIR"] == str(temp_root / "tmp")
    assert run.call_args.kwargs["cwd"] == runner.PROJECT_ROOT


def test_pytest_configure_exports_basetemp(monkeypatch, tmp_path):
    repo_conftest = _load_module("repo_conftest", PROJECT_ROOT / "conftest.py")
    basetemp = tmp_path / "base"
    monkeypatch.delenv("_PYTEST_BASETEMP", raising=False)

    repo_conftest.pytest_configure(SimpleNamespace(option=SimpleNamespace(basetemp=str(basetemp))))

    assert os.environ["_PYTEST_BASETEMP"] == str(basetemp.resolve())


def test_skip_log_accepts_pytest_basetemp_root(monkeypatch, tmp_path):
    log_module = _load_module(
        "log_session_end_skip",
        PROJECT_ROOT / "scripts/log_session_end_skip.py",
    )
    pytest_basetemp = tmp_path / "pytest-base"
    pytest_basetemp.mkdir()
    other_tmp = tmp_path / "ordinary-tmp"
    other_tmp.mkdir()
    monkeypatch.setenv("_PYTEST_BASETEMP", str(pytest_basetemp))
    monkeypatch.setenv("TMPDIR", str(other_tmp))
    log = pytest_basetemp / "skips.jsonl"

    rc = log_module.main(["--reason", "x", "--log-path", str(log)])

    assert rc == 0
    assert log.exists()


def test_allowed_roots_include_existing_pytest_basetemp(monkeypatch, tmp_path):
    log_module = _load_module(
        "log_session_end_skip",
        PROJECT_ROOT / "scripts/log_session_end_skip.py",
    )
    pytest_basetemp = tmp_path / "pytest-base"
    pytest_basetemp.mkdir()
    monkeypatch.delenv("TMPDIR", raising=False)
    monkeypatch.setenv("_PYTEST_BASETEMP", str(pytest_basetemp))

    roots = log_module._allowed_log_roots(PROJECT_ROOT)

    assert pytest_basetemp.resolve() in roots


def test_workflow_runs_pytest_through_non_tmp_runner():
    workflow_path = PROJECT_ROOT / ".github/workflows/pytest.yml"
    workflow = yaml.safe_load(workflow_path.read_text(encoding="utf-8"))

    run_pytest = next(
        step
        for step in workflow["jobs"]["test"]["steps"]
        if step.get("name") == "Run pytest"
    )

    assert "PYTEST_NON_TMP_ROOT" in run_pytest["env"]
    # Issue #5050 routes the run through the selection runner, which delegates to
    # run_pytest_non_tmp.main, so the temp-root isolation guarantee still holds.
    assert "scripts/ci/run_pytest_selected.py" in run_pytest["run"]
    selected_source = (PROJECT_ROOT / "scripts/ci/run_pytest_selected.py").read_text(
        encoding="utf-8"
    )
    assert "run_pytest_non_tmp" in selected_source
