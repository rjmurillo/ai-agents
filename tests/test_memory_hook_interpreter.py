"""Tests for the memory hook virtualenv re-exec (issue #4011).

settings.json registers the memory hooks as `python3 -u ...`. That interpreter
usually cannot import python-frontmatter, so the recall and reflection hooks
exited 0 having done nothing. The re-exec resolves the dependency without
changing the registration.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

from memory_enhancement.interpreter import (
    REENTRY_GUARD,
    dependency_available,
    find_venv_interpreter,
    reexec_under_project_venv,
    running_under_venv,
)


def _make_venv(project_dir: Path, name: str = "bin/python3") -> Path:
    interpreter = project_dir / ".venv" / name
    interpreter.parent.mkdir(parents=True, exist_ok=True)
    interpreter.write_text("#!/bin/sh\n", encoding="utf-8")
    return interpreter


def _make_symlinked_venv(project_dir: Path) -> Path:
    """A fixture interpreter shaped like a real one: a symlink, not a file.

    Every virtualenv built by ``python -m venv`` or ``uv`` on POSIX links
    ``bin/python3`` back to the interpreter it was created from. Reproducing
    that is what makes the issue #4468 regression test meaningful.
    """
    interpreter = project_dir / ".venv" / "bin" / "python3"
    interpreter.parent.mkdir(parents=True, exist_ok=True)
    interpreter.symlink_to(sys.executable)
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
    """Every branch either execs once or returns, never both and never twice.

    The guard is set to "0" rather than deleted: monkeypatch.delenv records
    nothing when the variable is already absent, so the value the function
    writes would leak into every later subprocess in the session and silently
    disable the re-exec the registration tests assert on.
    """

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
        monkeypatch.setenv(REENTRY_GUARD, "0")
        monkeypatch.setattr(
            "memory_enhancement.interpreter.dependency_available", lambda: False
        )
        calls = self._record_execv(monkeypatch)

        reexec_under_project_venv(tmp_path, ["hook.py"])

        assert calls == [(str(interpreter), [str(interpreter), "-u", "hook.py"])]

    @pytest.mark.unit
    def test_sets_the_guard_so_the_child_cannot_loop(self, tmp_path, monkeypatch):
        _make_venv(tmp_path)
        monkeypatch.setenv(REENTRY_GUARD, "0")
        monkeypatch.setattr(
            "memory_enhancement.interpreter.dependency_available", lambda: False
        )
        self._record_execv(monkeypatch)

        reexec_under_project_venv(tmp_path, ["hook.py"])

        assert os.environ[REENTRY_GUARD] == "1"

    @pytest.mark.unit
    def test_does_nothing_when_the_dependency_imports(self, tmp_path, monkeypatch):
        _make_venv(tmp_path)
        monkeypatch.setenv(REENTRY_GUARD, "0")
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
        monkeypatch.setenv(REENTRY_GUARD, "0")
        monkeypatch.setattr(
            "memory_enhancement.interpreter.dependency_available", lambda: False
        )
        calls = self._record_execv(monkeypatch)

        reexec_under_project_venv(tmp_path, ["hook.py"])

        assert calls == []

    @pytest.mark.unit
    def test_does_nothing_when_already_running_under_that_venv(
        self, tmp_path, monkeypatch
    ):
        """The intended skip: this process belongs to the virtualenv found.

        Establishing that means setting ``sys.prefix``, which is what actually
        changes when a virtualenv is active. An earlier version of this test
        symlinked the fixture interpreter at ``sys.executable`` instead, which
        proves only that two paths resolve alike and is true of every
        virtualenv on the machine whether or not it is active (issue #4468).
        """
        _make_venv(tmp_path)
        monkeypatch.setenv(REENTRY_GUARD, "0")
        monkeypatch.setattr(
            "memory_enhancement.interpreter.dependency_available", lambda: False
        )
        monkeypatch.setattr(
            "memory_enhancement.interpreter.sys.prefix", str(tmp_path / ".venv")
        )
        calls = self._record_execv(monkeypatch)

        reexec_under_project_venv(tmp_path, ["hook.py"])

        assert calls == []

    @pytest.mark.unit
    def test_execs_when_the_venv_interpreter_symlinks_to_the_running_one(
        self, tmp_path, monkeypatch
    ):
        """Regression for issue #4468: the shape every real virtualenv has.

        ``bin/python3`` is a symlink to the interpreter the virtualenv was
        built from, so it resolves to the same file as any other interpreter
        from that base install, including the system ``python3`` the hooks run
        under. The old guard compared resolved paths and skipped the re-exec
        here, which disabled the feature everywhere it was needed.
        """
        interpreter = _make_symlinked_venv(tmp_path)
        monkeypatch.setenv(REENTRY_GUARD, "0")
        monkeypatch.setattr(
            "memory_enhancement.interpreter.dependency_available", lambda: False
        )
        monkeypatch.setattr(
            "memory_enhancement.interpreter.sys.prefix", str(tmp_path / "elsewhere")
        )
        calls = self._record_execv(monkeypatch)

        reexec_under_project_venv(tmp_path, ["hook.py"])

        assert calls == [(str(interpreter), [str(interpreter), "-u", "hook.py"])]

    @pytest.mark.unit
    def test_the_symlinked_fixture_really_does_collide_under_realpath(self, tmp_path):
        """Negative control for the regression above.

        If the symlink stopped resolving to the running interpreter, that test
        would pass without exercising the condition it exists to cover. This
        asserts the fixture still reproduces the collision the old guard saw.
        """
        interpreter = _make_symlinked_venv(tmp_path)

        assert os.path.realpath(interpreter) == os.path.realpath(sys.executable)


class TestRunningUnderVenv:
    """sys.prefix is the discriminator; resolved interpreter paths are not."""

    @pytest.mark.unit
    def test_true_when_the_prefix_is_the_venv(self, tmp_path, monkeypatch):
        venv_dir = tmp_path / ".venv"
        venv_dir.mkdir()
        monkeypatch.setattr(
            "memory_enhancement.interpreter.sys.prefix", str(venv_dir)
        )

        assert running_under_venv(venv_dir) is True

    @pytest.mark.unit
    def test_false_when_the_prefix_is_the_base_installation(
        self, tmp_path, monkeypatch
    ):
        venv_dir = tmp_path / ".venv"
        venv_dir.mkdir()
        monkeypatch.setattr(
            "memory_enhancement.interpreter.sys.prefix", str(tmp_path / "usr")
        )

        assert running_under_venv(venv_dir) is False

    @pytest.mark.unit
    def test_false_for_a_venv_that_does_not_exist(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "memory_enhancement.interpreter.sys.prefix", str(tmp_path / "usr")
        )

        assert running_under_venv(tmp_path / "absent" / ".venv") is False
