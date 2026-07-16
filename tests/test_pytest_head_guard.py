"""Tests for the repository-wide pytest HEAD guard."""

from __future__ import annotations

import importlib.util
import subprocess
import sys
import warnings
from pathlib import Path

import pytest


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


def _silence_subject(module, monkeypatch):
    """Stub the commit-subject read so warn-path tests do not shell out to git."""
    monkeypatch.setattr(module, "_real_repo_head_subject", lambda: "concurrent work")


def test_check_head_change_is_silent_when_head_is_unchanged(monkeypatch):
    module = _load_root_conftest()
    _silence_subject(module, monkeypatch)

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        module._check_head_change("aaaaaaaa1111", "aaaaaaaa1111")

    assert caught == []


def test_check_head_change_warns_without_blaming_on_concurrent_commit(monkeypatch):
    module = _load_root_conftest()
    _silence_subject(module, monkeypatch)

    with pytest.warns(UserWarning) as record:
        module._check_head_change("aaaaaaaa1111", "bbbbbbbb2222")

    message = str(record[0].message)
    assert "#3109" in message
    assert "aaaaaaaa" in message
    assert "bbbbbbbb" in message
    # The guard names the concurrent commit as the likely cause, never accuses.
    assert "concurrent external commit" in message
    assert "mutated the REAL repo" not in message


def test_check_head_change_warns_when_post_head_is_unreadable(monkeypatch):
    module = _load_root_conftest()
    _silence_subject(module, monkeypatch)

    with pytest.warns(UserWarning) as record:
        module._check_head_change("aaaaaaaa1111", None)

    assert "None (unreadable during concurrent git)" in str(record[0].message)


def test_check_head_change_is_silent_when_baseline_is_unreadable(monkeypatch):
    module = _load_root_conftest()
    _silence_subject(module, monkeypatch)

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        module._check_head_change(None, "bbbbbbbb2222")

    assert caught == []


def test_guard_fixture_does_not_blame_test_for_external_commit(monkeypatch):
    """Reproduces #3109: HEAD moves during the test window; the test never ran git.

    Drives the real autouse fixture generator with a head-reader that returns a
    different SHA at teardown than at setup. The guard must warn, not fail.
    """
    module = _load_root_conftest()
    _silence_subject(module, monkeypatch)

    heads = iter(["aaaaaaaa1111", "bbbbbbbb2222"])
    monkeypatch.setattr(module, "_real_repo_head", lambda: next(heads))

    generator = module._guard_real_repo_head.__wrapped__()
    next(generator)  # fixture setup: captures the per-test baseline

    with pytest.warns(UserWarning, match="#3109"):
        with pytest.raises(StopIteration):
            next(generator)  # fixture teardown: reads the moved HEAD, warns
