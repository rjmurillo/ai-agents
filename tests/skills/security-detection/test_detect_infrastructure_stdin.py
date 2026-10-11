#!/usr/bin/env python3
"""Tests for NUL-delimited stdin handling."""

from __future__ import annotations

import io
import json
import subprocess
import sys
from pathlib import Path

import pytest

HERE = str(Path(__file__).resolve().parent)
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from detect_infrastructure_test_helpers import SCRIPT_PATH, get_files_from_stdin


def test_null_delimited_stdin_treats_option_shaped_filename_as_data() -> None:
    result = subprocess.run(
        [sys.executable, str(SCRIPT_PATH), "--files-from-stdin", "--json"],
        input=b"--use-git-staged\0.env.production\0",
        check=True,
        capture_output=True,
    )

    payload = json.loads(result.stdout)
    assert payload["file_count"] == 2
    assert payload["highest_risk"] == "critical"
    assert payload["findings"] == [
        {"File": ".env.production", "RiskLevel": "critical"},
    ]


def test_null_delimited_stdin_reader_preserves_option_shaped_paths(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(sys, "stdin", io.StringIO("--use-git-staged\0.env\0"))

    assert get_files_from_stdin() == ["--use-git-staged", ".env"]
