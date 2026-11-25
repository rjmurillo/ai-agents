"""Consecutive call_error breaker and the selected-row count in the predict summary.

Plan M1-T14, premortem R2, review finding 7. After 5 call_error results in a row the
transport is down. Calling the rest of the corpus only burns time, so predict stops, keeps
what it has, and exits 3.
"""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest

from tests.eval._actionability_arms_test_support import (
    GOOD,
    FakeCallApi,
    aa,
    heldout_rows,
    install_call_api,
    ok_record,
    pm,
    provider_argv,
    read_jsonl_file,
    write_corpus_file,
    write_jsonl_file,
)

_AUTH = "Anthropic API returned HTTP 401: error=auth; provider response redacted"


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("EVAL_PROVIDER", raising=False)


def _script(*steps: str) -> FakeCallApi:
    """A fake transport. "E" raises RuntimeError, "A" raises an auth error, else replies."""
    queue = list(steps)

    def reply(_message: str) -> str:
        step = queue.pop(0)
        if step == "E":
            raise RuntimeError("down")
        if step == "A":
            raise RuntimeError(_AUTH)
        return step

    return FakeCallApi(reply)


def _run(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    steps: list[str],
    rows: int,
    extra: tuple[str, ...] = (),
) -> tuple[int, FakeCallApi, Path]:
    fake = install_call_api(monkeypatch, _script(*steps))
    out = tmp_path / "pred.jsonl"
    corpus = write_corpus_file(tmp_path, heldout_rows(rows))
    return aa.main(provider_argv(corpus, out, *extra)), fake, out


class TestBreaker:
    def test_five_call_errors_in_a_row_stop_the_run_with_exit_three(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """The sixth call is never made, the five records are kept, and the exit is 3."""
        code, fake, out = _run(tmp_path, monkeypatch, ["E"] * 10, rows=10)

        seen = capsys.readouterr()
        assert code == 3
        assert len(fake.calls) == 5
        assert [r["status"] for r in read_jsonl_file(out)] == ["call_error"] * 5
        assert "attempted 5 of 10 selected" in seen.out
        assert "stopped after 5 consecutive call_error" in seen.out

    def test_four_in_a_row_do_not_trip_it(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The threshold is exactly five. The rate rule is switched off to isolate the breaker."""
        steps = ["E", "E", "E", "E", GOOD, GOOD, GOOD]

        code, fake, _ = _run(
            tmp_path, monkeypatch, steps, rows=7, extra=("--max-failure-rate", "1")
        )

        assert code == 0
        assert len(fake.calls) == 7

    def test_a_success_resets_the_streak(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Four errors, an ok, then four more errors is two short streaks, not one long one."""
        steps = ["E"] * 4 + [GOOD] + ["E"] * 4 + [GOOD]

        code, fake, _ = _run(
            tmp_path, monkeypatch, steps, rows=10, extra=("--max-failure-rate", "1")
        )

        assert code == 0
        assert len(fake.calls) == 10

    def test_a_parse_error_also_resets_the_streak(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A bad reply means the transport answered, so the streak counts call_error only."""
        steps = ["E"] * 4 + ["not json"] + ["E"] * 4 + [GOOD]

        code, fake, _ = _run(
            tmp_path, monkeypatch, steps, rows=10, extra=("--max-failure-rate", "1")
        )

        assert code == 0
        assert len(fake.calls) == 10

    def test_an_auth_failure_inside_a_streak_exits_four_not_three(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The credential problem is the more useful news, so exit 4 still wins."""
        code, fake, out = _run(tmp_path, monkeypatch, ["E"] * 4 + ["A", GOOD], rows=6)

        assert code == 4
        assert len(fake.calls) == 5
        assert [r["status"] for r in read_jsonl_file(out)][-1] == "auth_error"

    def test_the_breaker_fires_even_when_the_failure_rate_is_low(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Five ok rows carried over plus five errors is a 50 percent rate, which the rate rule
        allows. The streak is still an outage."""
        corpus = write_corpus_file(tmp_path, heldout_rows(10))
        out = write_jsonl_file(tmp_path / "pred.jsonl", [ok_record(f"H{i}") for i in range(5)])
        fake = install_call_api(monkeypatch, _script(*["E"] * 5))

        code = aa.main(provider_argv(corpus, out))

        assert code == 3
        assert len(fake.calls) == 5

    def test_a_rerun_after_a_trip_retries_the_failed_rows_and_finishes(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The recorded call_error rows are not ok, so the next run picks them up."""
        code, _, out = _run(tmp_path, monkeypatch, ["E"] * 8, rows=8)
        assert code == 3
        corpus = tmp_path / "corpus.jsonl"
        fake = install_call_api(monkeypatch, FakeCallApi())

        assert aa.main(provider_argv(corpus, out)) == 0

        assert len(fake.calls) == 8
        assert {r["status"] for r in read_jsonl_file(out)} == {"ok"}


class TestSelectedCountInSummary:
    def test_a_full_run_reports_n_of_n(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Group 7: every selected row was attempted."""
        code, _, _ = _run(tmp_path, monkeypatch, [GOOD] * 4, rows=4)

        out = capsys.readouterr().out
        assert code == 0
        assert "attempted 4 of 4 selected: ok 4, parse_error 0, call_error 0" in out
        assert "consecutive" not in out

    def test_an_auth_stop_reports_how_far_it_got(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Group 7: the line shows the run ended early."""
        code, _, _ = _run(tmp_path, monkeypatch, [GOOD, "A", GOOD, GOOD], rows=4)

        assert code == 4
        assert "attempted 2 of 4 selected" in capsys.readouterr().out

    def test_carried_ok_rows_count_as_attempted(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Group 7: on a resume the numerator covers the whole selection's records."""
        corpus = write_corpus_file(tmp_path, heldout_rows(3))
        out = write_jsonl_file(tmp_path / "pred.jsonl", [ok_record("H0")])
        install_call_api(monkeypatch, FakeCallApi())

        assert aa.main(provider_argv(corpus, out)) == 0

        assert "attempted 3 of 3 selected" in capsys.readouterr().out


class TestConstants:
    def test_the_threshold_is_a_named_constant_of_five(self) -> None:
        """The brief fixes five. A named constant keeps the number out of the logic."""
        assert pm.MAX_CONSECUTIVE_CALL_ERRORS == 5
        assert importlib.import_module("scripts.eval.actionability_predict") is pm
