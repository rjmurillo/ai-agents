"""Tests for the REQ-048 TASK-001 calibration script (replay, split, excerpt).

Transcripts are small synthetic fixtures built in code. Planted strings stand
in for private transcript text: the tests assert they never reach
sessions.jsonl, and that planted tokens are redacted in excerpts and samples.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from scripts.metrics import friction_calibration as cal
from scripts.metrics import friction_calibration_scan as scan
from tests.metrics.friction_calibration_helpers import (  # noqa: F401
    FAKE_TOKEN,
    SINCE,
    TS,
    UNTIL,
    call,
    human,
    result,
    three_turn_session,
    use,
    write,
)


@pytest.fixture
def row(tmp_path: Path):
    def _row(records: list[Any], raw: list[str] | None = None) -> dict[str, Any]:
        path = write(tmp_path / "sess-1.jsonl", records, raw)
        outcome = scan.scan_session(path, seed=1)
        assert outcome.row is not None
        return outcome.row

    return _row


class TestStops:
    def test_one_stop_per_later_human_turn_plus_eof(self, row) -> None:
        stops = row(three_turn_session())["stops"]
        assert [s["event_count"] for s in stops] == [1, 2, 3]
        assert [s["index"] for s in stops] == [0, 1, 2]

    def test_single_human_turn_has_only_the_eof_stop(self, row) -> None:
        result_row = row([human("only"), *call(1)])
        assert len(result_row["stops"]) == 1
        assert result_row["human_turns"] == 1

    def test_prefix_counts_grow_across_stops(self, row) -> None:
        counts = [s["tool_error"] for s in row(three_turn_session())["stops"]]
        assert counts == [1, 2, 3]

    def test_prefix_counts_are_zero_before_any_failure(self, row) -> None:
        records = [human("a"), *call(1), human("b"), *call(2, err="late failure")]
        assert [s["tool_error"] for s in row(records)["stops"]] == [0, 1]

    def test_empty_file_has_one_empty_stop(self, row) -> None:
        result_row = row([])
        assert result_row["records"] == 0
        assert result_row["stops"] == [
            {"index": 0, "event_count": 0, "tool_error": 0, "permission_denial": 0,
             "failed_retry": 0, "edit_churn": 0}
        ]  # fmt: skip

    def test_malformed_lines_are_skipped_and_counted(self, row) -> None:
        result_row = row([human("a"), *call(1)], raw=["{not json", "[1, 2]", "42"])
        assert result_row["skipped_lines"] == 3
        assert result_row["events"] == 1

    def test_sidechain_records_never_count(self, row) -> None:
        records = [
            human("a"),
            use("s1", "Bash", {"command": "x"}, sidechain=True),
            result("s1", "side failure", error=True, sidechain=True),
            {**human("sidechain human"), "isSidechain": True},
            *call(1),
        ]
        result_row = row(records)
        assert result_row["events"] == 1
        assert result_row["human_turns"] == 1
        assert result_row["stops"][-1]["tool_error"] == 0
        assert result_row["event_count_mismatch"] is False

    def test_tracker_event_count_matches_adapter(self, row) -> None:
        result_row = row(three_turn_session())
        assert result_row["event_count_mismatch"] is False

    def test_unpaired_result_makes_no_event(self, row) -> None:
        result_row = row([human("a"), result("ghost", "x", error=True)])
        assert result_row["events"] == 0

    def test_permission_denial_counts_separately(self, row) -> None:
        records = [human("a"), *call(1, err="Permission denied: /etc/x")]
        final = row(records)["stops"][-1]
        assert (final["tool_error"], final["permission_denial"]) == (0, 1)

    def test_edit_churn_counts_targets_over_whole_scan(self, row) -> None:
        records: list[Any] = [human("a")]
        for n in range(3):
            records += [
                use(f"e{n}", "Edit", {"file_path": "/w/a.py"}),
                result(f"e{n}", "ok"),
                use(f"c{n}", "Bash", {"command": "pytest -q"}),
                result(f"c{n}", "FAILED test_a", error=True),
            ]
        assert row(records)["stops"][-1]["edit_churn"] == 1


class TestFailedRetryDefinitions:
    def test_strict_counts_nonadjacent_repeat_broad_does_not(self, row) -> None:
        records = [
            human("a"),
            *call(1, cmd="a", err="E"),
            *call(2, cmd="b"),
            *call(3, cmd="a", err="E"),
        ]
        result_row = row(records)
        assert result_row["stops"][-1]["failed_retry"] == 1
        assert result_row["failed_retry_broad"] == 0

    def test_broad_counts_adjacent_repeat_after_success_strict_does_not(self, row) -> None:
        records = [human("a"), *call(1, cmd="a"), *call(2, cmd="a", err="E")]
        result_row = row(records)
        assert result_row["stops"][-1]["failed_retry"] == 0
        assert result_row["failed_retry_broad"] == 1


class TestRetrospective:
    def test_skill_form_after_second_turn(self, row) -> None:
        records = [
            human("a"), *call(1), human("b"),
            use("r1", "Skill", {"skill": "project-toolkit:retrospective"}),
            result("r1", "ok"),
        ]  # fmt: skip
        assert row(records)["retro_after_stop"] == 0

    def test_slash_form_is_after_the_stop_before_it(self, row) -> None:
        records = [human("a"), human("b"), human("c"), human("/retrospective now")]
        assert row(records)["retro_after_stop"] == 2

    def test_command_name_wrapper(self, row) -> None:
        wrapped = "<command-message>x</command-message><command-name>/retrospective</command-name>"
        assert row([human("a"), human("b"), human(wrapped)])["retro_after_stop"] == 1

    def test_retro_before_any_stop_is_null(self, row) -> None:
        assert row([human("/retrospective"), *call(1)])["retro_after_stop"] is None

    def test_no_retro_is_null(self, row) -> None:
        assert row(three_turn_session())["retro_after_stop"] is None

    def test_other_skill_and_mention_do_not_count(self, row) -> None:
        records = [
            human("a"), human("about retrospective notes"),
            use("r1", "Skill", {"skill": "reflect"}), result("r1", "ok"),
        ]  # fmt: skip
        assert row(records)["retro_after_stop"] is None

    def test_first_retro_wins(self, row) -> None:
        records = [human("a"), human("/retrospective"), human("c"), human("/retrospective")]
        assert row(records)["retro_after_stop"] == 0

    def test_sidechain_skill_does_not_count(self, row) -> None:
        records = [human("a"), human("b"), use("r1", "Skill", {"skill": "retrospective"}, True)]
        assert row(records)["retro_after_stop"] is None


class TestConsumerA:
    def test_fires_once_at_the_third_identical_failure(self, row) -> None:
        records = [human("a")] + [r for n in range(5) for r in call(n, err="same failure")]
        fires = row(records)["consumer_a"]
        repeats = [f for f in fires if f["signal"] == "failure-repeat"]
        assert [(f["index"], f["count"]) for f in repeats] == [(2, 3)]

    def test_no_fire_below_threshold(self, row) -> None:
        records = [human("a"), *call(1, err="x"), *call(2, err="x")]
        assert row(records)["consumer_a"] == []

    def test_fire_records_omit_fingerprint_text(self, row) -> None:
        records = [human("a")] + [r for n in range(3) for r in call(n, err="UNIQUE-FAILURE-TEXT")]
        fires = row(records)["consumer_a"]
        assert fires and set(fires[0]) == {"index", "signal", "count"}
        assert "UNIQUE-FAILURE-TEXT" not in json.dumps(fires)

    def test_distinct_fingerprints_each_fire(self, row) -> None:
        records = [human("a")]
        n = 0
        for text in ("alpha failure", "beta failure"):
            for _ in range(3):
                records += call(n, cmd=f"run {n}", err=text)
                n += 1
        assert len(row(records)["consumer_a"]) == 2


class TestTallies:
    def test_denial_hits_per_marker(self, row) -> None:
        records = [
            human("a"),
            *call(1, err="Permission denied"),
            *call(2, cmd="p", err="push rejected"),
        ]
        hits = row(records)["denial_hits"]
        assert hits["permission denied"] == 1
        assert hits["rejected"] == 1
        assert hits["was denied"] == 0

    def test_shell_success_split_by_check(self, row) -> None:
        records = [
            human("a"),
            *call(1, cmd="pytest -q"),
            *call(2, cmd="ls -la"),
            *call(3, cmd="ls", err="E"),
        ]
        assert row(records)["shell_success"] == {"check": 1, "not_check": 1}

    def test_candidates_collect_denial_and_unmatched_words(self, tmp_path: Path) -> None:
        records = [
            human("a"),
            *call(1, err="Permission denied here"),
            *call(2, cmd="q", err="request was blocked upstream"),
            *call(3, cmd="ls /tmp"),
        ]
        outcome = scan.scan_session(write(tmp_path / "s.jsonl", records), seed=1)
        assert outcome.cands is not None
        assert [i[1] for _, i in outcome.cands.denial.keyed()] == ["permission denied"]
        assert [i[1] for _, i in outcome.cands.word.keyed()] == ["blocked"]
        assert [i[1] for _, i in outcome.cands.shell.keyed()] == ["ls /tmp"]

    def test_sampling_is_seed_deterministic(self, tmp_path: Path) -> None:
        records = [human("a")] + [r for n in range(40) for r in call(n, cmd=f"ls {n}")]
        path = write(tmp_path / "s.jsonl", records)

        def picked(seed: int) -> list[Any]:
            outcome = scan.scan_session(path, seed=seed)
            assert outcome.cands is not None
            return sorted(i[1] for _, i in outcome.cands.shell.keyed())

        assert picked(7) == picked(7)

    def test_head_word_skips_cd_and_env_prefixes(self) -> None:
        assert scan.head_word("cd /x && FOO=1 Git status") == "git"
        assert scan.head_word("   ") == ""


class TestBudget:
    def test_small_file_is_within_budget(self, row) -> None:
        assert row([human("a"), *call(1)])["within_budget"] is True

    def test_slow_scan_is_out_of_budget(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(scan.hook(), "SCAN_BUDGET_SECONDS", -1.0)
        outcome = scan.scan_session(write(tmp_path / "s.jsonl", [human("a")]), seed=1)
        assert outcome.row is not None and outcome.row["within_budget"] is False

    def test_oversize_file_is_scanned_but_out_of_budget(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(scan.hook(), "MAX_TRANSCRIPT_BYTES", 10)
        outcome = scan.scan_session(write(tmp_path / "s.jsonl", [human("a")]), seed=1)
        assert outcome.row is not None
        assert outcome.row["within_budget"] is False and outcome.row["records"] == 1


class TestWindow:
    def test_bounds_are_inclusive_by_first_timestamp(self, tmp_path: Path) -> None:
        def status(ts: str | None) -> str:
            path = write(tmp_path / "w.jsonl", [human("a", ts)])
            return scan.scan_if_in_window(path, SINCE, UNTIL, 1).status

        assert status("2026-10-03T00:00:00Z") == "scanned"
        assert status("2026-11-02T23:59:59Z") == "scanned"
        assert status("2026-10-02T23:59:59Z") == "skipped_window"
        assert status("2026-11-03T00:00:00Z") == "skipped_window"
        assert status(None) == "skipped_no_timestamp"
        assert status("not a time") == "skipped_no_timestamp"

    def test_first_record_timestamp_decides_not_later_ones(self, tmp_path: Path) -> None:
        records = [human("a", "2026-09-01T00:00:00Z"), human("b", "2026-10-15T00:00:00Z")]
        path = write(tmp_path / "w.jsonl", records)
        assert scan.scan_if_in_window(path, SINCE, UNTIL, 1).status == "skipped_window"

    def test_timestampless_leading_record_is_passed_over(self, tmp_path: Path) -> None:
        path = write(tmp_path / "w.jsonl", [{"type": "snapshot"}, human("a", TS)])
        assert scan.scan_if_in_window(path, SINCE, UNTIL, 1).status == "scanned"

    def test_empty_file_has_no_timestamp(self, tmp_path: Path) -> None:
        path = tmp_path / "e.jsonl"
        path.write_text("", encoding="utf-8")
        assert scan.scan_if_in_window(path, SINCE, UNTIL, 1).status == "skipped_no_timestamp"

    def test_unreadable_file_is_a_counted_error(self, tmp_path: Path) -> None:
        outcome = scan.safe_scan(tmp_path / "missing.jsonl", SINCE, UNTIL, 1)
        assert outcome.status == "error" and outcome.detail == "FileNotFoundError"

    def test_corpus_files_drop_subagent_files(self, tmp_path: Path) -> None:
        for rel in ("p/a.jsonl", "p/agent-9.jsonl", "p/subagents/b.jsonl", "p/note.txt"):
            (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
            (tmp_path / rel).write_text("", encoding="utf-8")
        files, dropped = cal.corpus_files(str(tmp_path / "p" / "*") + "")
        assert [f.name for f in files] == ["a.jsonl"]
        assert dropped == 1
