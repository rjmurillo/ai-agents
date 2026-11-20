"""render_report.py and report_adr.py: the optional adr_drift section."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
import report_adr
from render_report import esc, main, render_page


def _finding(**overrides: Any) -> dict[str, Any]:
    base = {
        "id": "abc123def456",
        "kind": "adr-duplicate-number",
        "group": "Numbering",
        "severity": "high",
        "confidence": "deterministic",
        "evidence": {"path": "docs/adr/ADR-001-b.md", "line": 3},
        "suggested_fix": "Rename the later file to 124.",
    }
    return {**base, **overrides}


def _section(findings: list[dict[str, Any]], align: dict[str, Any] | None = None) -> dict[str, Any]:
    repo = {
        "repo": "my-repo",
        "head": "abc",
        "examined": 300,
        "truncated": False,
        "findings": findings,
        "align": align or {"status": "absent"},
    }
    return {"repos": [repo]}


def _run(tmp_path: Path, report: dict[str, Any], capsys) -> tuple[int, str]:
    path = tmp_path / "report.json"
    path.write_text(json.dumps(report), encoding="utf-8")
    code = 0
    try:
        main([str(path)])
    except SystemExit as exc:
        code = int(exc.code or 0)
    capsys.readouterr()
    html = tmp_path / "report.html"
    return code, html.read_text(encoding="utf-8") if html.exists() else ""


def test_section_renders_counts_findings_and_the_fix(tmp_path, capsys):
    report = {"scores": {"overall": 0.8}, "adr_drift": _section([_finding()])}

    code, html = _run(tmp_path, report, capsys)

    assert code == 0
    assert "ADR drift" in html and "adr-duplicate-number" in html
    assert "Rename the later file to 124." in html and "docs/adr/ADR-001-b.md:3" in html
    assert "1 findings: 1 numbering, 0 links, 0 history. 300 commits examined." in html


def test_page_without_the_section_equals_the_page_with_the_section_cut_out():
    base = {"scores": {"overall": 0.8}, "grade": "B"}

    plain = render_page(base)
    extended = render_page({**base, "adr_drift": _section([_finding()])})

    start = extended.index('\n<section aria-labelledby="adr-drift-h">')
    end = extended.index("\n</main>")
    assert extended[:start] + extended[end:] == plain


def test_report_without_the_section_renders_without_any_adr_text(tmp_path, capsys):
    code, html = _run(tmp_path, {"scores": {"overall": 0.8}}, capsys)

    assert code == 0 and "ADR drift" not in html and "adr-drift-h" not in html


@pytest.mark.parametrize("fix", ["", "   ", None])
def test_empty_suggested_fix_exits_1_and_writes_nothing(tmp_path, capsys, fix):
    finding = _finding(suggested_fix=fix)
    report = {"scores": {"overall": 0.8}, "adr_drift": _section([finding])}

    code, html = _run(tmp_path, report, capsys)

    assert code == 1 and html == ""


def test_missing_suggested_fix_key_exits_1(tmp_path, capsys):
    finding = _finding()
    del finding["suggested_fix"]

    code, _ = _run(tmp_path, {"scores": {"overall": 0.8}, "adr_drift": _section([finding])}, capsys)

    assert code == 1


def test_validation_reports_the_finding_id():
    errors = report_adr.validate_adr_drift({"adr_drift": _section([_finding(suggested_fix="")])})

    assert errors == [
        "adr_drift finding abc123def456 (adr-duplicate-number) has an empty suggested_fix"
    ]
    assert report_adr.validate_adr_drift({"adr_drift": _section([_finding()])}) == []
    assert report_adr.validate_adr_drift({}) == []


def test_adr_only_report_renders_without_a_scorecard(tmp_path, capsys):
    code, html = _run(tmp_path, {"adr_drift": _section([_finding()])}, capsys)

    assert code == 0
    assert "adr-duplicate-number" in html and "share-png" not in html and "Overall" not in html


def test_adr_only_report_with_an_empty_fix_exits_1(tmp_path, capsys):
    code, html = _run(tmp_path, {"adr_drift": _section([_finding(suggested_fix="")])}, capsys)

    assert code == 1 and html == ""


def test_report_with_neither_scores_nor_adr_drift_still_exits_1(tmp_path, capsys):
    code, _ = _run(tmp_path, {"title": "x"}, capsys)

    assert code == 1


def test_finding_text_is_escaped(tmp_path):
    finding = _finding(suggested_fix="<script>alert(1)</script>", evidence={"path": "<b>x</b>"})

    html = report_adr.render_adr_drift({"adr_drift": _section([finding])}, esc)

    assert "<script>alert(1)</script>" not in html and "&lt;script&gt;" in html
    assert "<b>x</b>" not in html


@pytest.mark.parametrize(
    ("align", "expected"),
    [
        ({"status": "absent"}, "align not installed. Deterministic check complete."),
        (
            {"status": "detected", "command_hint": "DO_NOT_TRACK=1 align adr"},
            "align found. Not run. To cross-check: `DO_NOT_TRACK=1 align adr`.",
        ),
        (
            {"status": "no_graph"},
            "align found, no graph. Not built, because building reads api.github.com",
        ),
        ({"status": "failed", "exit_code": 3, "text": "boom"}, "align failed (exit 3): boom"),
    ],
)
def test_align_state_lines(align, expected):
    html = report_adr.render_adr_drift({"adr_drift": _section([], align)}, esc)

    assert esc(expected) in html


def test_align_ran_prints_advisory_text_under_its_own_heading():
    align = {"status": "ran", "text": "ADR-001 listed", "advisory_note": "advisory; naming differs"}

    html = report_adr.render_adr_drift({"adr_drift": _section([], align)}, esc)

    assert "<h4>align cross-check</h4>" in html and "ADR-001 listed" in html
    assert "advisory; naming differs" in html


def test_skipped_section_states_the_reason():
    html = report_adr.render_adr_drift({"adr_drift": {"skipped": "all-conversations run"}}, esc)

    assert "ADR drift was not run: all-conversations run" in html


def test_truncated_history_is_disclosed():
    section = _section([])
    section["repos"][0]["truncated"] = True

    html = report_adr.render_adr_drift({"adr_drift": section}, esc)

    assert "history truncated at the commit limit" in html


def test_draft_links_are_relative_only():
    findings = [
        _finding(id="a1", draft="proposed/adr/ADR-124-x.md"),
        _finding(id="b2", draft="/etc/passwd"),
        _finding(id="c3", draft="https://evil.example/x"),
    ]

    html = report_adr.render_adr_drift({"adr_drift": _section(findings)}, esc)

    assert '<a href="proposed/adr/ADR-124-x.md">' in html
    assert 'href="/etc/passwd"' not in html and 'href="https://evil.example/x"' not in html
