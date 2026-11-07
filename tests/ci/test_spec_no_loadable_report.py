"""The no-loadable report for `ai-spec-review.yml` (issue #6506 fail-open-27).

- pos: Azure-only references produce a "No requirements were loadable" report
       that keeps the AI-SPEC-VALIDATION marker and publishes `report_file`
- neg: the report never names PASS, FAIL, WARN or INFRA_FAILURE
- edge: hostile reference text is dropped, an empty list reads `*None*`, and an
        unwritable path returns a nonzero exit instead of a green step
"""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

import pytest

from scripts.ci import spec_no_loadable_report
from scripts.ci.spec_no_loadable_report import EXIT_CONFIG, EXIT_OK


def _run(tmp_path: Path, **env: str) -> tuple[int, str, dict[str, str]]:
    out_file = tmp_path / "out.txt"
    base = {
        "ISSUE_REFS": "",
        "AZURE_REFS": "AB#123",
        "GITHUB_REPOSITORY": "owner/repo",
        "RUNNER_TEMP": str(tmp_path),
        "GITHUB_RUN_ID": "7",
        "GITHUB_OUTPUT": str(out_file),
    }
    with patch.dict(os.environ, {**base, **env}):
        code = spec_no_loadable_report.main()
    outputs = (
        dict(line.split("=", 1) for line in out_file.read_text().splitlines())
        if out_file.exists()
        else {}
    )
    report = Path(outputs["report_file"]).read_text(encoding="utf-8") if outputs else ""
    return code, report, outputs


def test_azure_only_writes_the_report_and_publishes_its_path(tmp_path):
    code, report, outputs = _run(tmp_path)

    assert code == EXIT_OK
    assert outputs["report_file"] == str(tmp_path / "spec-no-loadable-report-7.md")
    assert report.startswith("<!-- AI-SPEC-VALIDATION -->")
    assert "No requirements were loadable" in report
    assert "AB#123" in report


@pytest.mark.parametrize("word", ["PASS", "FAIL", "WARN ", "INFRA_FAILURE", "CRITICAL"])
def test_report_never_names_a_verdict(tmp_path, word):
    _, report, _ = _run(tmp_path, ISSUE_REFS="99")

    assert word not in report


def test_issue_and_azure_cells_both_render(tmp_path):
    _, report, _ = _run(tmp_path, ISSUE_REFS="99 owner/other#4", AZURE_REFS="AB#5 AB#9")

    assert "| **Issues** | 99 owner/other#4 |" in report
    assert "| **Azure Boards** | AB#5 AB#9 |" in report


def test_empty_issue_list_reads_none(tmp_path):
    _, report, _ = _run(tmp_path, ISSUE_REFS="")

    assert "| **Issues** | *None* |" in report


@pytest.mark.parametrize("hostile", ["<b>x</b>", "a|b", "@team", "[x](http://e.example)", "x\ny"])
def test_hostile_reference_text_is_dropped(tmp_path, hostile):
    _, report, _ = _run(tmp_path, AZURE_REFS=f"AB#1 {hostile}")

    assert "AB#1" in report
    for fragment in ("<b>", "@team", "](http://e", "a|b"):
        assert fragment not in report


def test_unsafe_repository_name_falls_back(tmp_path):
    _, report, _ = _run(tmp_path, GITHUB_REPOSITORY="evil](http://e.example)")

    assert "e.example" not in report


def test_unwritable_report_path_returns_nonzero(tmp_path, capsys):
    code, _, outputs = _run(tmp_path, RUNNER_TEMP=str(tmp_path / "missing" / "dir"))

    assert code == EXIT_CONFIG
    assert outputs == {}
    assert "failed to write" in capsys.readouterr().err
