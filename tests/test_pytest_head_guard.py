"""Tests for the repository-wide pytest HEAD guard."""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path


def _load_root_conftest():
    path = Path(__file__).resolve().parents[1] / "conftest.py"
    spec = importlib.util.spec_from_file_location("root_conftest_under_test", path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["root_conftest_under_test"] = module
    spec.loader.exec_module(module)
    return module


def test_real_repo_head_unsets_git_environment_overrides(monkeypatch):
    module = _load_root_conftest()
    captured: dict[str, dict[str, str]] = {}

    monkeypatch.setenv("GIT_DIR", "wrong")
    monkeypatch.setenv("GIT_WORK_TREE", "wrong")
    monkeypatch.setenv("GIT_INDEX_FILE", "wrong")
    monkeypatch.setenv("GIT_COMMON_DIR", "wrong")
    monkeypatch.setenv("GIT_AUTHOR_NAME", "kept")

    def fake_run(*_args, **kwargs):
        captured["env"] = kwargs["env"]
        return subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout="abc123\n",
            stderr="",
        )

    monkeypatch.setattr(module.subprocess, "run", fake_run)

    assert module._real_repo_head() == "abc123"
    assert captured["env"]["GIT_AUTHOR_NAME"] == "kept"
    for key in module._GIT_ENV_OVERRIDES:
        assert key not in captured["env"]
