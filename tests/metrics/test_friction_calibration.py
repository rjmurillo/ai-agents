"""Tests for the REQ-048 TASK-001 calibration script (replay, split, excerpt).

Transcripts are small synthetic fixtures built in code. Planted strings stand
in for private transcript text: the tests assert they never reach
sessions.jsonl, and that planted tokens are redacted in excerpts and samples.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

import pytest

from scripts.metrics import friction_calibration as cal
from scripts.metrics import friction_calibration_scan as scan
from scripts.metrics.friction_calibration_excerpt import excerpt_session

TS = "2026-10-15T12:00:00Z"
SINCE, UNTIL = date(2026, 10, 3), date(2026, 11, 2)
FAKE_TOKEN = "ghp_" + "A1b2C3d4E5" * 3 + "F6g7H8"  # ghp_ plus 36 chars


def human(text: str, ts: str | None = TS) -> dict[str, Any]:
    record: dict[str, Any] = {
        "type": "user",
        "origin": {"kind": "human"},
        "message": {"role": "user", "content": text},
    }
    if ts:
        record["timestamp"] = ts
    return record


def use(use_id: str, name: str, tool_input: object, sidechain: bool = False) -> dict[str, Any]:
    block = {"type": "tool_use", "id": use_id, "name": name, "input": tool_input}
    return {
        "type": "assistant",
        "isSidechain": sidechain,
        "message": {"role": "assistant", "content": [block]},
    }


def result(use_id: str, text: str, error: bool = False, sidechain: bool = False) -> dict[str, Any]:
    block: dict[str, Any] = {"type": "tool_result", "tool_use_id": use_id, "content": text}
    if error:
        block["is_error"] = True
    return {
        "type": "user",
        "isSidechain": sidechain,
        "toolUseResult": {},
        "message": {"role": "user", "content": [block]},
    }


def call(
    n: int, name: str = "Bash", cmd: str = "make build", err: str | None = None
) -> list[dict[str, Any]]:
    """A tool_use/tool_result pair; ``err`` makes the result an error."""
    return [
        use(f"u{n}", name, {"command": cmd}),
        result(f"u{n}", err or "done", error=err is not None),
    ]


def write(path: Path, records: list[Any], raw: list[str] | None = None) -> Path:
    lines = [json.dumps(r) for r in records] + (raw or [])
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


@pytest.fixture
def row(tmp_path: Path):
    def _row(records: list[Any], raw: list[str] | None = None) -> dict[str, Any]:
        path = write(tmp_path / "sess-1.jsonl", records, raw)
        outcome = scan.scan_session(path, seed=1)
        assert outcome.row is not None
        return outcome.row

    return _row


def three_turn_session() -> list[dict[str, Any]]:
    return [
        human("first prompt"),
        *call(1, err="boom one"),
        human("second"),
        *call(2, err="boom two"),
        human("third"),
        *call(3, err="boom three"),
    ]


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


def make_corpus(root: Path, count: int = 3) -> str:
    project = root / "proj-a"
    project.mkdir(parents=True)
    for i in range(count):
        records = [
            human("PLANTED-PROMPT-TEXT", f"2026-10-1{i}T10:00:00Z"),
            use("u1", "Bash", {"command": "echo PLANTED-COMMAND-TEXT"}),
            result("u1", "PLANTED-ERROR-TEXT denied", error=True),
            human("second PLANTED-PROMPT-TEXT"),
        ]
        write(project / f"sess-{i}.jsonl", records)
    write(project / "old.jsonl", [human("x", "2026-01-01T00:00:00Z")])
    return str(project / "*.jsonl")


class TestCli:
    def test_replay_writes_rows_with_no_transcript_text(self, tmp_path: Path, capsys) -> None:
        pattern = make_corpus(tmp_path / "corpus")
        out = tmp_path / "out"
        code = cal.main(
            ["replay", "--corpus-glob", pattern, "--since", "2026-10-03", "--until", "2026-11-02",
             "--out", str(out), "--workers", "1"]
        )  # fmt: skip
        assert code == 0
        text = (out / "sessions.jsonl").read_text(encoding="utf-8")
        rows = [json.loads(line) for line in text.splitlines()]
        assert sorted(r["session_id"] for r in rows) == ["sess-0", "sess-1", "sess-2"]
        assert "PLANTED" not in text
        assert rows[0]["project"] == "proj-a"
        summary = capsys.readouterr().out
        assert "sessions in window : 3" in summary and "window=1" in summary

    def test_samples_are_private_and_hold_redacted_text(self, tmp_path: Path) -> None:
        project = tmp_path / "c" / "p"
        project.mkdir(parents=True)
        err = f"request denied token {FAKE_TOKEN}"
        write(
            project / "s.jsonl",
            [human("a"), *call(1, cmd="ls", err=err), *call(2, cmd=f"echo {FAKE_TOKEN}")],
        )
        out = tmp_path / "out"
        cal.main(["replay", "--corpus-glob", str(project / "*.jsonl"), "--since", "2026-10-03",
                  "--until", "2026-11-02", "--out", str(out), "--workers", "1"])  # fmt: skip
        samples = out / "samples"
        assert (samples.stat().st_mode & 0o777) == 0o700
        for name in ("denial_samples.jsonl", "noncheck_shell_samples.jsonl"):
            body = (samples / name).read_text(encoding="utf-8")
            assert body and FAKE_TOKEN not in body
            assert ((samples / name).stat().st_mode & 0o777) == 0o600
        denial = (samples / "denial_samples.jsonl").read_text(encoding="utf-8")
        assert '"unmatched_word"' in denial and "redacted" in denial
        shell_rows = [
            json.loads(x)
            for x in (samples / "noncheck_shell_samples.jsonl")
            .read_text(encoding="utf-8")
            .splitlines()
        ]
        assert shell_rows[0]["kind"] == "head_table" and ["echo", 1] in shell_rows[0]["heads"]

    def test_replay_with_no_matches_exits_2(self, tmp_path: Path, capsys) -> None:
        code = cal.main(["replay", "--corpus-glob", str(tmp_path / "none*.jsonl"), "--since",
                         "2026-10-03", "--until", "2026-11-02", "--out", str(tmp_path / "o")]
        )  # fmt: skip
        assert code == 2 and "no session files" in capsys.readouterr().err

    def test_replay_rejects_inverted_window_and_bad_workers(self, tmp_path: Path) -> None:
        pattern = make_corpus(tmp_path / "corpus")
        base = ["replay", "--corpus-glob", pattern, "--out", str(tmp_path / "o")]
        assert cal.main([*base, "--since", "2026-11-02", "--until", "2026-10-03"]) == 2
        assert (
            cal.main([*base, "--since", "2026-10-03", "--until", "2026-11-02", "--workers", "0"])
            == 2
        )

    def test_bad_date_is_an_argparse_error(self, tmp_path: Path) -> None:
        with pytest.raises(SystemExit) as exc:
            cal.main(["replay", "--corpus-glob", "x", "--since", "10/03", "--until", "2026-11-02",
                      "--out", str(tmp_path)])  # fmt: skip
        assert exc.value.code == 2

    def test_pool_path_matches_inline(self, tmp_path: Path) -> None:
        pattern = make_corpus(tmp_path / "corpus", count=2)
        files, _ = cal.corpus_files(pattern)
        jobs = [(p, SINCE, UNTIL, 1) for p in files]
        inline = [r.status for r in cal.run_scans(jobs, 1)]
        assert inline.count("scanned") == 2 and inline.count("skipped_window") == 1


class TestSplit:
    def sessions(self, tmp_path: Path, n: int = 20) -> Path:
        path = tmp_path / "sessions.jsonl"
        path.write_text(
            "".join(json.dumps({"session_id": f"s{i:02d}"}) + "\n" for i in range(n)),
            encoding="utf-8",
        )
        return path

    def run_split(self, tmp_path: Path, seed: int, name: str) -> dict[str, Any]:
        out = tmp_path / name
        assert (
            cal.main(
                [
                    "split",
                    "--sessions",
                    str(self.sessions(tmp_path)),
                    "--seed",
                    str(seed),
                    "--out",
                    str(out),
                ]
            )
            == 0
        )
        return json.loads(out.read_text(encoding="utf-8"))

    def test_split_is_a_70_30_partition(self, tmp_path: Path) -> None:
        split = self.run_split(tmp_path, 48001, "a.json")
        everyone = [f"s{i:02d}" for i in range(20)]
        assert len(split["tune"]) == 14 and len(split["heldout"]) == 6
        assert set(split["tune"]).isdisjoint(split["heldout"])
        assert sorted(split["tune"] + split["heldout"]) == everyone
        assert split["seed"] == 48001

    def test_split_is_deterministic_and_seed_sensitive(self, tmp_path: Path) -> None:
        a = self.run_split(tmp_path, 1, "a.json")
        assert a == self.run_split(tmp_path, 1, "b.json")
        assert a["tune"] != self.run_split(tmp_path, 2, "c.json")["tune"]

    def test_split_ignores_input_order(self, tmp_path: Path) -> None:
        forward = self.sessions(tmp_path)
        reverse = tmp_path / "rev.jsonl"
        reverse.write_text(
            "".join(reversed(forward.read_text(encoding="utf-8").splitlines(True))),
            encoding="utf-8",
        )
        out_a, out_b = tmp_path / "a.json", tmp_path / "b.json"
        cal.main(["split", "--sessions", str(forward), "--seed", "5", "--out", str(out_a)])
        cal.main(["split", "--sessions", str(reverse), "--seed", "5", "--out", str(out_b)])
        assert out_a.read_text(encoding="utf-8") == out_b.read_text(encoding="utf-8")

    def test_split_missing_input_exits_2(self, tmp_path: Path) -> None:
        assert (
            cal.main(
                [
                    "split",
                    "--sessions",
                    str(tmp_path / "no"),
                    "--seed",
                    "1",
                    "--out",
                    str(tmp_path / "o"),
                ]
            )
            == 2
        )

    def test_split_of_empty_sessions(self, tmp_path: Path) -> None:
        empty = tmp_path / "e.jsonl"
        empty.write_text("", encoding="utf-8")
        out = tmp_path / "o.json"
        assert cal.main(["split", "--sessions", str(empty), "--seed", "1", "--out", str(out)]) == 0
        assert json.loads(out.read_text(encoding="utf-8"))["tune"] == []


class TestExcerpt:
    def session(self, tmp_path: Path) -> Path:
        records = [
            human("first prompt " + FAKE_TOKEN + " " + "p" * 500),
            {
                "type": "assistant",
                "message": {"content": [{"type": "text", "text": "looking " + "t" * 400}]},
            },
            *call(1, cmd=f"echo {FAKE_TOKEN}", err=f"bad {FAKE_TOKEN}\nsecond line"),
            human("later turn"),
            *call(2, cmd="ls"),
            human("after the stop"),
            *call(3, cmd="never shown"),
        ]
        return write(tmp_path / "abc.jsonl", records)

    def test_excerpt_redacts_token_and_truncates_fields(self, tmp_path: Path) -> None:
        text, counts = excerpt_session(self.session(tmp_path), stop=0)
        assert FAKE_TOKEN not in text and "redacted" in text
        assert counts == {
            "tool_error": 1,
            "permission_denial": 0,
            "failed_retry": 0,
            "edit_churn": 0,
        }
        assert "second line" not in text
        assert "never shown" not in text
        first = next(line for line in text.splitlines() if line.startswith("FIRST PROMPT"))
        assert len(first) <= len("FIRST PROMPT: ") + 300
        assert "#1 Bash input=" in text and "-> ERR bad" in text
        assert "ASSISTANT: looking" in text

    def test_excerpt_shows_later_turns_up_to_the_stop_only(self, tmp_path: Path) -> None:
        text, _ = excerpt_session(self.session(tmp_path), stop=1)
        assert "HUMAN: later turn" in text and "#2 Bash" in text and "-> ok" in text
        assert "after the stop" not in text

    def test_excerpt_never_prints_counts_in_the_file(self, tmp_path: Path) -> None:
        text, _ = excerpt_session(self.session(tmp_path), stop=0)
        assert "tool_error" not in text and "failed_retry" not in text

    def test_max_bytes_keeps_head_and_newest_with_marker(self, tmp_path: Path) -> None:
        records: list[Any] = [human("HEAD-PROMPT")]
        for n in range(60):
            records += call(n, cmd=f"cmd-{n:03d}")
        text, _ = excerpt_session(write(tmp_path / "big.jsonl", records), stop=0, max_bytes=600)
        assert len(text.encode("utf-8")) <= 600
        assert text.startswith("FIRST PROMPT: HEAD-PROMPT")
        assert "earlier lines elided" in text and "cmd-059" in text and "cmd-001" not in text

    def test_small_session_is_not_elided(self, tmp_path: Path) -> None:
        text, _ = excerpt_session(write(tmp_path / "s.jsonl", [human("hi"), *call(1)]), stop=0)
        assert "elided" not in text

    def test_stop_out_of_range_exits_2(self, tmp_path: Path, capsys) -> None:
        self.session(tmp_path)
        out = tmp_path / "x.txt"
        code = cal.main(
            [
                "excerpt",
                "--corpus-glob",
                str(tmp_path / "*.jsonl"),
                "--session",
                "abc",
                "--stop",
                "9",
                "--out",
                str(out),
            ]
        )
        assert code == 2 and "not in 0..2" in capsys.readouterr().err
        assert not out.exists()

    def test_unknown_session_exits_2(self, tmp_path: Path) -> None:
        code = cal.main(
            [
                "excerpt",
                "--corpus-glob",
                str(tmp_path / "*.jsonl"),
                "--session",
                "nope",
                "--stop",
                "0",
                "--out",
                str(tmp_path / "o"),
            ]
        )
        assert code == 2

    def test_cli_writes_file_and_prints_four_counts(self, tmp_path: Path, capsys) -> None:
        self.session(tmp_path)
        out = tmp_path / "ex.txt"
        code = cal.main(
            [
                "excerpt",
                "--corpus-glob",
                str(tmp_path / "*.jsonl"),
                "--session",
                "abc",
                "--stop",
                "0",
                "--out",
                str(out),
            ]
        )
        assert code == 0
        assert (
            "tool_error=1 permission_denial=0 failed_retry=0 edit_churn=0"
            in capsys.readouterr().out
        )
        assert FAKE_TOKEN not in out.read_text(encoding="utf-8")

    def test_empty_session_excerpt(self, tmp_path: Path) -> None:
        path = tmp_path / "e.jsonl"
        path.write_text("", encoding="utf-8")
        text, counts = excerpt_session(path, stop=0)
        assert text == "" and sum(counts.values()) == 0


class TestHelpers:
    def test_percentile_nearest_rank(self) -> None:
        values = [1.0, 2.0, 3.0, 4.0]
        assert cal.percentile(values, 50) == 2.0
        assert cal.percentile(values, 99) == 4.0
        assert cal.percentile([], 50) == 0.0

    def test_summarize_reports_budget_share(self) -> None:
        rows: list[dict[str, object]] = [
            {"scan_seconds": 0.1, "bytes": 1048576, "within_budget": True},
            {"scan_seconds": 9.0, "bytes": 1048576, "within_budget": False},
        ]
        text = cal.summarize(rows, __import__("collections").Counter(), 0)
        assert "within budget      : 1/2 (50.0%)" in text and "2.0 MiB" in text

    def test_summarize_empty(self) -> None:
        assert "sessions in window : 0" in cal.summarize([], __import__("collections").Counter(), 0)

    def test_parse_timestamp_variants(self) -> None:
        assert scan.parse_timestamp("2026-10-03T00:00:00Z") is not None
        assert scan.parse_timestamp("2026-10-03T00:00:00") is not None
        assert scan.parse_timestamp(5) is None and scan.parse_timestamp("") is None


class TestExcerptConversationOnly:
    """The excerpt reads what the judge must see once, and only real prose."""

    def test_request_blob_copies_and_repeats_render_once(self) -> None:
        from scripts.metrics.friction_calibration_excerpt import render_lines

        blob = {
            "type": "api-request-blob",
            "message": {"content": use("t1", "Bash", {"command": "pytest"})["message"]["content"]},
        }
        records = [
            human("fix it"),
            use("t1", "Bash", {"command": "pytest"}),
            result("t1", "boom", error=True),
            blob,
            use("t1", "Bash", {"command": "pytest"}),
            result("t1", "boom", error=True),
        ]
        tool_lines = [line for line in render_lines(records) if line.startswith("#")]
        assert len(tool_lines) == 1
        assert tool_lines[0].endswith("-> ERR boom")

    def test_injected_text_is_not_assistant_prose(self) -> None:
        from scripts.metrics.friction_calibration_excerpt import render_lines

        injected_user = {
            "type": "user",
            "message": {"content": [{"type": "text", "text": "<system-reminder> rules"}]},
        }
        hook_text = {
            "type": "assistant",
            "message": {"content": [{"type": "text", "text": "PreToolUse:Bash hook success: ok"}]},
        }
        prose = {
            "type": "assistant",
            "message": {"content": [{"type": "text", "text": "I will run the tests."}]},
        }
        lines = render_lines([human("go"), injected_user, hook_text, prose])
        assert [line for line in lines if line.startswith("ASSISTANT")] == [
            "ASSISTANT: I will run the tests."
        ]

    def test_headless_task_prompt_is_shown_once(self) -> None:
        from scripts.metrics.friction_calibration_excerpt import render_lines

        def plain(text: str) -> dict[str, Any]:
            return {"type": "user", "message": {"content": [{"type": "text", "text": text}]}}

        lines = render_lines([plain("<system-reminder> x"), plain("Review PR 7"), plain("more")])
        assert lines == ["TASK PROMPT: Review PR 7"]
