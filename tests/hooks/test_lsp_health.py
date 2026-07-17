#!/usr/bin/env python3
"""Tests for the lsp_health runtime-down signal (issue #2622, ADR-062 fail-open).

Covers the explicit ``LSP_DOWN`` env signal parse, the one-time-warning dedup
marker (warn once per session, silent after), the SessionStart marker clear, and
every fail-open degrade path (filesystem error never raises).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from scripts.hook_utilities import lsp_health  # noqa: E402


@pytest.fixture(autouse=True)
def _isolated_state(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Point the marker dir at a tmp dir and clear the env signal per test."""
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
    monkeypatch.delenv("LSP_DOWN", raising=False)


class TestLspRuntimeDown:
    def test_unset_is_not_down(self):
        assert lsp_health.lsp_runtime_down() is False

    @pytest.mark.parametrize("value", ["true", "TRUE", "1", "yes", "on", " True "])
    def test_truthy_values_are_down(self, monkeypatch, value):
        monkeypatch.setenv("LSP_DOWN", value)
        assert lsp_health.lsp_runtime_down() is True

    @pytest.mark.parametrize("value", ["false", "0", "no", "", "maybe"])
    def test_non_truthy_values_are_not_down(self, monkeypatch, value):
        monkeypatch.setenv("LSP_DOWN", value)
        assert lsp_health.lsp_runtime_down() is False


class TestPersistentDownSignal:
    """Issue #3108: a persistent marker makes the signal usable from dedicated tools."""

    def test_marker_makes_runtime_down_without_env(self):
        # Arrange: no LSP_DOWN env (autouse fixture cleared it), signal marker set.
        project = str(REPO_ROOT)
        assert lsp_health.lsp_runtime_down(project) is False
        assert lsp_health.set_lsp_down_signal(project) is True

        # Act / Assert: a fresh reader (the case a dedicated tool call hits) sees
        # the signal purely from the persisted file, with no env var in scope.
        assert lsp_health.lsp_runtime_down(project) is True

    def test_clear_restores_enforcement(self):
        project = str(REPO_ROOT)
        lsp_health.set_lsp_down_signal(project)
        assert lsp_health.lsp_runtime_down(project) is True

        assert lsp_health.clear_lsp_down_signal(project) is True
        assert lsp_health.lsp_runtime_down(project) is False

    def test_clear_is_idempotent_when_absent(self):
        assert lsp_health.clear_lsp_down_signal(str(REPO_ROOT)) is True

    def test_signal_marker_is_distinct_from_warn_marker(self):
        project = str(REPO_ROOT)
        lsp_health.set_lsp_down_signal(project)
        # The warn-once marker must not exist just because the signal is set.
        assert not lsp_health._marker_path(project).exists()
        assert lsp_health._down_signal_path(project).exists()

    def test_set_degrades_to_false_on_filesystem_error(self, monkeypatch):
        # A NUL byte in the path forces an OSError inside the writer.
        monkeypatch.setattr(
            lsp_health, "_down_signal_path", lambda _project_dir: Path("bad\0signal")
        )
        assert lsp_health.set_lsp_down_signal(str(REPO_ROOT)) is False

    def test_runtime_down_degrades_to_false_on_filesystem_error(self, monkeypatch):
        monkeypatch.setattr(
            lsp_health, "_down_signal_path", lambda _project_dir: Path("bad\0signal")
        )
        # Never raises; a broken marker read means "not down" (enforce as normal).
        assert lsp_health.lsp_runtime_down(str(REPO_ROOT)) is False


class TestDownSignalCli:
    """The CLI is the shell-usable producer the issue needs (Bash persists a file)."""

    def test_set_then_status_reports_active(self, tmp_path, monkeypatch, capsys):
        monkeypatch.chdir(tmp_path)
        assert lsp_health._main(["--set-down"]) == 0
        capsys.readouterr()

        assert lsp_health._main(["--status"]) == 0
        assert capsys.readouterr().out.strip() == "active"

    def test_clear_then_status_reports_inactive(self, tmp_path, monkeypatch, capsys):
        monkeypatch.chdir(tmp_path)
        lsp_health._main(["--set-down"])
        capsys.readouterr()

        assert lsp_health._main(["--clear-down"]) == 0
        capsys.readouterr()
        assert lsp_health._main(["--status"]) == 0
        assert capsys.readouterr().out.strip() == "inactive"

    def test_requires_a_mode(self):
        with pytest.raises(SystemExit):
            lsp_health._main([])


class TestWarnOnce:
    def test_first_call_warns_and_writes_marker(self, capsys):
        emitted = lsp_health.warn_once_lsp_down("lsp-read-guard", str(REPO_ROOT))
        assert emitted is True
        err = capsys.readouterr().err
        assert "LSP runtime is down" in err
        assert lsp_health._marker_path(str(REPO_ROOT)).exists()

    def test_second_call_is_silent(self, capsys):
        lsp_health.warn_once_lsp_down("lsp-read-guard", str(REPO_ROOT))
        capsys.readouterr()  # drain first warning
        emitted = lsp_health.warn_once_lsp_down("lsp-read-guard", str(REPO_ROOT))
        assert emitted is False
        assert capsys.readouterr().err == ""

    def test_existing_marker_is_silent(self, capsys):
        marker = lsp_health._marker_path(str(REPO_ROOT))
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text("1", encoding="utf-8")
        emitted = lsp_health.warn_once_lsp_down("lsp-read-guard", str(REPO_ROOT))
        assert emitted is False
        assert capsys.readouterr().err == ""

    def test_clear_marker_re_enables_warning(self, capsys):
        lsp_health.warn_once_lsp_down("lsp-read-guard", str(REPO_ROOT))
        capsys.readouterr()
        assert lsp_health.clear_lsp_down_marker(str(REPO_ROOT)) is True
        emitted = lsp_health.warn_once_lsp_down("lsp-read-guard", str(REPO_ROOT))
        assert emitted is True
        assert "LSP runtime is down" in capsys.readouterr().err

    def test_clear_marker_is_idempotent_when_absent(self):
        # No marker written yet; clearing must not raise and returns True.
        assert lsp_health.clear_lsp_down_marker(str(REPO_ROOT)) is True


class TestFailOpen:
    def test_warn_once_never_raises_on_unwritable_dir(self, monkeypatch, capsys):
        # Force the marker dir to an unwritable location: warning still prints,
        # the call reports warned, and no exception escapes.
        monkeypatch.setattr(lsp_health, "_state_dir", lambda: Path("/proc/nonexistent/cannot"))
        emitted = lsp_health.warn_once_lsp_down("lsp-read-guard", str(REPO_ROOT))
        assert emitted is True
        assert "LSP runtime is down" in capsys.readouterr().err

    def test_state_dir_falls_back_when_home_raises(self, monkeypatch, tmp_path):
        """_state_dir() uses tempfile.gettempdir() when XDG_STATE_HOME is absent
        and Path.home() raises RuntimeError (sandboxed/CI/no-homedir environments).
        """

        def _raise() -> Path:
            raise RuntimeError("Cannot determine home directory")

        monkeypatch.delenv("XDG_STATE_HOME", raising=False)
        monkeypatch.setattr(Path, "home", staticmethod(_raise))
        # Route tempfile fallback to tmp_path to keep tests hermetic
        monkeypatch.setattr(lsp_health.tempfile, "gettempdir", lambda: str(tmp_path))
        state = lsp_health._state_dir()
        assert str(state).startswith(str(tmp_path))
        assert state.name == lsp_health._STATE_SUBDIR

    def test_warn_once_never_raises_when_home_fails(self, monkeypatch, tmp_path, capsys):
        """warn_once_lsp_down() falls back gracefully when Path.home() raises
        RuntimeError; the warning is still emitted (fail-open, never raises).
        """

        def _raise() -> Path:
            raise RuntimeError("Cannot determine home directory")

        monkeypatch.delenv("XDG_STATE_HOME", raising=False)
        monkeypatch.setattr(Path, "home", staticmethod(_raise))
        # Route tempfile fallback to tmp_path to avoid stale markers from prior runs
        monkeypatch.setattr(lsp_health.tempfile, "gettempdir", lambda: str(tmp_path))
        emitted = lsp_health.warn_once_lsp_down("lsp-read-guard", str(REPO_ROOT))
        assert emitted is True
        assert "LSP runtime is down" in capsys.readouterr().err

    def test_warn_once_emits_when_marker_path_is_invalid(self, monkeypatch, capsys):
        monkeypatch.setattr(lsp_health, "_marker_path", lambda _project_dir: Path("bad\0marker"))
        emitted = lsp_health.warn_once_lsp_down("lsp-read-guard", str(REPO_ROOT))
        assert emitted is True
        assert "LSP runtime is down" in capsys.readouterr().err

    def test_clear_marker_fails_open_when_marker_path_is_invalid(self, monkeypatch):
        monkeypatch.setattr(lsp_health, "_marker_path", lambda _project_dir: Path("bad\0marker"))
        assert lsp_health.clear_lsp_down_marker(str(REPO_ROOT)) is False
