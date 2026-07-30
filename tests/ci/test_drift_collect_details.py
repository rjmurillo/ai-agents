"""Tests for scripts/ci/drift_collect_details.py.

Covers:
  - rc >= 2 from detect_agent_drift.py  -> error annotation, exit rc
  - empty drift-results.json            -> error, exit 1
  - parse_drift_results.py failure      -> propagate rc
  - success: agents_count written to GITHUB_OUTPUT
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

_SCRIPTS_CI = Path(__file__).resolve().parents[2] / "scripts" / "ci"
sys.path.insert(0, str(_SCRIPTS_CI))

from drift_collect_details import run, write_github_output  # noqa: E402


def _mock_run(returncode: int) -> MagicMock:
    m = MagicMock()
    m.returncode = returncode
    return m


def test_write_github_output_appends(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    out = tmp_path / "out.txt"
    out.write_text("", encoding="utf-8")
    monkeypatch.setenv("GITHUB_OUTPUT", str(out))
    write_github_output("agents_count", "3")
    assert out.read_text() == "agents_count=3\n"


def test_detection_crash_rc2_returns_2(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("RUNNER_TEMP", str(tmp_path))
    out_file = tmp_path / "out.txt"
    out_file.write_text("", encoding="utf-8")
    monkeypatch.setenv("GITHUB_OUTPUT", str(out_file))
    with patch("drift_collect_details.subprocess.run", return_value=_mock_run(2)):
        rc = run()
    assert rc == 2
    assert "::error::" in capsys.readouterr().out


def test_empty_json_returns_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("RUNNER_TEMP", str(tmp_path))
    out_file = tmp_path / "out.txt"
    out_file.write_text("", encoding="utf-8")
    monkeypatch.setenv("GITHUB_OUTPUT", str(out_file))
    with patch("drift_collect_details.subprocess.run", return_value=_mock_run(0)):
        rc = run()
    assert rc == 1
    assert "empty" in capsys.readouterr().out


def test_parse_script_failure_propagated(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("RUNNER_TEMP", str(tmp_path))
    out_file = tmp_path / "out.txt"
    out_file.write_text("", encoding="utf-8")
    monkeypatch.setenv("GITHUB_OUTPUT", str(out_file))
    detect_ok = _mock_run(0)
    parse_fail = _mock_run(5)

    def fake_run(cmd: list[str], **kwargs: object) -> MagicMock:
        if "detect_agent_drift" in " ".join(str(c) for c in cmd):
            (tmp_path / "drift-results.json").write_text('{"results":[]}', encoding="utf-8")
            return detect_ok
        return parse_fail

    with patch("drift_collect_details.subprocess.run", side_effect=fake_run):
        rc = run()
    assert rc == 5


def test_success_writes_agents_count(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("RUNNER_TEMP", str(tmp_path))
    out_file = tmp_path / "out.txt"
    out_file.write_text("", encoding="utf-8")
    monkeypatch.setenv("GITHUB_OUTPUT", str(out_file))
    (tmp_path / "drift-count.txt").write_text("2\n", encoding="utf-8")
    detect_ok = _mock_run(0)
    parse_ok = _mock_run(0)

    def fake_run(cmd: list[str], **kwargs: object) -> MagicMock:
        if "detect_agent_drift" in " ".join(str(c) for c in cmd):
            (tmp_path / "drift-results.json").write_text('{"results":[]}', encoding="utf-8")
            return detect_ok
        return parse_ok

    with patch("drift_collect_details.subprocess.run", side_effect=fake_run):
        rc = run()
    assert rc == 0
    assert "agents_count=2" in out_file.read_text()


def test_runner_temp_defaults_to_dot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("RUNNER_TEMP", raising=False)
    out_file = tmp_path / "out.txt"
    out_file.write_text("", encoding="utf-8")
    monkeypatch.setenv("GITHUB_OUTPUT", str(out_file))
    (tmp_path / "drift-count.txt").write_text("0", encoding="utf-8")
    detect_ok = _mock_run(0)
    parse_ok = _mock_run(0)

    def fake_run(cmd: list[str], **kwargs: object) -> MagicMock:
        if "detect_agent_drift" in " ".join(str(c) for c in cmd):
            (tmp_path / "drift-results.json").write_text("{}", encoding="utf-8")
            return detect_ok
        return parse_ok

    with patch("drift_collect_details.subprocess.run", side_effect=fake_run):
        rc = run()
    assert rc == 0
