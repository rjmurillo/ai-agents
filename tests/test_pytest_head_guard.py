"""Tests for the repository-wide pytest HEAD guard."""

from __future__ import annotations

import importlib.util
import json
import os
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
        captured["kwargs"] = kwargs
        return subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout="abc123\n",
            stderr="",
        )

    monkeypatch.setattr(module.subprocess, "run", fake_run)

    assert module._real_repo_head() == "abc123"
    kwargs = captured["kwargs"]
    assert kwargs["env"]["GIT_AUTHOR_NAME"] == "kept"
    for key in module._GIT_ENV_OVERRIDES:
        assert key not in kwargs["env"]
    assert kwargs["encoding"] == "utf-8"
    assert kwargs["errors"] == "replace"
    assert "text" not in kwargs


def test_real_repo_head_subject_decodes_git_output_as_utf8(monkeypatch):
    module = _load_root_conftest()
    captured: dict[str, object] = {}

    def fake_run(*_args, **kwargs):
        captured["kwargs"] = kwargs
        return subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout="subject\n",
            stderr="",
        )

    monkeypatch.setattr(module.subprocess, "run", fake_run)

    assert module._real_repo_head_subject() == "subject"
    kwargs = captured["kwargs"]
    assert kwargs["encoding"] == "utf-8"
    assert kwargs["errors"] == "replace"
    assert "text" not in kwargs


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


def test_check_head_change_fails_when_post_head_is_unreadable(monkeypatch):
    module = _load_root_conftest()
    _silence_subject(module, monkeypatch)

    with pytest.raises(pytest.fail.Exception, match="could not read repository HEAD"):
        module._check_head_change("aaaaaaaa1111", None)


def test_check_head_change_is_silent_when_baseline_is_unreadable(monkeypatch):
    module = _load_root_conftest()
    _silence_subject(module, monkeypatch)

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        module._check_head_change(None, "bbbbbbbb2222")

    assert caught == []


def _write_git_trace(path: Path, command: str, worktree: Path) -> None:
    events = (
        {"event": "cmd_name", "sid": "test-session", "name": command},
        {
            "event": "def_repo",
            "sid": "test-session",
            "repo": 1,
            "worktree": str(worktree),
        },
    )
    path.write_text(
        "".join(f"{json.dumps(event)}\n" for event in events),
        encoding="utf-8",
    )


def test_trace_identifies_mutating_git_command_in_project(tmp_path):
    module = _load_root_conftest()
    trace_path = tmp_path / "git-trace.json"
    _write_git_trace(trace_path, "commit", module.PROJECT_ROOT)

    assert module._trace_has_project_head_mutation(trace_path)


def test_trace_ignores_read_only_git_command_in_project(tmp_path):
    module = _load_root_conftest()
    trace_path = tmp_path / "git-trace.json"
    _write_git_trace(trace_path, "status", module.PROJECT_ROOT)

    assert not module._trace_has_project_head_mutation(trace_path)


def test_trace_ignores_mutating_git_command_in_other_worktree(tmp_path):
    module = _load_root_conftest()
    trace_path = tmp_path / "git-trace.json"
    _write_git_trace(trace_path, "commit", tmp_path / "isolated-repo")

    assert not module._trace_has_project_head_mutation(trace_path)


def test_check_head_change_fails_for_test_launched_mutation(tmp_path):
    module = _load_root_conftest()
    trace_path = tmp_path / "git-trace.json"
    _write_git_trace(trace_path, "commit", module.PROJECT_ROOT)

    with pytest.raises(pytest.fail.Exception, match="test-launched Git command"):
        module._check_head_change("aaaaaaaa1111", "bbbbbbbb2222", trace_path)


def test_check_head_change_warns_for_external_concurrent_commit(tmp_path, monkeypatch):
    module = _load_root_conftest()
    _silence_subject(module, monkeypatch)
    trace_path = tmp_path / "git-trace.json"

    with pytest.warns(UserWarning, match="concurrent external commit"):
        module._check_head_change("aaaaaaaa1111", "bbbbbbbb2222", trace_path)


def test_check_head_change_fails_when_trace_is_malformed(tmp_path):
    module = _load_root_conftest()
    trace_path = tmp_path / "git-trace.json"
    trace_path.write_text("not-json\n", encoding="utf-8")

    with pytest.raises(pytest.fail.Exception, match="could not attribute"):
        module._check_head_change("aaaaaaaa1111", "bbbbbbbb2222", trace_path)


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


def test_guard_fixture_fails_for_test_launched_mutation(monkeypatch):
    module = _load_root_conftest()
    heads = iter(["aaaaaaaa1111", "bbbbbbbb2222"])
    monkeypatch.setattr(module, "_real_repo_head", lambda: next(heads))

    generator = module._guard_real_repo_head.__wrapped__()
    next(generator)
    trace_path = Path(os.environ["GIT_TRACE2_EVENT"])
    _write_git_trace(trace_path, "commit", module.PROJECT_ROOT)

    with pytest.raises(pytest.fail.Exception, match="test-launched Git command"):
        next(generator)


def test_guard_fixture_restores_existing_trace_setting(monkeypatch):
    module = _load_root_conftest()
    heads = iter(["aaaaaaaa1111", "aaaaaaaa1111"])
    monkeypatch.setattr(module, "_real_repo_head", lambda: next(heads))
    monkeypatch.setenv("GIT_TRACE2_EVENT", "caller-trace.json")

    generator = module._guard_real_repo_head.__wrapped__()
    next(generator)

    assert os.environ["GIT_TRACE2_EVENT"] != "caller-trace.json"
    with pytest.raises(StopIteration):
        next(generator)
    assert os.environ["GIT_TRACE2_EVENT"] == "caller-trace.json"
