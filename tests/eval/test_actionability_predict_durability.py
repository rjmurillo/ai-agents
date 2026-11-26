"""Exit codes, resume log, and temperature for predict (group 2a, 2b, 2c).

Shared helpers: _actionability_arms_test_support.py.
"""

from __future__ import annotations

import importlib
import json
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest

from scripts.eval.actionability_io import split_jsonl_lines
from tests.eval._actionability_arms_test_support import (
    GOOD,
    FakeCallApi,
    aa,
    failed_record,
    heldout_rows,
    install_call_api,
    ok_record,
    pm,
    provider_argv,
    read_jsonl_file,
    row_id_of,
    write_corpus_file,
    write_jsonl_file,
)


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("EVAL_PROVIDER", raising=False)


_EVAL_DIR = Path(__file__).resolve().parents[2] / "scripts" / "eval"


def _http_message(status: int) -> str:
    """The real message `_eval_common.safe_http_error_message` builds for a status."""
    eval_dir = str(_EVAL_DIR)
    if eval_dir not in sys.path:
        sys.path.insert(0, eval_dir)
    common = importlib.import_module("_eval_common")
    return str(common.safe_http_error_message("Anthropic API", status, None))


class TestIsAuthFailure:
    @pytest.mark.parametrize("status", [401, 403])
    def test_real_safe_http_message_for_auth_statuses_is_recognized(self, status: int) -> None:
        """Group 2a: conformance with `_eval_common.safe_http_error_message` for 401 and 403."""
        assert pm.is_auth_failure(RuntimeError(_http_message(status))) is True

    @pytest.mark.parametrize("status", [400, 404, 408, 429, 500, 503])
    def test_other_statuses_are_not_auth(self, status: int) -> None:
        """Group 2a: only 401 and 403 are auth failures."""
        assert pm.is_auth_failure(RuntimeError(_http_message(status))) is False

    @pytest.mark.parametrize(
        "message", ["timed out", "network error", "", "HTTP 4010 is not a status line"]
    )
    def test_non_http_errors_are_not_auth(self, message: str) -> None:
        """Group 2a: unrelated errors never trip the auth stop."""
        assert pm.is_auth_failure(RuntimeError(message)) is False


class TestAuthExit:
    @pytest.mark.parametrize("status", [401, 403])
    def test_auth_failure_exits_four_records_it_and_stops_calling(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, status: int
    ) -> None:
        """Group 2a: first 401 or 403 stops the run with exit 4 and an auth_error record."""
        seen: list[str] = []

        def reply(message: str) -> str:
            seen.append(row_id_of(message))
            if len(seen) == 2:
                raise RuntimeError(_http_message(status))
            return GOOD

        fake = install_call_api(monkeypatch, FakeCallApi(reply))
        out = tmp_path / "pred.jsonl"

        code = aa.main(provider_argv(write_corpus_file(tmp_path, heldout_rows(5)), out))

        records = read_jsonl_file(out)
        assert code == 4
        assert len(fake.calls) == 2
        assert [(r["id"], r["status"]) for r in records] == [("H0", "ok"), ("H1", "auth_error")]
        assert records[1]["is_actionable"] is None

    def test_non_auth_http_errors_do_not_stop_the_run(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Group 2a: a 429 is a call_error and the run continues."""
        replies: Iterator[Exception | str] = iter(
            [RuntimeError(_http_message(429)), GOOD, GOOD, GOOD, GOOD, GOOD]
        )

        def reply(_message: str) -> str:
            item = next(replies)
            if isinstance(item, Exception):
                raise item
            return item

        fake = install_call_api(monkeypatch, FakeCallApi(reply))
        out = tmp_path / "pred.jsonl"

        code = aa.main(provider_argv(write_corpus_file(tmp_path, heldout_rows(6)), out))

        assert code == 0
        assert len(fake.calls) == 6
        assert [r["status"] for r in read_jsonl_file(out)][0] == "call_error"

    def test_auth_exit_wins_over_the_zero_ok_exit(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Group 2a: with no ok rows at all, exit 4 still outranks exit 3."""

        def reply(_message: str) -> str:
            raise RuntimeError(_http_message(401))

        install_call_api(monkeypatch, FakeCallApi(reply))
        out = tmp_path / "pred.jsonl"

        assert aa.main(provider_argv(write_corpus_file(tmp_path, heldout_rows(3)), out)) == 4


class TestZeroOkExit:
    @pytest.mark.parametrize("reply", ["not json", "GOOD_RAISES"])
    def test_one_attempt_with_no_ok_exits_three(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, reply: str
    ) -> None:
        """Group 2a: ok == 0 and attempted >= 1 exits 3 even below the 5-call minimum."""

        def run(_message: str) -> str:
            if reply == "GOOD_RAISES":
                raise RuntimeError("down")
            return reply

        install_call_api(monkeypatch, FakeCallApi(run))
        out = tmp_path / "pred.jsonl"

        code = aa.main(provider_argv(write_corpus_file(tmp_path, heldout_rows(1)), out))

        assert code == 3
        assert len(read_jsonl_file(out)) == 1

    def test_one_ok_among_failures_below_the_minimum_still_exits_zero(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Group 2a: the rate rule keeps its 5-call minimum when something succeeded."""
        feed = iter(["bad", "bad", "bad", GOOD])
        install_call_api(monkeypatch, FakeCallApi(lambda _m: next(feed)))
        out = tmp_path / "pred.jsonl"

        assert aa.main(provider_argv(write_corpus_file(tmp_path, heldout_rows(4)), out)) == 0


class TestAppendLog:
    def test_each_record_is_on_disk_before_the_next_call(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Group 2b: records are appended and flushed one by one, not written at the end."""
        out = tmp_path / "pred.jsonl"
        lines_seen: list[int] = []

        def reply(_message: str) -> str:
            lines_seen.append(
                len(split_jsonl_lines(out.read_text(encoding="utf-8"))) if out.exists() else 0
            )
            return GOOD

        install_call_api(monkeypatch, FakeCallApi(reply))

        assert aa.main(provider_argv(write_corpus_file(tmp_path, heldout_rows(4)), out)) == 0

        assert lines_seen == [0, 1, 2, 3]

    def test_a_crash_keeps_finished_records_and_resume_continues(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Group 2b: an interrupted run loses nothing, and a rerun calls only what is left."""

        class _CrashError(Exception):
            pass

        count = {"n": 0}

        def crashing(_message: str) -> str:
            count["n"] += 1
            if count["n"] == 3:
                raise _CrashError
            return GOOD

        install_call_api(monkeypatch, FakeCallApi(crashing))
        corpus = write_corpus_file(tmp_path, heldout_rows(5))
        out = tmp_path / "pred.jsonl"

        with pytest.raises(_CrashError):
            aa.main(provider_argv(corpus, out))
        assert [r["id"] for r in read_jsonl_file(out)] == ["H0", "H1"]

        capsys.readouterr()
        resumed = install_call_api(monkeypatch, FakeCallApi())
        assert aa.main(provider_argv(corpus, out)) == 0

        assert "resuming, 2 done" in capsys.readouterr().out
        assert [row_id_of(c["messages"][0]["content"]) for c in resumed.calls] == [
            "H2",
            "H3",
            "H4",
        ]
        assert [r["id"] for r in read_jsonl_file(out)] == ["H0", "H1", "H2", "H3", "H4"]

    def test_resume_retries_only_rows_that_are_not_ok(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Group 2b: ok rows are skipped, failed rows are retried, and no id is duplicated."""
        corpus = write_corpus_file(tmp_path, heldout_rows(4))
        out = write_jsonl_file(
            tmp_path / "pred.jsonl",
            [
                ok_record("H0", reason="kept"),
                failed_record("H1", "parse_error"),
                failed_record("H2", "call_error"),
            ],
        )
        fake = install_call_api(monkeypatch, FakeCallApi())

        assert aa.main(provider_argv(corpus, out)) == 0

        records = read_jsonl_file(out)
        assert "resuming, 1 done" in capsys.readouterr().out
        assert sorted(row_id_of(c["messages"][0]["content"]) for c in fake.calls) == [
            "H1",
            "H2",
            "H3",
        ]
        assert sorted(r["id"] for r in records) == ["H0", "H1", "H2", "H3"]
        assert {r["status"] for r in records} == {"ok"}
        assert next(r for r in records if r["id"] == "H0")["reason"] == "kept"

    def test_a_stale_auth_error_record_is_retried_too(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Group 2b: auth_error is not ok, so fixing the key and rerunning retries that row."""
        corpus = write_corpus_file(tmp_path, heldout_rows(2))
        out = write_jsonl_file(
            tmp_path / "pred.jsonl", [ok_record("H0"), failed_record("H1", "auth_error")]
        )
        fake = install_call_api(monkeypatch, FakeCallApi())

        assert aa.main(provider_argv(corpus, out)) == 0

        assert len(fake.calls) == 1
        assert {r["status"] for r in read_jsonl_file(out)} == {"ok"}

    def test_a_torn_final_line_is_dropped_and_the_run_resumes(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Group 2b: a kill mid-write leaves a partial last line, which is not an error."""
        corpus = write_corpus_file(tmp_path, heldout_rows(2))
        out = tmp_path / "pred.jsonl"
        out.write_text(json.dumps(ok_record("H0")) + '\n{"id": "H1", "stat', encoding="utf-8")
        fake = install_call_api(monkeypatch, FakeCallApi())

        assert aa.main(provider_argv(corpus, out)) == 0

        assert len(fake.calls) == 1
        assert [r["id"] for r in read_jsonl_file(out)] == ["H0", "H1"]

    def test_a_corrupt_line_in_the_middle_exits_two_and_leaves_the_file(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Group 2b: damage that is not a torn tail is a config error, not silently dropped."""
        corpus = write_corpus_file(tmp_path, heldout_rows(3))
        out = tmp_path / "pred.jsonl"
        text = json.dumps(ok_record("H0")) + "\nnot json\n" + json.dumps(ok_record("H1")) + "\n"
        out.write_text(text, encoding="utf-8")
        fake = install_call_api(monkeypatch, FakeCallApi())

        code = aa.main(provider_argv(corpus, out))

        assert code == 2
        assert fake.calls == []
        assert out.read_text(encoding="utf-8") == text

    @pytest.mark.parametrize("field", ["model", "provider", "prompt_sha256"])
    def test_resume_refuses_ok_records_from_a_different_run_setup(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, field: str
    ) -> None:
        """Group 2b: mixing models, providers, or prompts in one log would poison the score."""
        corpus = write_corpus_file(tmp_path, heldout_rows(2))
        out = write_jsonl_file(tmp_path / "pred.jsonl", [ok_record("H0", **{field: "other"})])
        before = out.read_text(encoding="utf-8")
        fake = install_call_api(monkeypatch, FakeCallApi())

        code = aa.main(provider_argv(corpus, out))

        assert code == 2
        assert fake.calls == []
        assert out.read_text(encoding="utf-8") == before

    def test_a_fresh_run_does_not_print_resuming(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Group 2b: no output file, no resume line."""
        install_call_api(monkeypatch, FakeCallApi())
        out = tmp_path / "pred.jsonl"

        assert aa.main(provider_argv(write_corpus_file(tmp_path, heldout_rows(1)), out)) == 0

        assert "resuming" not in capsys.readouterr().out

    def test_everything_already_ok_makes_no_calls_and_exits_zero(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Group 2b: a finished log reruns as a no-op."""
        corpus = write_corpus_file(tmp_path, heldout_rows(3))
        out = write_jsonl_file(tmp_path / "pred.jsonl", [ok_record(f"H{i}") for i in range(3)])
        fake = install_call_api(monkeypatch, FakeCallApi())

        assert aa.main(provider_argv(corpus, out)) == 0

        assert fake.calls == []
        assert "resuming, 3 done" in capsys.readouterr().out
        assert len(read_jsonl_file(out)) == 3

    def test_exit_code_counts_carried_ok_rows(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Group 2a and 2b: one new failure among four carried ok rows is 1 of 5, not 1 of 1."""
        corpus = write_corpus_file(tmp_path, heldout_rows(5))
        out = write_jsonl_file(tmp_path / "pred.jsonl", [ok_record(f"H{i}") for i in range(4)])
        install_call_api(monkeypatch, FakeCallApi("not json"))

        assert aa.main(provider_argv(corpus, out)) == 0

    def test_auth_stop_keeps_carried_records(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Group 2a and 2b: exit 4 on resume leaves the carried ok rows and the auth record."""
        corpus = write_corpus_file(tmp_path, heldout_rows(3))
        out = write_jsonl_file(tmp_path / "pred.jsonl", [ok_record("H0")])

        def reply(_message: str) -> str:
            raise RuntimeError(_http_message(403))

        install_call_api(monkeypatch, FakeCallApi(reply))

        assert aa.main(provider_argv(corpus, out)) == 4
        assert [(r["id"], r["status"]) for r in read_jsonl_file(out)] == [
            ("H0", "ok"),
            ("H1", "auth_error"),
        ]


class TestTemperature:
    def test_temperature_is_none_so_call_api_does_not_retry_without_it(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Group 2c: send no temperature; a rejected one makes call_api retry, doubling calls."""
        fake = install_call_api(monkeypatch, FakeCallApi())

        code = aa.main(
            provider_argv(write_corpus_file(tmp_path, heldout_rows(1)), tmp_path / "pred.jsonl")
        )

        assert code == 0
        assert fake.calls[0]["temperature"] is None
