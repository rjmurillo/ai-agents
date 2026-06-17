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
        monkeypatch.setattr(
            lsp_health, "_state_dir", lambda: Path("/proc/nonexistent/cannot")
        )
        emitted = lsp_health.warn_once_lsp_down("lsp-read-guard", str(REPO_ROOT))
        assert emitted is True
        assert "LSP runtime is down" in capsys.readouterr().err
