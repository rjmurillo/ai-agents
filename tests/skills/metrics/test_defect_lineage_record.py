#!/usr/bin/env python3
"""Tests for defect_lineage_record, the pure schema and recheck logic (issue #5638)."""

from __future__ import annotations

import copy
import sys
from pathlib import Path

import pytest

TESTS_METRICS_DIR = str(Path(__file__).resolve().parent)
SKILL_METRICS_DIR = str(Path(__file__).resolve().parents[3] / ".claude" / "skills" / "metrics")
for _entry in (TESTS_METRICS_DIR, SKILL_METRICS_DIR):
    if _entry not in sys.path:
        sys.path.insert(0, _entry)

import defect_lineage_record as rec
from lineage_test_helpers import SHA_A, SHA_B, fixed_chain, observation_chain


def problems_of(record):
    return rec.validate_record(record)


def has(problems, fragment):
    return any(fragment in problem for problem in problems)


def mutate(path, value, base=fixed_chain):
    record = base()
    target = record
    for key in path[:-1]:
        target = target[key]
    if value is _DELETE:
        del target[path[-1]]
    else:
        target[path[-1]] = value
    return record


_DELETE = object()


class TestValidRecords:
    def test_fixed_chain_is_valid(self):
        assert problems_of(fixed_chain()) == []

    def test_observation_chain_is_valid(self):
        assert problems_of(observation_chain()) == []

    def test_unmerged_follow_up_is_valid_while_current(self):
        record = fixed_chain()
        record["follow_up"]["merged_at"] = None
        record["status"] = "CURRENT"
        record["status_history"][-1]["status"] = "CURRENT"
        assert problems_of(record) == []

    def test_null_follow_up_is_valid_while_current(self):
        record = fixed_chain()
        record["follow_up"] = None
        record["status"] = "CURRENT"
        record["status_history"][-1]["status"] = "CURRENT"
        assert problems_of(record) == []

    def test_pre_merge_detection_is_valid_without_review_race(self):
        record = fixed_chain()
        record["supports"] = ["defect"]
        record["detection"]["at"] = "2026-09-06T22:00:00Z"
        record["detection_delay_seconds"] = -1413
        assert problems_of(record) == []

    def test_require_valid_returns_the_record(self):
        record = fixed_chain()
        assert rec.require_valid(record) is record

    def test_require_valid_raises_with_every_problem(self):
        with pytest.raises(rec.LineageError) as err:
            rec.require_valid({"id": 5})
        assert len(err.value.problems) > 3
        assert "missing keys" in str(err.value)


class TestShape:
    def test_non_object_record(self):
        assert problems_of([]) == ["record must be a JSON object"]

    def test_missing_keys_are_named(self):
        record = fixed_chain()
        del record["claim"]
        assert has(problems_of(record), "missing keys: claim")

    @pytest.mark.parametrize("value", [0, 2, "1"])
    def test_schema_version(self, value):
        assert has(problems_of(mutate(["schema_version"], value)), "schema_version must be 1")

    @pytest.mark.parametrize("value", ["", "no-slash", 5, None])
    def test_repository(self, value):
        assert has(problems_of(mutate(["repository"], value)), "repository must look like")

    @pytest.mark.parametrize("key", ["id", "default_branch", "claim"])
    def test_blank_text_fields(self, key):
        assert has(problems_of(mutate([key], "  ")), f"record.{key} must be a non-empty string")


class TestSupports:
    @pytest.mark.parametrize("value", [[], "defect", None])
    def test_must_be_non_empty_list(self, value):
        assert has(problems_of(mutate(["supports"], value)), "supports must be a non-empty list")

    def test_unknown_value(self):
        assert has(problems_of(mutate(["supports"], ["defect", "bogus"])), "unknown values")

    def test_observation_stands_alone(self):
        assert has(problems_of(mutate(["supports"], ["observation", "defect"])), "cannot combine")

    def test_process_gap_alone_is_valid(self):
        assert problems_of(mutate(["supports"], ["process_gap"])) == []


class TestSections:
    @pytest.mark.parametrize("key", ["introduction", "detection", "recheck"])
    def test_section_must_be_object(self, key):
        assert has(problems_of(mutate([key], "x")), f"{key} must be an object")

    @pytest.mark.parametrize(
        "value",
        [
            "2026-09-06T22:23",
            "2026-09-06 22:23:33Z",
            "2026-09-06T22:23:33",
            "2026-13-40T99:99:99Z",
            5,
        ],
    )
    def test_timestamps_need_seconds_and_z(self, value):
        problems = problems_of(mutate(["introduction", "merged_at"], value))
        assert has(problems, "introduction.merged_at must be a UTC timestamp")

    def test_url_must_match_repository(self):
        problems = problems_of(
            mutate(["introduction", "url"], "https://github.com/other/repo/pull/1")
        )
        assert has(problems, "introduction.url must start with")

    @pytest.mark.parametrize("value", [0, -1, True, "5", None])
    def test_pr_must_be_positive_int(self, value):
        assert has(problems_of(mutate(["introduction", "pr"], value)), "introduction.pr must be")

    @pytest.mark.parametrize("value", ["XYZ", "abc", "A" * 40, "a" * 41, 5])
    def test_commit_must_be_hex(self, value):
        assert has(problems_of(mutate(["introduction", "commit"], value)), "introduction.commit")

    def test_follow_up_must_be_null_or_object(self):
        assert has(problems_of(mutate(["follow_up"], "x")), "follow_up must be null or an object")

    def test_follow_up_kind(self):
        assert has(problems_of(mutate(["follow_up", "kind"], "bogus")), "follow_up.kind must be")

    def test_follow_up_requires_merged_at_key(self):
        problems = problems_of(mutate(["follow_up", "merged_at"], _DELETE))
        assert has(problems, "follow_up.merged_at is required")

    def test_merged_follow_up_needs_commit(self):
        problems = problems_of(mutate(["follow_up", "commit"], _DELETE))
        assert has(problems, "follow_up.commit")

    @pytest.mark.parametrize("key", ["reverted_by", "superseded_by"])
    def test_pointers_must_be_null_or_object(self, key):
        record = fixed_chain()
        record[key] = "x"
        assert has(problems_of(record), f"{key} must be null or an object")

    @pytest.mark.parametrize("key", ["reverted_by", "superseded_by"])
    def test_pointers_are_checked(self, key):
        record = fixed_chain()
        record[key] = {"pr": 0, "url": "https://example.com/x"}
        problems = problems_of(record)
        assert has(problems, f"{key}.pr must be") and has(problems, f"{key}.url must start")

    def test_null_pointer_is_fine(self):
        record = fixed_chain()
        record["reverted_by"] = None
        assert problems_of(record) == []


class TestContradictions:
    def test_review_race_needs_detection_after_merge(self):
        record = fixed_chain()
        record["detection"]["at"] = "2026-09-06T22:23:30Z"
        record["detection_delay_seconds"] = -3
        assert has(problems_of(record), "review_race but detection is not after")

    def test_review_race_rejects_same_second(self):
        record = fixed_chain()
        record["detection"]["at"] = record["introduction"]["merged_at"]
        record["detection_delay_seconds"] = 0
        assert has(problems_of(record), "delta 0 s")

    def test_stored_delay_must_match_timestamps(self):
        problems = problems_of(mutate(["detection_delay_seconds"], 300))
        assert has(problems, "detection_delay_seconds is 300 but the timestamps give 5")

    def test_follow_up_cannot_merge_before_introduction(self):
        record = fixed_chain()
        record["follow_up"]["merged_at"] = "2026-09-06T22:00:00Z"
        assert has(problems_of(record), "merged before the introduction merged")

    def test_repair_cannot_precede_detection(self):
        record = fixed_chain()
        record["follow_up"]["merged_at"] = "2026-09-06T22:23:36Z"
        assert has(problems_of(record), "repaired a defect before it was detected")

    def test_planned_work_may_precede_detection(self):
        record = observation_chain()
        record["follow_up"]["merged_at"] = "2026-09-06T22:23:36Z"
        assert problems_of(record) == []

    def test_fixed_needs_merged_defect_repair(self):
        record = fixed_chain()
        record["follow_up"]["merged_at"] = None
        assert has(problems_of(record), "FIXED needs a merged defect_repair")

    def test_fixed_without_follow_up(self):
        assert has(problems_of(mutate(["follow_up"], None)), "FIXED needs a merged defect_repair")

    def test_observation_cannot_be_fixed(self):
        record = observation_chain()
        record["status"] = "FIXED"
        record["status_history"][-1]["status"] = "FIXED"
        assert has(problems_of(record), "cannot be FIXED")

    def test_observation_cannot_have_defect_repair(self):
        record = observation_chain()
        record["follow_up"]["kind"] = "defect_repair"
        assert has(problems_of(record), "cannot have a defect_repair follow_up")

    def test_reverted_needs_pointer(self):
        record = fixed_chain()
        record["status"] = "REVERTED"
        record["status_history"][-1]["status"] = "REVERTED"
        assert has(problems_of(record), "REVERTED needs reverted_by")

    def test_superseded_needs_pointer(self):
        record = fixed_chain()
        record["status"] = "SUPERSEDED"
        record["status_history"][-1]["status"] = "SUPERSEDED"
        assert has(problems_of(record), "SUPERSEDED needs superseded_by")

    def test_superseded_with_pointer_is_valid(self):
        record = fixed_chain()
        record["status"] = "SUPERSEDED"
        record["status_history"][-1]["status"] = "SUPERSEDED"
        record["superseded_by"] = {
            "pr": 6000,
            "url": "https://github.com/rjmurillo/ai-agents/pull/6000",
        }
        assert problems_of(record) == []

    def test_unknown_status(self):
        assert has(problems_of(mutate(["status"], "LIVE")), "status must be one of")


class TestHistory:
    def test_must_be_non_empty_list(self):
        assert has(
            problems_of(mutate(["status_history"], [])), "status_history must be a non-empty"
        )

    def test_entry_must_be_object(self):
        record = fixed_chain()
        record["status_history"].insert(0, "x")
        assert has(problems_of(record), "status_history[0] must be an object")

    def test_entry_fields(self):
        record = fixed_chain()
        record["status_history"][0].update(status="LIVE", live_sha="abc", basis="")
        problems = problems_of(record)
        assert has(problems, "status_history[0].status must be")
        assert has(problems, "status_history[0].live_sha must be")
        assert has(problems, "status_history[0].basis must be")

    def test_checked_at_must_strictly_increase(self):
        record = fixed_chain()
        record["status_history"][1]["checked_at"] = record["status_history"][0]["checked_at"]
        assert has(problems_of(record), "must strictly increase")

    def test_one_second_apart_is_ordered(self):
        record = fixed_chain()
        record["status_history"][0]["checked_at"] = "2026-10-13T11:00:00Z"
        record["status_history"][1]["checked_at"] = "2026-10-13T11:00:01Z"
        assert problems_of(record) == []

    def test_status_matches_last_entry(self):
        record = fixed_chain()
        record["status"] = "CURRENT"
        assert has(problems_of(record), "does not match the last status_history entry")

    def test_fixed_entry_cannot_precede_repair(self):
        record = fixed_chain()
        record["status_history"][1]["checked_at"] = "2026-09-07T01:00:00Z"
        assert has(problems_of(record), "is FIXED before the follow_up merged")

    def test_malformed_entry_does_not_crash_fixed_scan(self):
        record = fixed_chain()
        record["status_history"].insert(0, 5)
        assert has(problems_of(record), "status_history[0] must be an object")


class TestRecheckAndLimitations:
    @pytest.mark.parametrize("path", ["/etc/passwd", "../x", "a/../b"])
    def test_path_must_be_relative(self, path):
        assert has(problems_of(mutate(["recheck", "path"], path)), "repository-relative")

    def test_pattern_must_compile(self):
        assert has(problems_of(mutate(["recheck", "pattern"], "(")), "not a valid regex")

    def test_non_string_pattern_is_one_problem_not_a_crash(self):
        problems = problems_of(mutate(["recheck", "pattern"], 5))
        assert has(problems, "recheck.pattern must be a non-empty string")
        assert not has(problems, "not a valid regex")

    def test_live_when(self):
        assert has(problems_of(mutate(["recheck", "live_when"], "never")), "recheck.live_when")

    def test_recheck_text_fields(self):
        assert has(problems_of(mutate(["recheck", "command"], "")), "recheck.command")

    @pytest.mark.parametrize("value", [[], "x", None])
    def test_limitations_required(self, value):
        assert has(problems_of(mutate(["limitations"], value)), "limitations must be a non-empty")

    def test_limitations_entries(self):
        assert has(problems_of(mutate(["limitations"], ["ok", " "])), "entries must be non-empty")


class TestDerivedDelays:
    def test_five_seconds_after_merge(self):
        assert rec.detection_delay_seconds(fixed_chain()) == 5

    def test_negative_before_merge(self):
        record = fixed_chain()
        record["detection"]["at"] = "2026-09-06T22:00:00Z"
        assert rec.detection_delay_seconds(record) == -1413

    def test_repair_delay(self):
        assert rec.repair_delay_seconds(fixed_chain()) == 15164

    def test_repair_delay_none_without_follow_up(self):
        assert rec.repair_delay_seconds(mutate(["follow_up"], None)) is None

    def test_repair_delay_none_when_unmerged(self):
        assert rec.repair_delay_seconds(mutate(["follow_up", "merged_at"], None)) is None

    def test_unparseable_time_raises(self):
        with pytest.raises(rec.LineageError):
            rec.detection_delay_seconds(mutate(["detection", "at"], "soon"))


def probe(state, at="2026-10-14T00:00:00Z", sha=SHA_B, detail="d"):
    return rec.Probe(state, sha, at, detail)


class TestClassify:
    def test_unavailable_is_unverified(self):
        status, basis = rec.classify_probe(fixed_chain(), probe("unavailable"))
        assert status == "UNVERIFIED" and "unavailable" in basis

    def test_claim_holds_is_current(self):
        assert rec.classify_probe(fixed_chain(), probe("present"))[0] == "CURRENT"

    def test_claim_gone_after_repair_is_fixed(self):
        assert rec.classify_probe(fixed_chain(), probe("absent"))[0] == "FIXED"

    def test_live_when_absent_inverts_the_test(self):
        record = fixed_chain()
        record["recheck"]["live_when"] = "absent"
        assert rec.classify_probe(record, probe("absent"))[0] == "CURRENT"
        assert rec.classify_probe(record, probe("present"))[0] == "FIXED"

    def test_claim_holds_after_revert_is_reverted(self):
        record = fixed_chain()
        record["reverted_by"] = {
            "pr": 7,
            "url": f"https://github.com/{record['repository']}/pull/7",
        }
        assert rec.classify_probe(record, probe("present"))[0] == "REVERTED"

    def test_claim_gone_with_superseder_is_superseded(self):
        record = fixed_chain()
        record["superseded_by"] = {
            "pr": 7,
            "url": f"https://github.com/{record['repository']}/pull/7",
        }
        assert rec.classify_probe(record, probe("absent"))[0] == "SUPERSEDED"

    def test_claim_gone_without_repair_is_unverified_not_fixed(self):
        status, basis = rec.classify_probe(mutate(["follow_up"], None), probe("absent"))
        assert status == "UNVERIFIED" and "no merged repair" in basis

    def test_claim_gone_with_unmerged_repair_is_unverified(self):
        record = mutate(["follow_up", "merged_at"], None)
        assert rec.classify_probe(record, probe("absent"))[0] == "UNVERIFIED"

    def test_observation_is_never_fixed(self):
        assert rec.classify_probe(observation_chain(), probe("absent"))[0] == "UNVERIFIED"


class TestApplyRecheck:
    def test_appends_and_keeps_the_chain(self):
        before = fixed_chain()
        after = rec.apply_recheck(before, probe("present"))
        assert after["status"] == "CURRENT"
        assert len(after["status_history"]) == 3
        assert after["status_history"][:2] == before["status_history"]
        assert after["introduction"] == before["introduction"]
        assert after["detection"] == before["detection"]
        assert after["follow_up"] == before["follow_up"]

    def test_does_not_mutate_the_input(self):
        before = fixed_chain()
        snapshot = copy.deepcopy(before)
        rec.apply_recheck(before, probe("absent"))
        assert before == snapshot

    def test_fixed_recheck_stays_fixed_with_new_entry(self):
        after = rec.apply_recheck(fixed_chain(), probe("absent"))
        assert after["status"] == "FIXED"
        assert after["status_history"][-1]["live_sha"] == SHA_B

    def test_unavailable_never_claims_fixed_or_live(self):
        after = rec.apply_recheck(fixed_chain(), probe("unavailable"))
        assert after["status"] == "UNVERIFIED"
        assert after["status_history"][1]["status"] == "FIXED"

    def test_regression_after_fix_is_recorded_as_current(self):
        fixed = rec.apply_recheck(fixed_chain(), probe("absent"))
        back = rec.apply_recheck(fixed, probe("present", at="2026-10-15T00:00:00Z"))
        assert back["status"] == "CURRENT"
        assert [e["status"] for e in back["status_history"]] == [
            "CURRENT",
            "FIXED",
            "FIXED",
            "CURRENT",
        ]

    @pytest.mark.parametrize(
        ("changes", "fragment"),
        [
            ({"state": "maybe"}, "probe state"),
            ({"live_sha": "abc"}, "probe live_sha"),
            ({"checked_at": "yesterday"}, "probe checked_at must be a UTC"),
        ],
    )
    def test_rejects_bad_probe(self, changes, fragment):
        base = probe("present")
        bad = rec.Probe(**{**base.__dict__, **changes})
        with pytest.raises(rec.LineageError) as err:
            rec.apply_recheck(fixed_chain(), bad)
        assert fragment in str(err.value)

    def test_equal_or_earlier_time_is_rejected(self):
        for at in ("2026-10-13T11:00:00Z", "2026-10-13T10:59:59Z"):
            with pytest.raises(rec.LineageError) as err:
                rec.apply_recheck(fixed_chain(), probe("present", at=at))
            assert "later than the last" in str(err.value)

    def test_one_second_later_is_accepted(self):
        after = rec.apply_recheck(fixed_chain(), probe("present", at="2026-10-13T11:00:01Z"))
        assert after["status_history"][-1]["checked_at"] == "2026-10-13T11:00:01Z"

    def test_invalid_record_is_rejected(self):
        with pytest.raises(rec.LineageError):
            rec.apply_recheck(mutate(["claim"], ""), probe("present"))

    def test_result_that_contradicts_is_rejected(self):
        record = mutate(["follow_up", "merged_at"], "2026-10-20T00:00:00Z")
        record["status"] = "CURRENT"
        record["status_history"] = record["status_history"][:1]
        with pytest.raises(rec.LineageError) as err:
            rec.apply_recheck(record, probe("absent"))
        assert "FIXED" in str(err.value)

    def test_unused_sha_constant_is_a_valid_sha(self):
        assert SHA_A != SHA_B


class TestParseTimestamp:
    def test_valid(self):
        assert rec.parse_timestamp("2026-09-06T22:23:33Z").second == 33

    @pytest.mark.parametrize("value", [None, 5, "", "2026-02-30T00:00:00Z"])
    def test_invalid(self, value):
        assert rec.parse_timestamp(value) is None
