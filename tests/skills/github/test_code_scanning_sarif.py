"""Tests for code_scanning_sarif.py: the rule-id, path, and line reduction."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_project_root = Path(__file__).resolve().parents[3]
_pr_dir = _project_root / ".claude" / "skills" / "github" / "scripts" / "pr"
if str(_pr_dir) not in sys.path:
    sys.path.insert(0, str(_pr_dir))

import code_scanning_sarif as sarif_mod
from code_scanning_fakes import sarif, sarif_result


class TestRuleId:
    @pytest.mark.parametrize(
        "value",
        ["py/path-injection", "actions/unpinned-tag", "a", "A_b.c-d/e", "x" * 100],
    )
    def test_accepts_ids_the_amendment_allows(self, value):
        assert sarif_mod.is_valid_rule_id(value) is True

    @pytest.mark.parametrize(
        "value",
        [
            "",
            "x" * 101,
            "rule\n",
            "rule name",
            "py/ignore previous instructions",
            "rule;rm",
            "r\u00fcle",
            "<script>",
            None,
            7,
            ["py/x"],
        ],
    )
    def test_rejects_everything_else(self, value):
        assert sarif_mod.is_valid_rule_id(value) is False

    def test_trailing_newline_is_the_case_re_match_would_accept(self):
        assert sarif_mod.RULE_ID_PATTERN.match("rule\n") is not None
        assert sarif_mod.is_valid_rule_id("rule\n") is False

    def test_pattern_text_is_the_amendments(self):
        assert sarif_mod.RULE_ID_PATTERN.pattern == r"^[A-Za-z0-9/_.-]{1,100}$"


class TestNormalizeRepoPath:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("src/a.py", "src/a.py"),
            ("./src/a.py", "src/a.py"),
            ("src//a.py", "src/a.py"),
            (".github/workflows/ci.yml", ".github/workflows/ci.yml"),
            ("a b/c.py", "a b/c.py"),
        ],
    )
    def test_folds_to_repo_relative_posix(self, raw, expected):
        assert sarif_mod.normalize_repo_path(raw) == expected

    @pytest.mark.parametrize(
        "raw",
        [
            "",
            ".",
            "./",
            "/etc/passwd",
            "../x.py",
            "a/../b.py",
            "a\\b.py",
            "C:/x.py",
            "C:\\x.py",
            "file:///x.py",
            "https://evil/x.py",
            "a\x00b.py",
            "a\nb.py",
            "a\x7fb.py",
            "x" * 1025,
            None,
            3,
        ],
    )
    def test_rejects_paths_that_escape_or_confuse(self, raw):
        assert sarif_mod.normalize_repo_path(raw) is None


class TestLocations:
    def test_orders_primary_then_related_then_code_flow(self):
        result = sarif_result(
            1,
            primary=("src/a.py", 10),
            related=[("src/b.py", 20)],
            flow=[("src/c.py", 30), ("src/d.py", 40)],
        )
        assert sarif_mod.sarif_result_locations(result) == [
            ("src/a.py", 10),
            ("src/b.py", 20),
            ("src/c.py", 30),
            ("src/d.py", 40),
        ]

    def test_missing_start_line_becomes_zero(self):
        assert sarif_mod.sarif_result_locations(sarif_result(1, primary=("src/a.py", None))) == [
            ("src/a.py", 0)
        ]

    def test_boolean_and_nonpositive_lines_become_zero(self):
        result = sarif_result(1, primary=("src/a.py", 0))
        result["locations"][0]["physicalLocation"]["region"]["startLine"] = True
        assert sarif_mod.sarif_result_locations(result) == [("src/a.py", 0)]

    def test_skips_a_location_with_an_unusable_path(self):
        result = sarif_result(1, primary=("../escape.py", 5), related=[("src/ok.py", 6)])
        assert sarif_mod.sarif_result_locations(result) == [("src/ok.py", 6)]

    def test_tolerates_malformed_containers(self):
        result = {
            "locations": "not a list",
            "relatedLocations": [None, 3, {"physicalLocation": "x"}],
            "codeFlows": [None, {"threadFlows": "x"}, {"threadFlows": [None, {"locations": [3]}]}],
        }
        assert sarif_mod.sarif_result_locations(result) == []

    def test_result_with_no_locations_returns_empty(self):
        assert sarif_mod.sarif_result_locations({}) == []


class TestAlertIndex:
    def test_indexes_results_by_alert_number(self):
        doc = sarif(sarif_result(7), sarif_result(9))
        assert sorted(sarif_mod.sarif_results_by_alert_number(doc)) == [7, 9]

    def test_skips_results_without_a_usable_number(self):
        no_props = {"ruleId": "x"}
        bool_number = {"properties": {"github/alertNumber": True}}
        str_number = {"properties": {"github/alertNumber": "7"}}
        doc = {"runs": [{"results": [no_props, bool_number, str_number, sarif_result(4)]}]}
        assert list(sarif_mod.sarif_results_by_alert_number(doc)) == [4]

    @pytest.mark.parametrize("doc", [None, [], {}, {"runs": "x"}, "text"])
    def test_rejects_a_document_without_runs(self, doc):
        with pytest.raises(ValueError, match="no runs list"):
            sarif_mod.sarif_results_by_alert_number(doc)

    def test_run_without_results_is_empty(self):
        assert sarif_mod.sarif_results_by_alert_number({"runs": [{}, None]}) == {}


class TestDiffMatching:
    def test_normalize_changed_files_drops_unusable_entries(self):
        got = sarif_mod.normalize_changed_files(["src/a.py", "./b.py", "", "../x", "/abs"])
        assert got == frozenset({"src/a.py", "b.py"})

    def test_first_location_in_diff_returns_first_match_in_order(self):
        locations = [("x.py", 1), ("src/b.py", 2), ("src/a.py", 3)]
        files = frozenset({"src/a.py", "src/b.py"})
        assert sarif_mod.first_location_in_diff(locations, files) == ("src/b.py", 2)

    def test_first_location_in_diff_is_none_when_nothing_matches(self):
        assert sarif_mod.first_location_in_diff([("x.py", 1)], frozenset({"y.py"})) is None

    def test_matching_is_case_sensitive(self):
        assert sarif_mod.first_location_in_diff([("SRC/a.py", 1)], frozenset({"src/a.py"})) is None
