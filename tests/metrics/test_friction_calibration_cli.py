"""Tests for the calibration CLI, split, and excerpt (REQ-048 TASK-001).

Split from test_friction_calibration.py to stay under the file-size lint.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from scripts.metrics import friction_calibration as cal
from scripts.metrics import friction_calibration_scan as scan
from scripts.metrics.friction_calibration_excerpt import excerpt_session
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
