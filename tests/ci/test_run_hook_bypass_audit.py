"""Tests for scripts/ci/run_hook_bypass_audit.py.

Covers the detector wrapper extracted from audit-hook-bypass.yml. The contract
under test is the one Issue #2808 showed was masked: exit 1 from the detector
means "indicators found" and must not fail the job, while any code >= 2 means
the detector crashed and must fail loud instead of being reported as a clean
audit. A non-crash code that still produced no report is the same broken-audit
condition reached by a different route.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

_SCRIPTS_CI = Path(__file__).resolve().parent.parent.parent / "scripts" / "ci"
_original_path = sys.path.copy()
try:
    sys.path.insert(0, str(_SCRIPTS_CI))
    from run_hook_bypass_audit import main  # noqa: E402
finally:
    sys.path[:] = _original_path


class _Detector:
    """Stand-in for subprocess.run that returns a code and optionally writes JSON."""

    def __init__(self, code: int, report: Path | None, body: str = '{"a": 1}') -> None:
        self.calls: list[list[str]] = []
        self._code = code
        self._report = report
        self._body = body

    def __call__(self, argv, **kwargs):  # noqa: ANN001, ANN204
        self.calls.append(list(argv))
        if self._report is not None:
            self._report.write_text(self._body, encoding="utf-8")
        return subprocess.CompletedProcess(argv, self._code)


def _args(tmp_path: Path) -> list[str]:
    return [
        "--detector", str(tmp_path / "detect.py"),
        "--base-ref", "origin/main",
        "--output", str(tmp_path / "audit.json"),
    ]


@pytest.mark.parametrize("code", [0, 1])
def test_clean_and_indicator_codes_both_succeed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, code: int
) -> None:
    monkeypatch.setattr(subprocess, "run", _Detector(code, tmp_path / "audit.json"))
    assert main(_args(tmp_path)) == 0


@pytest.mark.parametrize("code", [2, 3, 127])
def test_crash_codes_are_forwarded_unchanged(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    code: int,
) -> None:
    monkeypatch.setattr(subprocess, "run", _Detector(code, tmp_path / "audit.json"))
    assert main(_args(tmp_path)) == code
    assert f"failed to run (exit {code})" in capsys.readouterr().out


def test_missing_report_after_a_success_code_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(subprocess, "run", _Detector(0, None))
    assert main(_args(tmp_path)) == 1
    assert "missing or empty" in capsys.readouterr().out


def test_empty_report_after_a_success_code_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(
        subprocess, "run", _Detector(0, tmp_path / "audit.json", body="")
    )
    assert main(_args(tmp_path)) == 1
    assert "missing or empty" in capsys.readouterr().out


def test_crash_takes_precedence_over_a_written_report(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(subprocess, "run", _Detector(2, tmp_path / "audit.json"))
    assert main(_args(tmp_path)) == 2


def test_detector_receives_the_forwarded_arguments(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    detector = _Detector(0, tmp_path / "audit.json")
    monkeypatch.setattr(subprocess, "run", detector)
    main(_args(tmp_path))
    argv = detector.calls[0]
    assert argv[1] == str(tmp_path / "detect.py")
    assert argv[2:4] == ["--base-ref", "origin/main"]
    assert argv[4:] == ["--output", str(tmp_path / "audit.json")]


def test_unlaunchable_detector_is_reported(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def _boom(argv, **kwargs):  # noqa: ANN001, ANN202
        raise OSError("exec format error")

    monkeypatch.setattr(subprocess, "run", _boom)
    assert main(_args(tmp_path)) == 1
    assert "cannot run" in capsys.readouterr().err
