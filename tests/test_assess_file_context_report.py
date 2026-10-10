"""The markdown report lists issues against each file's own thresholds (issue #6166)."""

from __future__ import annotations

import sys
from pathlib import Path

_HERE = str(Path(__file__).resolve().parent)
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

# ruff: noqa: E402
from assess_file_context_helpers import CONFIG, assessment, generate_markdown_report


def test_test_file_passing_its_floor_reports_no_issue() -> None:
    report = generate_markdown_report([assessment("tests/test_new.py", "test")], CONFIG)

    assert "Testability Issues" not in report


def test_explicit_production_context_reports_the_issue() -> None:
    files = [assessment("tests/test_new.py", "test")]

    report = generate_markdown_report(files, CONFIG, "production")

    assert "Testability Issues" in report


def test_authored_file_reports_production_issue_by_default() -> None:
    report = generate_markdown_report([assessment("src/mod.py", "authored")], CONFIG)

    assert "Testability Issues" in report
