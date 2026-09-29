#!/usr/bin/env python3
"""Tests for backlog_provenance_report, the pure logic (issue #5702)."""

from __future__ import annotations

import json
import sys
from datetime import timedelta
from pathlib import Path

import pytest

TESTS_SKILLS_DIR = str(Path(__file__).resolve().parents[1])
if TESTS_SKILLS_DIR not in sys.path:
    sys.path.insert(0, TESTS_SKILLS_DIR)
TESTS_METRICS_DIR = str(Path(__file__).resolve().parent)
if TESTS_METRICS_DIR not in sys.path:
    sys.path.insert(0, TESTS_METRICS_DIR)

from backlog_test_helpers import ENDPOINT, NOW, record
from claude_skills_import import import_skill_script

rep = import_skill_script(".claude/skills/metrics/backlog_provenance_report.py")


def issue(number, at, login="owner", title="t", labels=()):
    return rep.Issue(number, title, login, at, frozenset(labels))


def make_report(records, days=7):
    backlog = rep.Backlog(issues=[rep.parse_record(item) for item in records])
    return rep.build_report(backlog, "o", "r", ENDPOINT, NOW - timedelta(days=days), NOW, NOW)


class TestParseTimestamp:
    def test_parses_z_suffix(self):
        assert rep.parse_timestamp("2026-09-29T12:00:00Z") == NOW

    @pytest.mark.parametrize("value", [None, "", 5, "not-a-date", "2026-09-29T12:00:00"])
    def test_rejects_bad_values(self, value):
        with pytest.raises(rep.ReportError) as err:
            rep.parse_timestamp(value)
        assert err.value.exit_code == 3


class TestParseRecord:
    def test_reads_fields_and_lowercases_labels(self):
        parsed = rep.parse_record(record(7, labels=("Source:Agent", "bug")))
        assert parsed.number == 7
        assert parsed.login == "owner"
        assert parsed.labels == frozenset({"source:agent", "bug"})

    def test_empty_labels_list_is_valid(self):
        raw = record(1)
        raw["labels"] = []
        assert rep.parse_record(raw).labels == frozenset()

    def test_null_title_becomes_empty(self):
        raw = record(1)
        raw["title"] = None
        assert rep.parse_record(raw).title == ""

    @pytest.mark.parametrize("labels", [None, "source:agent", {"name": "x"}])
    def test_malformed_labels_abort_with_exit_3(self, labels):
        raw = record(1)
        raw["labels"] = labels
        with pytest.raises(rep.ReportError, match="malformed labels") as err:
            rep.parse_record(raw)
        assert err.value.exit_code == 3

    @pytest.mark.parametrize("user", [None, "owner", {}, {"login": ""}, {"login": 5}])
    def test_missing_author_aborts_with_exit_3(self, user):
        raw = record(1)
        raw["user"] = user
        with pytest.raises(rep.ReportError, match="no author login") as err:
            rep.parse_record(raw)
        assert err.value.exit_code == 3

    @pytest.mark.parametrize("bad", ["text", None, {"number": "1"}, {"number": True}, {}])
    def test_rejects_malformed_records(self, bad):
        with pytest.raises(rep.ReportError) as err:
            rep.parse_record(bad)
        assert err.value.exit_code == 3

    def test_ignores_non_dict_labels(self):
        raw = record(1)
        raw["labels"] = ["plain", {"name": "source:human"}]
        assert rep.parse_record(raw).labels == frozenset({"source:human"})


class TestClassifyProvenance:
    @pytest.mark.parametrize(
        ("labels", "bucket"),
        [
            (("source:human",), "human-only"),
            (("source:agent",), "agent-only"),
            (("source:human", "source:agent"), "conflict"),
            ((), "unknown"),
            (("bug",), "unknown"),
        ],
    )
    def test_buckets(self, labels, bucket):
        assert rep.classify_provenance(issue(1, NOW, labels=labels)) == bucket

    def test_author_does_not_change_bucket(self):
        assert rep.classify_provenance(issue(1, NOW, login="rjmurillo")) == "unknown"


class TestIsMachinery:
    @pytest.mark.parametrize(
        "title",
        [
            "Ratchet drifts",
            "LEFTHOOK config",
            "fix hooks",
            "pre_pr gate",
            "ADR review",
            "pr-autofix",
        ],
    )
    def test_matches_terms_case_insensitively(self, title):
        assert rep.is_machinery(issue(1, NOW, title=title))

    @pytest.mark.parametrize(
        "title", ["ADR-042 supersede", "hook-based check", "memory-search fails", "fix ADR."]
    )
    def test_hyphen_and_punctuation_neighbours_match(self, title):
        assert rep.is_machinery(issue(1, NOW, title=title))

    @pytest.mark.parametrize("title", ["Address feedback", "Add dark mode", "gateway timeout", ""])
    def test_whole_word_only(self, title):
        assert not rep.is_machinery(issue(1, NOW, title=title))

    def test_area_validation_label(self):
        assert rep.is_machinery(issue(1, NOW, title="Add dark mode", labels=("area-validation",)))


class TestFindBursts:
    def test_three_within_ten_minutes_is_a_burst(self):
        items = [issue(n, NOW + timedelta(minutes=n * 4)) for n in (1, 2, 3)]
        assert rep.find_bursts(items) == [[1, 2, 3]]

    def test_two_issues_are_not_a_burst(self):
        items = [issue(n, NOW + timedelta(minutes=n)) for n in (1, 2)]
        assert rep.find_bursts(items) == []

    def test_exactly_ten_minutes_from_first_is_inside(self):
        items = [
            issue(1, NOW),
            issue(2, NOW + timedelta(minutes=5)),
            issue(3, NOW + timedelta(minutes=10)),
        ]
        assert rep.find_bursts(items) == [[1, 2, 3]]

    def test_one_second_past_ten_minutes_is_outside(self):
        items = [
            issue(1, NOW),
            issue(2, NOW + timedelta(minutes=5)),
            issue(3, NOW + timedelta(minutes=10, seconds=1)),
        ]
        assert rep.find_bursts(items) == []

    def test_different_logins_do_not_combine(self):
        items = [issue(1, NOW, "a"), issue(2, NOW, "b"), issue(3, NOW, "a")]
        assert rep.find_bursts(items) == []

    def test_overlapping_windows_assign_each_issue_once(self):
        # 0,5,10 form one burst; 15 and 20 start a new group of two, not a burst.
        items = [issue(n, NOW + timedelta(minutes=m)) for n, m in enumerate((0, 5, 10, 15, 20), 1)]
        assert rep.find_bursts(items) == [[1, 2, 3]]

    def test_two_bursts_from_one_login(self):
        first = [issue(n, NOW + timedelta(minutes=n)) for n in (1, 2, 3)]
        later = [issue(n, NOW + timedelta(hours=2, minutes=n)) for n in (4, 5, 6)]
        assert rep.find_bursts(first + later) == [[1, 2, 3], [4, 5, 6]]

    def test_empty_input(self):
        assert rep.find_bursts([]) == []


class TestShare:
    def test_ratio(self):
        assert rep.share(1, 3) == 0.3333

    def test_zero_total_is_none_not_zero(self):
        assert rep.share(0, 0) is None


class TestBuildReport:
    def test_mixed_batch_with_burst(self):
        report = make_report(
            [
                record(1, 100, "Add feature", labels=("source:human",)),
                record(2, 50, "Ratchet drift", labels=("source:agent",)),
                record(3, 48, "Validator gap", labels=("source:agent",)),
                record(4, 46, "Hook fails", labels=("source:agent",)),
                record(5, 30, "Both labels", labels=("source:human", "source:agent")),
                record(6, 20, "No label"),
            ]
        )
        assert report["total"] == 6
        counts = {name: report["provenance"][name]["count"] for name in rep.BUCKETS}
        assert counts == {"human-only": 1, "agent-only": 3, "conflict": 1, "unknown": 1}
        assert sum(counts.values()) == report["total"]
        assert report["provenance"]["agent-only"]["issues"] == [2, 3, 4]
        assert report["machinery_heuristic"]["issues"] == [2, 3, 4]
        assert report["bursts"]["groups"] == [[2, 3, 4]]
        assert report["completeness"]["complete"] is True

    def test_empty_window_reports_zero_counts_and_null_shares(self):
        report = make_report([])
        assert report["total"] == 0
        assert all(report["provenance"][name]["count"] == 0 for name in rep.BUCKETS)
        assert all(report["provenance"][name]["share"] is None for name in rep.BUCKETS)
        assert report["machinery_heuristic"]["share"] is None
        assert report["bursts"]["count"] == 0

    def test_json_serializable(self):
        json.dumps(make_report([record(1)]))


class TestRenderMarkdown:
    def test_contains_table_and_completeness(self):
        text = rep.render_markdown(make_report([record(1, labels=("source:agent",))]))
        assert "| agent-only | 1 | 100.0% |" in text
        assert "Read complete: 0 page(s), 0 record(s)" in text
        assert "Limitations:" in text

    def test_empty_prints_na_not_zero_percent(self):
        text = rep.render_markdown(make_report([]))
        assert "| unknown | 0 | N/A |" in text
        assert "Machinery share (heuristic): 0 (N/A)" in text
        assert "0.0%" not in text


class TestOutputEquivalence:
    def test_markdown_table_matches_json_counts(self):
        report = make_report(
            [
                record(1, labels=("source:human",)),
                record(2, labels=("source:agent",)),
                record(3, labels=("source:agent",)),
                record(4),
            ]
        )
        text = rep.render_markdown(report)
        for name in rep.BUCKETS:
            entry = report["provenance"][name]
            row = f"| {name} | {entry['count']} | {rep._percent(entry['share'])} |"
            assert row in text
        assert f"New issues in window: {report['total']}" in text
