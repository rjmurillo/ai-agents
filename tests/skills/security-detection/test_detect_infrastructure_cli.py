#!/usr/bin/env python3
"""Tests for the detect_infrastructure command-line entry points."""

from __future__ import annotations

import io
import json
import runpy
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

HERE = str(Path(__file__).resolve().parent)
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from detect_infrastructure_test_helpers import SCRIPT_PATH, main


def test_main_reads_null_delimited_stdin(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(
        sys,
        "argv",
        ["detect_infrastructure.py", "--files-from-stdin", "--json"],
    )
    monkeypatch.setattr(sys, "stdin", io.StringIO("--use-git-staged\0.env\0"))

    assert main() == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["file_count"] == 2
    assert payload["highest_risk"] == "critical"


def test_main_reports_high_risk_findings(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(
        sys,
        "argv",
        ["detect_infrastructure.py", "--files", "Dockerfile"],
    )

    assert main() == 0

    assert "HIGH: Security agent review RECOMMENDED" in capsys.readouterr().out


def test_script_entry_point_exits_with_main_result(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(
        sys,
        "argv",
        [str(SCRIPT_PATH), "--files", "README.md"],
    )

    with pytest.raises(SystemExit, match="0"):
        runpy.run_path(str(SCRIPT_PATH), run_name="__main__")

    assert "No infrastructure/security files detected." in capsys.readouterr().out


class TestMain:
    """Tests for main entry point."""

    def test_returns_zero_with_no_files(self, capsys: pytest.CaptureFixture[str]) -> None:
        with patch("sys.argv", ["detect_infrastructure.py"]):
            result = main()
        assert result == 0

    def test_json_output(self, capsys: pytest.CaptureFixture[str]) -> None:
        argv = [
            "detect_infrastructure.py", "--files",
            ".github/workflows/ci.yml", "--json",
        ]
        with patch("sys.argv", argv):
            result = main()
        assert result == 0
        captured = capsys.readouterr()
        assert '"critical"' in captured.out
        assert json.loads(captured.out)["highest_risk"] == "critical"

    def test_human_output_for_findings(self, capsys: pytest.CaptureFixture[str]) -> None:
        with patch("sys.argv", ["detect_infrastructure.py", "--files", ".github/workflows/ci.yml"]):
            result = main()
        assert result == 0
        captured = capsys.readouterr()
        assert "CRITICAL" in captured.out

    def test_returns_zero_for_files_without_findings(self) -> None:
        with patch("sys.argv", ["detect_infrastructure.py", "--files", "src/main.py"]):
            result = main()
        assert result == 0

    def test_help_exits_zero(self) -> None:
        with patch("sys.argv", ["detect_infrastructure.py", "--help"]):
            with pytest.raises(SystemExit) as exc:
                main()
        assert exc.value.code == 0
