#!/usr/bin/env python3
"""Tests for defect_lineage_report (issue #5638)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

TESTS_METRICS_DIR = str(Path(__file__).resolve().parent)
SKILL_METRICS_DIR = str(Path(__file__).resolve().parents[3] / ".claude" / "skills" / "metrics")
for _entry in (TESTS_METRICS_DIR, SKILL_METRICS_DIR):
    if _entry not in sys.path:
        sys.path.insert(0, _entry)

import defect_lineage_record as rec
import defect_lineage_report as rep
from lineage_test_helpers import SHA_B, fixed_chain, observation_chain


def live_chain():
    record = fixed_chain()
    record["status"] = "CURRENT"
    record["status_history"][-1]["status"] = "CURRENT"
    return record


def unverified_chain():
    record = fixed_chain()
    record["status"] = "UNVERIFIED"
    record["status_history"][-1]["status"] = "UNVERIFIED"
    return record


class TestBuckets:
    @pytest.mark.parametrize(
        ("status", "bucket"),
        [
            ("CURRENT", "live"),
            ("REVERTED", "live"),
            ("UNVERIFIED", "unverified"),
            ("FIXED", "historical"),
            ("SUPERSEDED", "historical"),
        ],
    )
    def test_defect_status_maps_to_bucket(self, status, bucket):
        record = fixed_chain()
        record["status"] = status
        assert rep.bucket_of(record) == bucket

    @pytest.mark.parametrize("status", ["CURRENT", "REVERTED", "UNVERIFIED", "SUPERSEDED"])
    def test_observation_is_never_a_defect_bucket(self, status):
        record = observation_chain()
        record["status"] = status
        assert rep.bucket_of(record) == "observation"

    def test_fixed_finding_is_not_in_the_live_bucket(self):
        summary = rep.build_summary([fixed_chain(), live_chain() | {"id": "other"}])
        assert [e["id"] for e in summary["buckets"]["historical"]] == ["pr-5623-chain"]
        assert [e["id"] for e in summary["buckets"]["live"]] == ["other"]
        assert summary["counts"] == {"live": 1, "unverified": 0, "historical": 1, "observation": 0}


class TestDelay:
    def test_after_merge_is_seconds_level(self):
        assert rep.describe_delay(5) == "5 s after merge"

    def test_before_merge(self):
        assert rep.describe_delay(-30) == "30 s before merge"

    def test_same_second_is_not_provable(self):
        assert "not provable" in rep.describe_delay(0)


class TestSummary:
    def test_entry_carries_latest_live_sha_and_history_length(self):
        entry = rep.build_summary([fixed_chain()])["buckets"]["historical"][0]
        assert entry["live_sha"] == SHA_B
        assert entry["history_length"] == 2
        assert entry["detection_delay_seconds"] == 5
        assert entry["repair_delay_seconds"] == 15164
        assert entry["status"] == "FIXED"

    def test_invalid_record_raises(self):
        with pytest.raises(rec.LineageError):
            rep.build_summary([{"id": "x"}])

    def test_does_not_mutate_inputs(self):
        record = fixed_chain()
        before = json.dumps(record, sort_keys=True)
        rep.build_summary([record])
        assert json.dumps(record, sort_keys=True) == before


class TestMarkdown:
    def render(self, *records):
        return rep.render_markdown(rep.build_summary(list(records)))

    def test_every_bucket_heading_prints_even_when_empty(self):
        text = self.render()
        for title in (
            "Live findings at the recorded SHA",
            "Unverified at the recorded SHA",
            "Historical mechanism evidence (not live)",
            "Observations (no defect claimed)",
        ):
            assert f"## {title}" in text
        assert text.count("None.") == 4

    def test_fixed_finding_is_listed_under_historical_only(self):
        text = self.render(fixed_chain())
        live, rest = text.split("## Unverified at the recorded SHA")
        assert "pr-5623-chain" not in live.split("## Live findings at the recorded SHA")[1]
        assert "### pr-5623-chain" in rest
        assert "Status: FIXED at " + SHA_B in text

    def test_shows_seconds_level_latency_and_limitations(self):
        text = self.render(fixed_chain())
        assert "(5 s after merge)" in text
        assert "15164 s after detection" in text
        assert "Proves the line is gone" in text
        assert "Evidence supports: defect, review_race" in text

    def test_live_unverified_and_observation_sections(self):
        text = self.render(live_chain(), unverified_chain() | {"id": "u"}, observation_chain())
        assert "| Live findings at the recorded SHA | 1 |" in text
        assert "| Unverified at the recorded SHA | 1 |" in text
        assert "| Observations (no defect claimed) | 1 |" in text
        assert "| Historical mechanism evidence (not live) | 0 |" in text

    def test_follow_up_none_and_unmerged_lines(self):
        none_text = self.render(live_chain() | {"follow_up": None})
        assert "- Follow-up: none recorded" in none_text
        record = live_chain()
        record["follow_up"]["merged_at"] = None
        assert "PR #5630 (defect_repair), merged not merged" in self.render(record)

    def test_output_has_no_dashes_that_ci_bans(self):
        text = self.render(fixed_chain(), observation_chain())
        assert chr(0x2014) not in text and chr(0x2013) not in text


class TestJson:
    def test_round_trips(self):
        summary = rep.build_summary([fixed_chain()])
        assert json.loads(rep.render_json(summary)) == summary
