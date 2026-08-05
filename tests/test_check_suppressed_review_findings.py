"""Tests for check_suppressed_review_findings.py."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

_ROOT = Path(__file__).resolve().parents[1]
_SCRIPTS_DIR = _ROOT / ".claude" / "skills" / "github" / "scripts" / "pr"


def _import_script(name: str):
    spec = importlib.util.spec_from_file_location(name, _SCRIPTS_DIR / f"{name}.py")
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


_mod = _import_script("check_suppressed_review_findings")
parse_suppressed_sections = _mod.parse_suppressed_sections
build_report = _mod.build_report
main = _mod.main


def _review(review_id: int, body: str) -> dict:
    return {
        "id": review_id,
        "node_id": f"PRR_{review_id}",
        "user": {"login": "copilot-pull-request-reviewer[bot]"},
        "state": "COMMENTED",
        "body": body,
        "submitted_at": "2026-08-03T00:00:00Z",
        "html_url": f"https://github.test/review/{review_id}",
    }


def test_parses_suppressed_findings_with_file_line_and_text() -> None:
    body = """<details>
<summary>Suppressed comments (2)</summary>

**src/app.py:10**
* First finding.

**docs/readme.md:42**
* Second finding.
</details>
"""
    sections = parse_suppressed_sections(body)
    assert sections[0]["declared_count"] == 2
    assert sections[0]["parsed_count"] == 2
    assert sections[0]["findings"][0] == {
        "path": "src/app.py",
        "line": 10,
        "text": "First finding.",
    }


def test_returns_zero_when_suppressed_section_is_absent() -> None:
    report = build_report("o", "r", 1, [_review(1, "No suppressed comments here.")])
    assert report["suppressed_count"] == 0
    assert report["parsed_finding_count"] == 0
    assert report["count_mismatches"] == []


def test_zero_count_section_does_not_create_findings() -> None:
    sections = parse_suppressed_sections(
        "<details>\n<summary>Suppressed comments (0)</summary>\n</details>"
    )
    assert sections == [{"declared_count": 0, "parsed_count": 0, "findings": []}]


def test_malformed_section_reports_count_mismatch() -> None:
    report = build_report(
        "o",
        "r",
        1,
        [_review(1, "<summary>Suppressed comments (3)</summary>\nnot a finding")],
    )
    assert report["suppressed_count"] == 3
    assert report["parsed_finding_count"] == 0
    assert report["count_mismatches"] == [
        {"review_id": 1, "section_index": 0, "declared_count": 3, "parsed_count": 0}
    ]


def test_multiple_reviews_are_aggregated() -> None:
    report = build_report(
        "o",
        "r",
        7,
        [
            _review(1, "<summary>Suppressed comments (1)</summary>\n**a.py:1**\n* A"),
            _review(2, "<summary>Suppressed comments: 2</summary>\n**b.py:2**\n* B"),
        ],
    )
    assert report["review_count"] == 2
    assert report["suppressed_review_count"] == 2
    assert report["suppressed_count"] == 3
    assert report["parsed_finding_count"] == 2


def test_main_exits_zero_and_emits_raw_json(capsys) -> None:
    page = [_review(1, "<summary>Suppressed comments (1)</summary>\n**a.py:1**\n* A")]
    completed = subprocess.CompletedProcess(
        args=[],
        returncode=0,
        stdout=json.dumps([page]),
        stderr="",
    )
    with patch("check_suppressed_review_findings.assert_gh_authenticated"), \
         patch(
             "check_suppressed_review_findings.resolve_repo_params",
             return_value=type("Repo", (), {"owner": "o", "repo": "r"})(),
         ), \
         patch("subprocess.run", return_value=completed):
        rc = main(["--pull-request", "99"])

    assert rc == 0
    output = json.loads(capsys.readouterr().out)
    assert output["suppressed_count"] == 1
    assert output["fetched_pages_complete"] is True


def test_pr_review_config_contains_suppressed_gate() -> None:
    config = (_ROOT / ".claude" / "commands" / "pr-review-config.yaml").read_text()
    assert "check_suppressed_review_findings.py --pull-request {pr}" in config
    assert "stdout-json.suppressed_count == 0" in config
