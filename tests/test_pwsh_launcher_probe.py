"""The pwsh probe skips a launcher that cannot start and nothing else (issue #7231)."""

from __future__ import annotations

import stat
from pathlib import Path

import pytest

from tests import pwsh_launcher_probe as probe


def _stub_pwsh(directory: Path, body: str) -> None:
    stub = directory / "pwsh"
    stub.write_text(f"#!/bin/sh\n{body}\n", encoding="utf-8")
    stub.chmod(stub.stat().st_mode | stat.S_IEXEC)


@pytest.fixture
def path_with(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    """Point PATH at a directory that holds only the stub under test."""
    probe.pwsh_skip_reason.cache_clear()
    monkeypatch.setattr(probe, "_ON_CI", False)
    monkeypatch.setenv("PATH", str(tmp_path))
    yield tmp_path
    probe.pwsh_skip_reason.cache_clear()


def test_absent_launcher_skips_as_not_installed(path_with: Path) -> None:
    assert probe.pwsh_skip_reason() == "pwsh not installed"


def test_launcher_that_cannot_start_skips_with_its_own_message(path_with: Path) -> None:
    _stub_pwsh(
        path_with, "echo 'snap-confine is packaged without necessary permissions' >&2; exit 1"
    )

    reason = probe.pwsh_skip_reason()

    assert reason is not None
    assert "snap-confine is packaged without necessary permissions" in reason
    assert "issue #7231" in reason


def test_launcher_that_starts_runs_the_test(path_with: Path) -> None:
    _stub_pwsh(path_with, "echo pwsh-probe-ok")

    assert probe.pwsh_skip_reason() is None


def test_launcher_that_starts_and_rejects_the_probe_runs_the_test(path_with: Path) -> None:
    _stub_pwsh(path_with, "echo 'Unknown parameter: -NonInteractive' >&2; exit 64")

    assert probe.pwsh_skip_reason() is None


def test_launcher_that_exits_zero_without_the_marker_runs_the_test(path_with: Path) -> None:
    _stub_pwsh(path_with, "exit 0")

    assert probe.pwsh_skip_reason() is None


def test_ci_never_skips_a_present_launcher(
    path_with: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(probe, "_ON_CI", True)
    _stub_pwsh(path_with, "exit 1")

    assert probe.pwsh_skip_reason() is None


def test_require_working_pwsh_skips_through_pytest(path_with: Path) -> None:
    _stub_pwsh(
        path_with, "echo 'snap-confine is packaged without necessary permissions' >&2; exit 1"
    )

    with pytest.raises(pytest.skip.Exception):
        probe.require_working_pwsh()
