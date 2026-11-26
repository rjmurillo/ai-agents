"""render_report.py and report_adr.py: the adr_drift section, read from scan files by path."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
import report_adr
from adr_drift_helpers import symlink_or_skip
from render_report import esc, main, render_page

SCAN = "adr_drift/my-repo.json"


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


def _resolved(findings: list[dict[str, Any]], **repo_extra: Any) -> dict[str, Any]:
    repo = {
        "repo": "my-repo",
        "head": "abc",
        "examined": 300,
        "truncated": False,
        "findings": findings,
        **repo_extra,
    }
    return {"repos": [repo]}


def _write(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def _scan_file(root: Path, findings: list[dict[str, Any]], **extra: Any) -> None:
    scan = {"repo": "/r", "head": "abc", "examined": 300, "truncated": False, **extra}
    _write(root / SCAN, {**scan, "findings": findings})


def _section(**entry: Any) -> dict[str, Any]:
    return {"repos": [{"repo": "my-repo", "scan": SCAN, **entry}]}


def _run(root: Path, report: dict[str, Any], capsys) -> tuple[int, str, str]:
    _write(root / "report.json", report)
    code = 0
    try:
        main([str(root / "report.json")])
    except SystemExit as exc:
        code = int(exc.code or 0)
    err = capsys.readouterr().err
    html = root / "report.html"
    return code, html.read_text(encoding="utf-8") if html.is_file() else "", err


def _adr_only(**section: Any) -> dict[str, Any]:
    return {"mode": "adr_only", "adr_drift": section or _section()}


def test_section_renders_counts_findings_and_the_fix_from_the_scan_file(tmp_path, capsys):
    _scan_file(tmp_path, [_finding()])

    code, html, _ = _run(tmp_path, {"scores": {"overall": 0.8}, "adr_drift": _section()}, capsys)

    assert code == 0
    assert "ADR drift" in html and "adr-duplicate-number" in html
    assert "Rename the later file to 124." in html and "docs/adr/ADR-001-b.md:3" in html
    assert "1 findings: 0 setup, 1 numbering, 0 links, 0 history. 300 commits examined." in html


def test_findings_retyped_into_report_json_are_ignored(tmp_path, capsys):
    _scan_file(tmp_path, [_finding()])
    stale = _section(findings=[_finding(kind="adr-broken-link", suggested_fix="retyped")])

    code, html, _ = _run(tmp_path, {"mode": "adr_only", "adr_drift": stale}, capsys)

    assert code == 0 and "adr-duplicate-number" in html
    assert "adr-broken-link" not in html and "retyped" not in html


def test_page_without_the_section_equals_the_page_with_the_section_cut_out():
    base = {"scores": {"overall": 0.8}, "grade": "B"}

    plain = render_page(base)
    extended = render_page({**base, "adr_drift": _resolved([_finding()])})

    start = extended.index('\n<section aria-labelledby="adr-drift-h">')
    end = extended.index("\n</main>")
    assert extended[:start] + extended[end:] == plain


def test_report_without_the_section_renders_without_any_adr_text(tmp_path, capsys):
    code, html, _ = _run(tmp_path, {"scores": {"overall": 0.8}}, capsys)

    assert code == 0 and "ADR drift" not in html and "adr-drift-h" not in html


@pytest.mark.parametrize("fix", ["", "   ", None])
def test_empty_suggested_fix_exits_1_and_writes_nothing(tmp_path, capsys, fix):
    _scan_file(tmp_path, [_finding(suggested_fix=fix)])

    code, html, err = _run(tmp_path, {"scores": {"overall": 0.8}, "adr_drift": _section()}, capsys)

    assert code == 1 and html == "" and "empty suggested_fix" in err


def test_missing_suggested_fix_key_exits_1(tmp_path, capsys):
    finding = _finding()
    del finding["suggested_fix"]
    _scan_file(tmp_path, [finding])

    code, _, _ = _run(tmp_path, {"scores": {"overall": 0.8}, "adr_drift": _section()}, capsys)

    assert code == 1


def test_validation_reports_the_finding_id():
    errors = report_adr.validate_adr_drift({"adr_drift": _resolved([_finding(suggested_fix="")])})

    assert errors == [
        "adr_drift finding abc123def456 (adr-duplicate-number) has an empty suggested_fix"
    ]
    assert report_adr.validate_adr_drift({"adr_drift": _resolved([_finding()])}) == []
    assert report_adr.validate_adr_drift({}) == []


def test_marked_adr_only_report_renders_without_a_scorecard(tmp_path, capsys):
    _scan_file(tmp_path, [_finding()])

    code, html, _ = _run(tmp_path, _adr_only(), capsys)

    assert code == 0
    assert "adr-duplicate-number" in html and "share-png" not in html and "Overall" not in html


def test_marked_adr_only_report_with_an_empty_fix_exits_1(tmp_path, capsys):
    _scan_file(tmp_path, [_finding(suggested_fix="")])

    code, html, _ = _run(tmp_path, _adr_only(), capsys)

    assert code == 1 and html == ""


def test_an_adr_drift_section_without_the_marker_still_needs_a_score(tmp_path, capsys):
    _scan_file(tmp_path, [_finding()])

    code, html, err = _run(tmp_path, {"adr_drift": _section()}, capsys)

    assert code == 1 and html == "" and "scores.overall" in err


def test_the_marker_without_an_adr_drift_object_exits_1(tmp_path, capsys):
    code, _, err = _run(tmp_path, {"mode": "adr_only"}, capsys)

    assert code == 1 and "needs an adr_drift object" in err


def test_report_with_neither_scores_nor_adr_drift_still_exits_1(tmp_path, capsys):
    code, _, _ = _run(tmp_path, {"title": "x"}, capsys)

    assert code == 1


def test_finding_text_is_escaped():
    finding = _finding(suggested_fix="<script>alert(1)</script>", evidence={"path": "<b>x</b>"})

    html = report_adr.render_adr_drift({"adr_drift": _resolved([finding])}, esc)

    assert "<script>alert(1)</script>" not in html and "&lt;script&gt;" in html
    assert "<b>x</b>" not in html


def test_skipped_section_states_the_reason():
    html = report_adr.render_adr_drift({"adr_drift": {"skipped": "all-conversations run"}}, esc)

    assert "ADR drift was not run: all-conversations run" in html


def test_a_skipped_section_needs_no_scan_file(tmp_path, capsys):
    code, html, _ = _run(tmp_path, _adr_only(skipped="all-conversations run"), capsys)

    assert code == 0 and "ADR drift was not run" in html


def test_truncated_history_is_disclosed():
    html = report_adr.render_adr_drift({"adr_drift": _resolved([], truncated=True)}, esc)

    assert "history truncated at the commit limit" in html


def test_truncation_and_read_errors_flow_from_the_scan_file(tmp_path, capsys):
    errors = [{"path": "docs/adr/ADR-002-<x>.md", "error": "permission denied"}]
    _scan_file(tmp_path, [], truncated=True, read_errors=errors)

    code, html, _ = _run(tmp_path, _adr_only(), capsys)

    assert code == 0 and "history truncated at the commit limit" in html
    assert "Unreadable paths, not checked" in html and "permission denied" in html
    assert "ADR-002-&lt;x&gt;.md" in html and "ADR-002-<x>.md" not in html


@pytest.mark.parametrize("name", ["../outside.json", "/etc/hostname"], ids=["parent", "absolute"])
def test_a_scan_path_outside_the_report_directory_exits_2(tmp_path, capsys, name):
    root = tmp_path / "run"
    _write(tmp_path / "outside.json", {"findings": []})

    code, html, err = _run(root, _adr_only(repos=[{"repo": "r", "scan": name}]), capsys)

    assert code == 2 and html == "" and "outside the report directory" in err


def test_a_nul_byte_in_the_scan_path_exits_2_without_a_traceback(tmp_path, capsys):
    root = tmp_path / "run"

    code, html, err = _run(root, _adr_only(repos=[{"repo": "r", "scan": "a\0b.json"}]), capsys)

    assert code == 2 and html == "" and "error:" in err
    assert "Traceback" not in err and "cannot read adr_drift scan" in err


def test_a_nul_byte_in_the_decisions_path_exits_2_without_a_traceback(tmp_path, capsys):
    root = tmp_path / "run"
    _scan_file(root, [])

    code, html, err = _run(
        root, _adr_only(repos=[{"repo": "r", "scan": SCAN, "decisions": "a\0"}]), capsys
    )

    assert code == 2 and html == "" and "error:" in err and "Traceback" not in err


def test_a_symlink_that_leaves_the_report_directory_exits_2(tmp_path, capsys):
    root = tmp_path / "run"
    (root / "adr_drift").mkdir(parents=True)
    _write(tmp_path / "outside.json", {"findings": []})
    symlink_or_skip(root / SCAN, tmp_path / "outside.json")

    code, _, err = _run(root, _adr_only(), capsys)

    assert code == 2 and "outside the report directory" in err


@pytest.mark.parametrize(
    ("setup", "message"),
    [
        ("missing", "cannot read adr_drift scan"),
        ("not-json", "cannot read adr_drift scan"),
        ("no-findings", "holds no findings list"),
        ("not-an-object", "holds no findings list"),
    ],
)
def test_an_unusable_scan_file_exits_2(tmp_path, capsys, setup, message):
    if setup == "not-json":
        (tmp_path / "adr_drift").mkdir()
        (tmp_path / SCAN).write_text("{nope", encoding="utf-8")
    elif setup == "no-findings":
        _write(tmp_path / SCAN, {"head": "abc"})
    elif setup == "not-an-object":
        _write(tmp_path / SCAN, [1, 2])

    code, html, err = _run(tmp_path, _adr_only(), capsys)

    assert code == 2 and html == "" and message in err


@pytest.mark.parametrize("label", ["adr_drift scan", "adr_drift decisions"])
def test_an_input_file_over_the_size_cap_exits_2(tmp_path, capsys, monkeypatch, label):
    """The cap sits between the two file sizes, so only the named file is over it."""
    decisions = "adr_drift/decisions.json"
    _scan_file(tmp_path, [_finding()])
    padding = "x" * 4000 if label.endswith("decisions") else ""
    _write(tmp_path / decisions, {"candidates": [], "pad": padding})
    sizes = sorted((tmp_path / name).stat().st_size for name in (SCAN, decisions))
    monkeypatch.setattr(report_adr, "MAX_FILE_BYTES", sizes[0])

    report = _adr_only(**_section(decisions=decisions))
    if label.endswith("scan"):
        _write(tmp_path / SCAN, {"findings": [_finding()], "pad": "y" * 8000})
    code, html, err = _run(tmp_path, report, capsys)

    assert code == 2 and html == "" and f"{label} " in err and "larger than" in err


def test_a_scan_file_nested_past_the_parser_limit_exits_2(tmp_path, capsys):
    (tmp_path / "adr_drift").mkdir()
    (tmp_path / SCAN).write_text("[" * 200_000 + "]" * 200_000, encoding="utf-8")

    code, html, err = _run(tmp_path, _adr_only(), capsys)

    assert code == 2 and html == "" and "cannot read adr_drift scan" in err


@pytest.mark.parametrize("name", [7, "", "   "], ids=["number", "empty", "blank"])
def test_a_scan_path_that_is_not_a_path_string_exits_2(tmp_path, capsys, name):
    code, html, err = _run(tmp_path, _adr_only(repos=[{"repo": "r", "scan": name}]), capsys)

    assert code == 2 and html == "" and "must be a path string" in err


def test_a_section_with_neither_skipped_nor_repos_exits_2(tmp_path, capsys):
    code, _, err = _run(tmp_path, _adr_only(repos=[]), capsys)

    assert code == 2 and "neither `skipped` nor a repos entry" in err


def test_a_report_html_that_cannot_be_written_exits_2_for_adr_only_and_scored_reports(
    tmp_path, capsys
):
    _scan_file(tmp_path, [_finding()])
    (tmp_path / "report.html").mkdir()

    adr_only = _run(tmp_path, _adr_only(), capsys)
    scored = _run(tmp_path, {"scores": {"overall": 0.8}, "adr_drift": _section()}, capsys)

    assert adr_only[0] == scored[0] == 2
    assert "cannot write" in adr_only[2] and "cannot write" in scored[2]


def _bootstrap_candidate(**source: str) -> dict[str, Any]:
    """One candidate in skill-bootstrap's `bootstrap_adr.py scan` output shape."""
    return {
        "id": "c-aaaaaaa",
        "kind": "commit",
        "title": "switch <b>to</b> uv",
        "reason": "faster installs",
        "excerpt": "body",
        "date": "2026-11-20",
        "source": source or {"sha": "a" * 40, "pr_url": "https://example.com/pull/7"},
        "signals": [],
    }


def _render_decisions(tmp_path, capsys, payload):
    _scan_file(tmp_path, [])
    _write(tmp_path / "adr_drift" / "decisions.json", payload)
    entry = _section(decisions="adr_drift/decisions.json")["repos"][0]
    return _run(tmp_path, _adr_only(repos=[entry]), capsys)


def test_bootstrap_candidates_render_as_an_escaped_table(tmp_path, capsys):
    code, html, _ = _render_decisions(tmp_path, capsys, {"candidates": [_bootstrap_candidate()]})

    assert code == 0 and "Candidate undocumented decisions for my-repo" in html
    assert "switch &lt;b&gt;to&lt;/b&gt; uv" in html and "<b>to</b>" not in html
    assert "https://example.com/pull/7" in html and "faster installs" in html
    assert "c-aaaaaaa" in html and "a" * 10 in html and "a" * 11 not in html


def test_a_candidate_source_url_shows_as_text_never_a_link(tmp_path, capsys):
    candidate = _bootstrap_candidate(sha="b" * 40, url="javascript:alert(1)")

    _, html, _ = _render_decisions(tmp_path, capsys, {"candidates": [candidate]})

    assert "javascript:alert(1)" in html and 'href="javascript' not in html
    assert '<th scope="col">Source URL</th>' in html


def test_a_null_reason_renders_empty_not_none(tmp_path, capsys):
    candidate = {**_bootstrap_candidate(), "reason": None}

    _, html, _ = _render_decisions(tmp_path, capsys, {"candidates": [candidate]})

    assert ">None<" not in html


@pytest.mark.parametrize("payload", [{"count": 0}, [_bootstrap_candidate()]])
def test_a_decisions_file_without_a_candidates_object_exits_2(tmp_path, capsys, payload):
    code, _, err = _render_decisions(tmp_path, capsys, payload)

    assert code == 2 and "has no `candidates` list" in err


def test_a_repo_without_decisions_renders_no_candidate_table(tmp_path, capsys):
    _scan_file(tmp_path, [_finding()])

    _, html, _ = _run(tmp_path, _adr_only(), capsys)

    assert "Candidate undocumented decisions" not in html


def test_a_history_finding_renders_its_commit_and_subject(tmp_path, capsys):
    history = _finding(
        kind="adr-contradiction-candidate",
        group="History",
        confidence="heuristic",
        evidence={"sha": "c" * 40, "subject": "refactor: drop <old> path", "adr": "docs/adr/x.md"},
        suggested_fix="Review the ADR against the commit.",
    )
    _scan_file(tmp_path, [history])

    code, html, _ = _run(tmp_path, _adr_only(), capsys)

    assert code == 0
    assert "c" * 10 + " refactor: drop &lt;old&gt; path" in html and "c" * 11 not in html


def test_a_decision_log_candidate_shows_its_source_file(tmp_path, capsys):
    candidate = {
        **_bootstrap_candidate(),
        "kind": "decision-log",
        "source": {"file": "docs/decisions.md", "entry_id": "use-uv"},
    }

    code, html, _ = _render_decisions(tmp_path, capsys, {"candidates": [candidate]})

    assert code == 0 and "<code>docs/decisions.md</code>" in html


def test_refused_paths_from_the_scan_file_are_listed(tmp_path, capsys):
    rejected = [{"path": "docs/adr", "reason": "resolves <outside> the repository"}]
    _scan_file(tmp_path, [], locate={"rejected": rejected})

    code, html, _ = _run(tmp_path, _adr_only(), capsys)

    assert code == 0 and "Refused paths, not checked:" in html
    assert "docs/adr: resolves &lt;outside&gt; the repository" in html


def test_a_scan_without_refused_paths_lists_none(tmp_path, capsys):
    _scan_file(tmp_path, [])

    _, html, _ = _run(tmp_path, _adr_only(), capsys)

    assert "Refused paths" not in html


def test_open_opens_an_adr_only_report_and_skips_the_share_hint(tmp_path, capsys, monkeypatch):
    import render_report

    opened: list[Path] = []
    monkeypatch.setattr(render_report, "open_report", lambda path: opened.append(path) or True)
    _scan_file(tmp_path, [])
    _write(tmp_path / "report.json", _adr_only())

    main([str(tmp_path / "report.json"), "--open"])

    out = capsys.readouterr().out
    assert opened == [tmp_path / "report.html"]
    assert "opened in the default browser" in out and "Share button" not in out


def test_without_open_an_adr_only_report_is_not_opened(tmp_path, capsys, monkeypatch):
    import render_report

    opened: list[Path] = []
    monkeypatch.setattr(render_report, "open_report", lambda path: opened.append(path) or True)
    _scan_file(tmp_path, [])
    _write(tmp_path / "report.json", _adr_only())

    main([str(tmp_path / "report.json")])

    assert opened == []
