"""Real shared-runner contract tests for the ruff ratchet."""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.ci import ruff_ratchet
from tests.ci.ruff_ratchet_test_helpers import _install_hung_popen, _install_noop_windows_job

# --- Through the real shared runner ----------------------------------------
#
# The tests above fake ``_run_subprocess`` and write its marker text by hand.
# These run the real runner with only ``Popen`` replaced, so a change to the
# runner's timeout contract (exit -1, "Command timed out after Ns") fails here.


@pytest.mark.windows_path
def test_real_runner_ruff_timeout_exits_external_with_partial_output(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(ruff_ratchet, "_module_available_outside_checkout", lambda _n, _r: True)
    child = _install_hung_popen(monkeypatch, b'[{"code": "E5', b"warning: slow\n")

    exit_code = ruff_ratchet.run_ruff(["scripts/a.py"], tmp_path, {})
    captured = capsys.readouterr()

    assert exit_code == ruff_ratchet.EXIT_EXTERNAL
    assert child.timeouts[0] == ruff_ratchet._RUFF_TIMEOUT_SECONDS
    assert f"Command timed out after {ruff_ratchet._RUFF_TIMEOUT_SECONDS}s" in captured.err
    assert "warning: slow" in captured.err
    assert '[{"code": "E5' in captured.err


@pytest.mark.windows_path
def test_real_runner_git_timeout_exits_external_with_partial_output(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    child = _install_hung_popen(monkeypatch, b"scripts/partial.py\0", b"progress: reading refs")

    status, files, _base = ruff_ratchet.changed_python_files("feature-base", tmp_path)
    captured = capsys.readouterr()

    assert status == ruff_ratchet.EXIT_EXTERNAL
    assert files == []
    assert child.timeouts[0] == ruff_ratchet._GIT_TIMEOUT_SECONDS
    # One hung call: the timed-out communicate plus its drain, no second git.
    assert len(child.timeouts) == 2
    assert f"Command timed out after {ruff_ratchet._GIT_TIMEOUT_SECONDS}s" in captured.err
    assert "progress: reading refs" in captured.err
    assert "git partial stdout" in captured.err
    assert "scripts/partial.py" in captured.err


@pytest.mark.windows_path
def test_hung_popen_fixture_reaches_communicate_under_simulated_windows(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The Windows branch must not kill the runner-contract fake before use."""
    from scripts.validation import subprocess_runner

    monkeypatch.setattr(ruff_ratchet, "_module_available_outside_checkout", lambda _n, _r: True)
    child = _install_hung_popen(monkeypatch, b"", b"")
    monkeypatch.setattr(subprocess_runner.os, "name", "nt")
    monkeypatch.setattr(subprocess_runner.sys, "platform", "win32")
    monkeypatch.setattr(subprocess_runner, "_SUPPORTS_PGROUP", False)

    exit_code = ruff_ratchet.run_ruff(["scripts/a.py"], tmp_path, {})

    assert exit_code == ruff_ratchet.EXIT_EXTERNAL
    assert child.timeouts, "the Windows setup path never reached communicate"


@pytest.mark.windows_path
def test_real_runner_missing_ruff_module_exits_external(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    from scripts.validation import subprocess_runner

    class _MissingModulePopen:
        pid = 1
        returncode = 1
        _handle = 1

        def communicate(self, timeout: float | None = None) -> tuple[str, str]:
            return "", "No module named ruff\n"

        def kill(self) -> None:
            return None

        def wait(self, timeout: float | None = None) -> int:
            return self.returncode

        def __enter__(self) -> _MissingModulePopen:
            return self

        def __exit__(self, *_exc: object) -> None:
            return None

    monkeypatch.setattr(ruff_ratchet, "_module_available_outside_checkout", lambda _n, _r: True)
    _install_noop_windows_job(monkeypatch)
    monkeypatch.setattr(
        subprocess_runner.subprocess,
        "Popen",
        lambda *_a, **_k: _MissingModulePopen(),
    )

    exit_code = ruff_ratchet.run_ruff(["scripts/a.py"], tmp_path, {})

    assert exit_code == ruff_ratchet.EXIT_EXTERNAL
    captured = capsys.readouterr()
    assert "No module named ruff" in captured.err
    assert "produced no JSON output" in captured.err
