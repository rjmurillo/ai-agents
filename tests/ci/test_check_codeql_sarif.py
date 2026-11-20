"""Tests for ``scripts/ci/check_codeql_sarif.py`` (issues #3529, #3926)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.ci import check_codeql_sarif as ccs

REPO_ROOT = Path(__file__).resolve().parents[2]

WORKFLOW = REPO_ROOT / ".github" / "workflows" / "codeql-analysis.yml"


def _sarif(*, rules: list[dict], results: list[dict]) -> dict:
    return {"runs": [{"tool": {"driver": {"rules": rules}}, "results": results}]}


def _error(rule_id: str, text: str = "boom") -> dict:
    return {"level": "error", "ruleId": rule_id, "message": {"text": text}}


def _rule(rule_id: str, severity: object) -> dict:
    return {"id": rule_id, "properties": {"security-severity": severity}}


class TestSeverityIsNumeric:
    """Regression guard for issue #3926."""

    def test_a_cvss_ten_finding_is_critical(self) -> None:
        doc = _sarif(rules=[_rule("r1", "10.0")], results=[_error("r1")])
        tally = ccs.grade([("a.sarif", doc)])
        assert tally.critical == 1
        assert tally.high == 0

    def test_a_cvss_nine_point_three_finding_is_critical(self) -> None:
        doc = _sarif(rules=[_rule("r1", "9.3")], results=[_error("r1")])
        assert ccs.grade([("a.sarif", doc)]).critical == 1

    def test_a_cvss_eight_point_nine_finding_is_high(self) -> None:
        doc = _sarif(rules=[_rule("r1", "8.9")], results=[_error("r1")])
        tally = ccs.grade([("a.sarif", doc)])
        assert tally.critical == 0
        assert tally.high == 1

    def test_exactly_nine_is_critical(self) -> None:
        doc = _sarif(rules=[_rule("r1", "9.0")], results=[_error("r1")])
        assert ccs.grade([("a.sarif", doc)]).critical == 1

    def test_a_numeric_severity_also_works(self) -> None:
        doc = _sarif(rules=[_rule("r1", 9.8)], results=[_error("r1")])
        assert ccs.grade([("a.sarif", doc)]).critical == 1

    @pytest.mark.parametrize("bad", ["", "n/a", None, [], {}])
    def test_an_unparseable_severity_is_high_not_critical(self, bad: object) -> None:
        doc = _sarif(rules=[_rule("r1", bad)], results=[_error("r1")])
        tally = ccs.grade([("a.sarif", doc)])
        assert tally.critical == 0
        assert tally.high == 1

    @pytest.mark.parametrize("flag", [True, False])
    def test_a_boolean_severity_is_no_severity_not_a_number(self, flag: bool) -> None:
        """A bool is an int in Python. Reporting 1.0 would fabricate a severity."""
        assert ccs._severity(flag) is None

    def test_a_real_number_survives_the_type_guard(self) -> None:
        assert ccs._severity(7.5) == 7.5

    def test_a_missing_rule_is_high_not_critical(self) -> None:
        doc = _sarif(rules=[], results=[_error("unknown-rule")])
        tally = ccs.grade([("a.sarif", doc)])
        assert tally.critical == 0
        assert tally.high == 1

    def test_a_rule_without_properties_is_high(self) -> None:
        doc = _sarif(rules=[{"id": "r1"}], results=[_error("r1")])
        assert ccs.grade([("a.sarif", doc)]).high == 1


class TestGrading:
    @pytest.mark.parametrize(
        ("result_fields", "default_level", "counts", "label"),
        [
            ({}, "error", (1, 0), "CRITICAL"),
            ({}, "warning", (0, 0), "MEDIUM"),
            ({}, None, (0, 0), "MEDIUM"),
            ({"level": "warning"}, "error", (0, 0), "MEDIUM"),
            ({"level": "error"}, "warning", (1, 0), "CRITICAL"),
            ({"level": "note"}, "error", (0, 0), None),
            ({"kind": "pass"}, "error", (0, 0), None),
        ],
    )
    def test_effective_level(self, result_fields, default_level, counts, label):
        """D22 A applies SARIF level precedence before grading."""
        rule = _rule("r1", "9.0")
        if default_level is not None:
            rule["defaultConfiguration"] = {"level": default_level}
        doc = _sarif(rules=[rule], results=[{"ruleId": "r1", **result_fields}])
        tally = ccs.grade([("a.sarif", doc)])
        assert (tally.critical, tally.high) == counts
        assert tally.lines[1:] == ([f"  {label}: r1 - "] if label else [])

    def test_rule_index_and_extension_determine_inherited_severity(self):
        """D22 A resolves indexes within their original tool component."""
        rule = _rule("r1", "10.0") | {"defaultConfiguration": {"level": "error"}}
        doc = _sarif(
            rules=[_rule("r1", "1.0")],
            results=[{"rule": {"index": 1, "toolComponent": {"index": 0}}}],
        )
        doc["runs"][0]["tool"]["extensions"] = [{"rules": [_rule("other", 1), rule]}]
        tally = ccs.grade([("a.sarif", doc)])
        assert (tally.critical, tally.high) == (1, 0)
        assert tally.lines[-1] == "  CRITICAL: r1 - "

    @pytest.mark.parametrize(
        "reference",
        [
            {"ruleIndex": 1},
            {"ruleId": "r1"},
            {"ruleIndex": -1, "ruleId": "r1"},
            {"ruleIndex": True, "ruleId": "r1"},
        ],
    )
    def test_legacy_rule_references(self, reference: dict[str, object]) -> None:
        """Rule indexes use positions in the original array."""
        rule = _rule("r1", "10.0") | {"defaultConfiguration": {"level": "error"}}
        doc = _sarif(rules=[{}, rule], results=[reference])
        assert ccs.grade([("a.sarif", doc)]).lines[-1] == "  CRITICAL: r1 - "

    def test_rule_id_can_resolve_an_extension(self) -> None:
        rule = _rule("ext/r1", 9.3) | {"defaultConfiguration": {"level": "error"}}
        doc = _sarif(rules=[], results=[{"ruleId": "ext/r1"}])
        doc["runs"][0]["tool"]["extensions"] = [{"rules": [rule]}]
        assert ccs.grade([("a.sarif", doc)]).critical == 1

    @pytest.mark.parametrize("score", ["7.5", 0, None, "unscored"])
    def test_result_severity_overrides_inherited_severity(self, score: object) -> None:
        result = _error("r1") | {"properties": {"security-severity": score}}
        doc = _sarif(rules=[_rule("r1", "10.0")], results=[result])
        assert ccs.grade([("a.sarif", doc)]).high == 1

    def test_result_severity_works_without_a_rule(self) -> None:
        result = _error("r1") | {"properties": {"security-severity": "9.5"}}
        doc = _sarif(rules=[], results=[result])
        assert ccs.grade([("a.sarif", doc)]).critical == 1

    def test_unresolved_rule_defaults_to_warning(self) -> None:
        doc = _sarif(rules=[], results=[{"ruleId": "r1", "ruleIndex": 3}])
        assert ccs.grade([("a.sarif", doc)]).lines[-1] == "  MEDIUM: r1 - "

    def test_warnings_are_counted_but_not_graded(self) -> None:
        doc = _sarif(
            rules=[], results=[{"level": "warning", "ruleId": "w1", "message": {"text": "m"}}]
        )
        tally = ccs.grade([("a.sarif", doc)])
        assert (tally.total, tally.critical, tally.high) == (1, 0, 0)
        assert "  MEDIUM: w1 - m" in tally.lines

    def test_notes_are_counted_but_produce_no_line(self) -> None:
        doc = _sarif(rules=[], results=[{"level": "note", "ruleId": "n1"}])
        tally = ccs.grade([("a.sarif", doc)])
        assert tally.total == 1
        assert not any("n1" in line for line in tally.lines)

    def test_findings_accumulate_across_files(self) -> None:
        doc = _sarif(rules=[_rule("r1", "9.5")], results=[_error("r1")])
        tally = ccs.grade([("a.sarif", doc), ("b.sarif", doc)])
        assert tally.critical == 2
        assert tally.total == 2

    def test_each_file_is_announced(self) -> None:
        tally = ccs.grade([("a.sarif", _sarif(rules=[], results=[]))])
        assert tally.lines == ["Analyzing: a.sarif"]

    def test_a_missing_message_does_not_crash(self) -> None:
        doc = _sarif(rules=[_rule("r1", "9.5")], results=[{"level": "error", "ruleId": "r1"}])
        assert "  CRITICAL: r1 - " in ccs.grade([("a.sarif", doc)]).lines

    def test_malformed_runs_are_skipped(self) -> None:
        tally = ccs.grade([("a.sarif", {"runs": ["not-a-dict", None]})])
        assert tally.total == 0

    def test_a_document_without_runs_is_empty(self) -> None:
        assert ccs.grade([("a.sarif", {})]).total == 0


class TestRenderSummary:
    def test_critical_renders_the_caution_admonition(self) -> None:
        text = ccs.render_summary(ccs.Tally(critical=1, high=0, total=1))
        assert "[!CAUTION]" in text
        assert "Merge blocked." in text

    def test_high_only_renders_the_warning_admonition(self) -> None:
        text = ccs.render_summary(ccs.Tally(critical=0, high=2, total=2))
        assert "[!WARNING]" in text
        assert "[!CAUTION]" not in text

    def test_clean_renders_the_tip_admonition(self) -> None:
        assert "[!TIP]" in ccs.render_summary(ccs.Tally())

    def test_the_table_carries_the_counts(self) -> None:
        text = ccs.render_summary(ccs.Tally(critical=3, high=4, total=9))
        assert "| Critical | 3 |" in text
        assert "| High | 4 |" in text
        assert "| **Total** | **9** |" in text


class TestLoadDocuments:
    def test_sarif_files_are_found_recursively(self, tmp_path: Path) -> None:
        nested = tmp_path / "leg1"
        nested.mkdir()
        (nested / "a.sarif").write_text(json.dumps(_sarif(rules=[], results=[])), encoding="utf-8")
        assert [name for name, _ in ccs.load_documents(tmp_path)] == ["a.sarif"]

    def test_unparseable_files_are_skipped_not_fatal(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        (tmp_path / "bad.sarif").write_text("{not json", encoding="utf-8")
        assert ccs.load_documents(tmp_path) == []
        assert "::warning::" in capsys.readouterr().out

    def test_non_sarif_files_are_ignored(self, tmp_path: Path) -> None:
        (tmp_path / "a.json").write_text("{}", encoding="utf-8")
        assert ccs.load_documents(tmp_path) == []


class TestCli:
    @pytest.mark.parametrize(("score", "expected_exit"), [("7.5", 0), ("9.0", 1), ("10.0", 1)])
    def test_inherited_error_uses_existing_threshold(self, tmp_path, capsys, score, expected_exit):
        """D22 A blocks inherited critical results and reports inherited high results."""
        rule = _rule("r1", score) | {"defaultConfiguration": {"level": "error"}}
        doc = _sarif(rules=[rule], results=[{"ruleId": "r1"}])
        (tmp_path / "a.sarif").write_text(json.dumps(doc), encoding="utf-8")
        assert ccs.main(["--sarif-dir", str(tmp_path)]) == expected_exit
        assert ("CRITICAL: r1" if expected_exit else "HIGH: r1") in capsys.readouterr().out

    def test_an_empty_directory_exits_nonzero_with_a_message(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        assert ccs.main(["--sarif-dir", str(tmp_path)]) == 1
        assert "No SARIF files found" in capsys.readouterr().out

    def test_a_missing_directory_exits_nonzero(self, tmp_path: Path) -> None:
        assert ccs.main(["--sarif-dir", str(tmp_path / "nope")]) == 1

    def test_an_unparseable_sarif_file_exits_nonzero(self, tmp_path: Path) -> None:
        (tmp_path / "bad.sarif").write_text("{not json", encoding="utf-8")
        assert ccs.main(["--sarif-dir", str(tmp_path)]) == 1

    def test_a_critical_finding_fails_the_job(self, tmp_path: Path) -> None:
        doc = _sarif(rules=[_rule("r1", "10.0")], results=[_error("r1")])
        (tmp_path / "a.sarif").write_text(json.dumps(doc), encoding="utf-8")
        assert ccs.main(["--sarif-dir", str(tmp_path)]) == 1

    def test_a_high_finding_does_not_fail_the_job(self, tmp_path: Path) -> None:
        doc = _sarif(rules=[_rule("r1", "7.5")], results=[_error("r1")])
        (tmp_path / "a.sarif").write_text(json.dumps(doc), encoding="utf-8")
        assert ccs.main(["--sarif-dir", str(tmp_path)]) == 0

    def test_the_summary_is_appended(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        doc = _sarif(rules=[], results=[])
        (tmp_path / "a.sarif").write_text(json.dumps(doc), encoding="utf-8")
        summary = tmp_path / "summary.md"
        summary.write_text("existing\n", encoding="utf-8")
        monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
        ccs.main(["--sarif-dir", str(tmp_path)])
        text = summary.read_text(encoding="utf-8")
        assert text.startswith("existing\n")
        assert "## CodeQL Analysis Summary" in text

    def test_the_sarif_dir_argument_is_required(self) -> None:
        with pytest.raises(SystemExit):
            ccs.main([])


class TestWorkflowWiring:
    def test_the_workflow_invokes_the_script(self) -> None:
        assert "scripts/ci/check_codeql_sarif.py" in WORKFLOW.read_text(encoding="utf-8")

    def test_the_replaced_powershell_is_gone(self) -> None:
        text = WORKFLOW.read_text(encoding="utf-8")
        assert "$criticalCount" not in text
        assert "ConvertFrom-Json" not in text
        assert "security-severity" not in text
