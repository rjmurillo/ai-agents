"""Report for a PR whose spec references hold no loadable requirements (issue #6506).

An `AB#` only body arms the spec gates, but the loader cannot read Azure Boards
content. The workflow skips the model steps and still posts this report.

- pos: loadable=false posts a "No requirements were loadable" report, exit 0
- neg: the report never claims a verdict
- edge: loadable true or unset keeps the full report; has_specs=false wins;
        hostile reference text stays inside one table cell
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from unittest.mock import patch

import pytest

_SCRIPTS_DIR = Path(__file__).resolve().parents[1] / ".github" / "scripts"


def _import_script(name: str):
    spec = importlib.util.spec_from_file_location(name, _SCRIPTS_DIR / f"{name}.py")
    assert spec is not None, f"Could not load spec for {name}"
    assert spec.loader is not None, f"Spec for {name} has no loader"
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_mod = _import_script("generate_spec_report")
main = _mod.main


def _run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *argv: str) -> tuple[int, str]:
    output_file = tmp_path / "output"
    output_file.touch()
    monkeypatch.setenv("GITHUB_OUTPUT", str(output_file))
    report_dir = tmp_path / "ai-review-results"
    report_dir.mkdir()
    with patch.object(_mod, "initialize_ai_review", return_value=str(report_dir)):
        rc = main(["--github-repository", "owner/repo", *argv])
    report_file = dict(
        line.split("=", 1) for line in output_file.read_text().splitlines() if "=" in line
    )["report_file"]
    return rc, Path(report_file).read_text()


def test_loadable_false_posts_a_no_requirements_report_and_exits_zero(tmp_path, monkeypatch):
    rc, report = _run(
        tmp_path,
        monkeypatch,
        "--has-specs",
        "true",
        "--loadable",
        "false",
        "--azure-refs",
        "AB#123",
    )

    assert rc == 0
    assert "<!-- AI-SPEC-VALIDATION -->" in report
    assert "No requirements were loadable" in report
    assert "AB#123" in report


def test_loadable_false_never_claims_a_verdict_even_when_verdicts_are_passed(tmp_path, monkeypatch):
    _, report = _run(
        tmp_path,
        monkeypatch,
        "--has-specs",
        "true",
        "--loadable",
        "false",
        "--azure-refs",
        "AB#5",
        "--trace-verdict",
        "PASS",
        "--completeness-verdict",
        "PASS",
    )

    assert "PASS" not in report
    assert "INFRA_FAILURE" not in report


@pytest.mark.parametrize("loadable", [["--loadable", "true"], []])
def test_loadable_true_or_unset_keeps_the_full_report(tmp_path, monkeypatch, loadable):
    _, report = _run(
        tmp_path,
        monkeypatch,
        "--has-specs",
        "true",
        "--trace-verdict",
        "PASS",
        "--completeness-verdict",
        "PASS",
        *loadable,
    )

    assert "No requirements were loadable" not in report


def test_no_specs_wins_over_loadable_false(tmp_path, monkeypatch):
    _, report = _run(tmp_path, monkeypatch, "--has-specs", "false", "--loadable", "false")

    assert "No spec references found" in report


def test_hostile_azure_text_stays_in_one_cell(tmp_path, monkeypatch):
    _, report = _run(
        tmp_path,
        monkeypatch,
        "--has-specs",
        "true",
        "--loadable",
        "false",
        "--azure-refs",
        "<b>x</b>|@team",
    )

    assert "<b>" not in report
    assert "|@team" not in report
