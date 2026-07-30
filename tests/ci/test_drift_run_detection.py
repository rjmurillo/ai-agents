"""Tests for scripts/ci/drift_run_detection.py.

Covers the exit-code mapping from detect_agent_drift.py:
  rc=0  -> drift_detected=false, exit 0
  rc=1  -> drift_detected=true,  exit 0
  rc=2+ -> drift_detected=false, exit rc (propagate crash)
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from scripts.ci.drift_run_detection import main, run, write_github_output

# ---------------------------------------------------------------------------
# write_github_output
# ---------------------------------------------------------------------------


def test_write_github_output_appends_to_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    out = tmp_path / "output.txt"
    out.write_text("", encoding="utf-8")
    monkeypatch.setenv("GITHUB_OUTPUT", str(out))
    write_github_output("drift_detected", "true")
    assert out.read_text() == "drift_detected=true\n"


def test_write_github_output_falls_back_to_stdout(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("GITHUB_OUTPUT", raising=False)
    write_github_output("drift_detected", "false")
    assert "drift_detected=false" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# run() - main logic
# ---------------------------------------------------------------------------


def _mock_run(returncode: int) -> MagicMock:
    m = MagicMock()
    m.returncode = returncode
    return m


def test_no_drift_returns_zero_and_sets_false(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    out = tmp_path / "gh_out.txt"
    out.write_text("", encoding="utf-8")
    monkeypatch.setenv("GITHUB_OUTPUT", str(out))
    with patch("scripts.ci.drift_run_detection.subprocess.run", return_value=_mock_run(0)):
        assert run() == 0
    assert "drift_detected=false" in out.read_text()


def test_drift_detected_returns_zero_and_sets_true(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    out = tmp_path / "gh_out.txt"
    out.write_text("", encoding="utf-8")
    monkeypatch.setenv("GITHUB_OUTPUT", str(out))
    with patch("scripts.ci.drift_run_detection.subprocess.run", return_value=_mock_run(1)):
        assert run() == 0
    assert "drift_detected=true" in out.read_text()


def test_crash_propagates_exit_code(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    out = tmp_path / "gh_out.txt"
    out.write_text("", encoding="utf-8")
    monkeypatch.setenv("GITHUB_OUTPUT", str(out))
    with patch("scripts.ci.drift_run_detection.subprocess.run", return_value=_mock_run(3)):
        assert run() == 3
    # drift_detected set to false before propagating
    assert "drift_detected=false" in out.read_text()


def test_crash_rc2_propagated(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    out = tmp_path / "gh_out.txt"
    out.write_text("", encoding="utf-8")
    monkeypatch.setenv("GITHUB_OUTPUT", str(out))
    with patch("scripts.ci.drift_run_detection.subprocess.run", return_value=_mock_run(2)):
        assert run() == 2


def test_main_delegates_to_run() -> None:
    with patch("scripts.ci.drift_run_detection.run", return_value=0) as mock_run:
        assert main() == 0
        mock_run.assert_called_once()
