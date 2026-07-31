"""Tests for the memory hook virtualenv re-exec (issue #4011).

settings.json registers the memory hooks as `python3 -u ...`. That interpreter
usually cannot import python-frontmatter, so the recall and reflection hooks
exited 0 having done nothing. The re-exec resolves the dependency without
changing the registration.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from memory_enhancement.interpreter import (
    REENTRY_GUARD,
    dependency_available,
    find_venv_interpreter,
    reexec_under_project_venv,
)


def _make_venv(project_dir: Path, name: str = "bin/python3") -> Path:
    interpreter = project_dir / ".venv" / name
    interpreter.parent.mkdir(parents=True, exist_ok=True)
    interpreter.write_text("#!/bin/sh\n", encoding="utf-8")
    return interpreter


class TestDependencyAvailable:
    """The probe answers for the running interpreter, not for a path."""

    @pytest.mark.unit
    def test_reports_true_for_a_stdlib_module(self):
        assert dependency_available("json") is True

    @pytest.mark.unit
    def test_reports_false_for_a_missing_module(self):
        assert dependency_available("definitely_not_installed_xyz") is False


class TestFindVenvInterpreter:
    """Locating .venv is what separates a repo checkout from a plugin install."""

    @pytest.mark.unit
    def test_finds_the_posix_interpreter(self, tmp_path):
        expected = _make_venv(tmp_path)

        assert find_venv_interpreter(tmp_path) == expected

    @pytest.mark.unit
    def test_finds_the_windows_interpreter(self, tmp_path):
        expected = _make_venv(tmp_path, "Scripts/python.exe")

        assert find_venv_interpreter(tmp_path) == expected

    @pytest.mark.unit
    def test_returns_none_without_a_venv(self, tmp_path):
        assert find_venv_interpreter(tmp_path) is None

    @pytest.mark.unit
    def test_returns_none_when_venv_is_a_directory_not_a_file(self, tmp_path):
        (tmp_path / ".venv" / "bin" / "python3").mkdir(parents=True)

        assert find_venv_interpreter(tmp_path) is None


class TestReexecUnderProjectVenv:
    """Every branch either execs once or returns, never both and never twice."""

    @staticmethod
    def _record_execv(monkeypatch) -> list[tuple[str, list[str]]]:
        calls: list[tuple[str, list[str]]] = []
        monkeypatch.setattr(
            "memory_enhancement.interpreter.os.execv",
            lambda path, args: calls.append((path, args)),
        )
        return calls

    @pytest.mark.unit
    def test_execs_the_venv_interpreter_when_the_dependency_is_missing(
        self, tmp_path, monkeypatch
    ):
        interpreter = _make_venv(tmp_path)
        monkeypatch.delenv(REENTRY_GUARD, raising=False)
        monkeypatch.setattr(
            "memory_enhancement.interpreter.dependency_available", lambda: False
        )
        calls = self._record_execv(monkeypatch)

        reexec_under_project_venv(tmp_path, ["hook.py"])

        assert calls == [(str(interpreter), [str(interpreter), "-u", "hook.py"])]

    @pytest.mark.unit
    def test_sets_the_guard_so_the_child_cannot_loop(self, tmp_path, monkeypatch):
        _make_venv(tmp_path)
        monkeypatch.delenv(REENTRY_GUARD, raising=False)
        monkeypatch.setattr(
            "memory_enhancement.interpreter.dependency_available", lambda: False
        )
        self._record_execv(monkeypatch)

        reexec_under_project_venv(tmp_path, ["hook.py"])

        import os

        assert os.environ[REENTRY_GUARD] == "1"

    @pytest.mark.unit
    def test_does_nothing_when_the_dependency_imports(self, tmp_path, monkeypatch):
        _make_venv(tmp_path)
        monkeypatch.delenv(REENTRY_GUARD, raising=False)
        monkeypatch.setattr(
            "memory_enhancement.interpreter.dependency_available", lambda: True
        )
        calls = self._record_execv(monkeypatch)

        reexec_under_project_venv(tmp_path, ["hook.py"])

        assert calls == []

    @pytest.mark.unit
    def test_does_nothing_when_the_guard_is_already_set(self, tmp_path, monkeypatch):
        _make_venv(tmp_path)
        monkeypatch.setenv(REENTRY_GUARD, "1")
        monkeypatch.setattr(
            "memory_enhancement.interpreter.dependency_available", lambda: False
        )
        calls = self._record_execv(monkeypatch)

        reexec_under_project_venv(tmp_path, ["hook.py"])

        assert calls == []

    @pytest.mark.unit
    def test_does_nothing_without_a_venv(self, tmp_path, monkeypatch):
        monkeypatch.delenv(REENTRY_GUARD, raising=False)
        monkeypatch.setattr(
            "memory_enhancement.interpreter.dependency_available", lambda: False
        )
        calls = self._record_execv(monkeypatch)

        reexec_under_project_venv(tmp_path, ["hook.py"])

        assert calls == []

    @pytest.mark.unit
    def test_does_nothing_when_the_venv_interpreter_is_already_running(
        self, tmp_path, monkeypatch
    ):
        interpreter = tmp_path / ".venv" / "bin" / "python3"
        interpreter.parent.mkdir(parents=True)
        interpreter.symlink_to(sys.executable)
        monkeypatch.delenv(REENTRY_GUARD, raising=False)
        monkeypatch.setattr(
            "memory_enhancement.interpreter.dependency_available", lambda: False
        )
        calls = self._record_execv(monkeypatch)

        reexec_under_project_venv(tmp_path, ["hook.py"])

        assert calls == []
