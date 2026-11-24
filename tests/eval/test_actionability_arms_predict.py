"""Tests for the predict subcommand of scripts/eval/actionability_arms.py.

Plan M1-T14, premortem R2. Shared helpers: _actionability_arms_test_support.py.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from tests.eval._actionability_arms_test_support import (
    API_KEY,
    GOOD,
    FakeCallApi,
    aa,
    heldout_rows,
    install_call_api,
    make_row,
    pm,
    predict_argv,
    read_jsonl_file,
    write_corpus_file,
)


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("EVAL_PROVIDER", raising=False)


class TestPredictRows:
    def test_ok_record_carries_verdict_latency_and_provenance(self) -> None:
        """Plan M1-T14: each record names status, verdict, latency, provider, model, prompt hash."""
        ticks = iter([10.0, 10.5])

        records = pm.predict_rows(
            [make_row("A")],
            complete=lambda _msg: GOOD,
            provider="fake-provider",
            model="fake-model",
            prompt_sha256="h" * 64,
            clock=lambda: next(ticks),
        )

        assert records == [
            {
                "id": "A",
                "status": "ok",
                "is_actionable": True,
                "confidence": 0.9,
                "reason": "names a change",
                "latency_s": 0.5,
                "provider": "fake-provider",
                "model": "fake-model",
                "prompt_sha256": "h" * 64,
            }
        ]

    def test_unparseable_reply_is_a_parse_error_with_no_verdict(self) -> None:
        """Plan M1-T14: a bad reply is recorded, never turned into a verdict."""
        records = pm.predict_rows(
            [make_row("A")],
            complete=lambda _msg: "I think it is actionable",
            provider="p",
            model="m",
            prompt_sha256="h",
        )

        assert records[0]["status"] == "parse_error"
        assert records[0]["is_actionable"] is None
        assert records[0]["confidence"] is None

    def test_transport_error_is_a_call_error_without_the_message(self) -> None:
        """Plan M1-T14: the exception class is recorded, its text is not."""

        def _fail(_msg: str) -> str:
            raise RuntimeError("secret-bearing provider detail")

        records = pm.predict_rows(
            [make_row("A")], complete=_fail, provider="p", model="m", prompt_sha256="h"
        )

        assert records[0]["status"] == "call_error"
        assert records[0]["error_type"] == "RuntimeError"
        assert "secret-bearing" not in str(records[0])

    def test_one_failed_row_does_not_stop_the_rest(self) -> None:
        """Plan M1-T14: every row gets a record."""
        replies = iter(["garbage", GOOD])

        records = pm.predict_rows(
            [make_row("A"), make_row("B")],
            complete=lambda _msg: next(replies),
            provider="p",
            model="m",
            prompt_sha256="h",
        )

        assert [r["status"] for r in records] == ["parse_error", "ok"]


class TestPredictCli:
    def test_sends_only_in_band_rows_of_the_requested_split(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Plan M1-T14: dev, outside, and out-of-band rows are never sent."""
        monkeypatch.setenv("ANTHROPIC_API_KEY", API_KEY)
        fake = install_call_api(monkeypatch, FakeCallApi())
        rows = [
            make_row("HELD1"),
            make_row("HELD2"),
            make_row("DEV1", split="dev"),
            make_row("OUT1", split="outside", in_band=False),
            make_row("HELD_OUT_OF_BAND", in_band=False),
        ]
        corpus = write_corpus_file(tmp_path, rows)
        out = tmp_path / "pred.jsonl"

        code = aa.main(predict_argv(corpus, out))

        assert code == 0
        assert [r["id"] for r in read_jsonl_file(out)] == ["HELD1", "HELD2"]
        assert len(fake.calls) == 2

    def test_dev_split_is_selectable(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Plan M1-T16: prompt tuning runs on the dev split."""
        monkeypatch.setenv("ANTHROPIC_API_KEY", API_KEY)
        install_call_api(monkeypatch, FakeCallApi())
        corpus = write_corpus_file(tmp_path, [make_row("HELD"), make_row("DEV", split="dev")])
        out = tmp_path / "pred.jsonl"
        argv = predict_argv(corpus, out)
        argv[argv.index("heldout")] = "dev"

        assert aa.main(argv) == 0

        assert [r["id"] for r in read_jsonl_file(out)] == ["DEV"]

    def test_call_uses_the_frozen_prompt_and_spec_budgets(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Plan M1-T14: system prompt from prompt-v1.md, 100 output tokens, temperature 0."""
        monkeypatch.setenv("ANTHROPIC_API_KEY", API_KEY)
        fake = install_call_api(monkeypatch, FakeCallApi())
        corpus = write_corpus_file(tmp_path, [make_row("A", body="Add a null check")])
        out = tmp_path / "pred.jsonl"

        assert aa.main(predict_argv(corpus, out, "--provider", "fake-provider")) == 0

        (call,) = fake.calls
        system, digest = pm.load_prompt()
        assert call["system"] == system
        assert call["model"] == "fake-model"
        assert call["provider"] == "fake-provider"
        assert call["max_tokens"] == 100
        assert call["temperature"] is None
        assert "Add a null check" in call["messages"][0]["content"]
        record = read_jsonl_file(out)[0]
        assert record["prompt_sha256"] == digest
        assert record["prompt_sha256"] == hashlib.sha256(pm.PROMPT_PATH.read_bytes()).hexdigest()
        assert record["provider"] == "fake-provider"
        assert record["model"] == "fake-model"

    def test_api_key_never_reaches_output_or_console(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Plan M1-T14: the key goes to the transport and nowhere else."""
        monkeypatch.setenv("ANTHROPIC_API_KEY", API_KEY)
        fake = install_call_api(monkeypatch, FakeCallApi())
        corpus = write_corpus_file(tmp_path, heldout_rows(2))
        out = tmp_path / "pred.jsonl"

        assert aa.main(predict_argv(corpus, out)) == 0

        seen = capsys.readouterr()
        assert fake.calls[0]["api_key"] == API_KEY
        assert API_KEY not in seen.out + seen.err
        assert API_KEY not in out.read_text(encoding="utf-8")

    def test_default_provider_without_a_key_returns_two_and_writes_nothing(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Plan M1-T14: no key and no provider is a config error naming the variable."""
        fake = install_call_api(monkeypatch, FakeCallApi())
        corpus = write_corpus_file(tmp_path, heldout_rows(2))
        out = tmp_path / "pred.jsonl"

        code = aa.main(predict_argv(corpus, out))

        assert code == 2
        assert not out.exists()
        assert fake.calls == []
        assert "ANTHROPIC_API_KEY" in capsys.readouterr().err

    def test_whitespace_key_counts_as_absent(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Plan M1-T14: an empty or blank key is absent."""
        monkeypatch.setenv("ANTHROPIC_API_KEY", "   ")
        install_call_api(monkeypatch, FakeCallApi())
        out = tmp_path / "pred.jsonl"

        assert aa.main(predict_argv(write_corpus_file(tmp_path, heldout_rows(1)), out)) == 2
        assert not out.exists()

    def test_named_provider_runs_without_an_anthropic_key(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Plan M1-T14: a non-default provider brings its own credential."""
        fake = install_call_api(monkeypatch, FakeCallApi())
        out = tmp_path / "pred.jsonl"

        code = aa.main(
            predict_argv(write_corpus_file(tmp_path, heldout_rows(1)), out, "--provider", "other")
        )

        assert code == 0
        assert fake.calls[0]["api_key"] == ""

    def test_model_is_required_with_no_default(self, tmp_path: Path) -> None:
        """Plan M1-T14: no default model id lives in code."""
        argv = ["predict", "--corpus", str(tmp_path / "c.jsonl"), "--split", "heldout"]

        with pytest.raises(SystemExit) as raised:
            aa.main([*argv, "--output", str(tmp_path / "o.jsonl")])

        assert raised.value.code == 2

    @pytest.mark.parametrize("rate", ["-0.1", "1.5"])
    def test_out_of_range_failure_rate_returns_two(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, rate: str
    ) -> None:
        """Plan M1-T14: --max-failure-rate is a fraction."""
        monkeypatch.setenv("ANTHROPIC_API_KEY", API_KEY)
        install_call_api(monkeypatch, FakeCallApi())
        corpus = write_corpus_file(tmp_path, heldout_rows(1))

        code = aa.main(predict_argv(corpus, tmp_path / "o.jsonl", "--max-failure-rate", rate))

        assert code == 2

    def test_no_selected_rows_returns_two(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Plan M1-T14: zero in-band rows in the split is a wrong-split config error."""
        monkeypatch.setenv("ANTHROPIC_API_KEY", API_KEY)
        install_call_api(monkeypatch, FakeCallApi())
        corpus = write_corpus_file(tmp_path, [make_row("DEV", split="dev")])
        out = tmp_path / "pred.jsonl"

        assert aa.main(predict_argv(corpus, out)) == 2
        assert not out.exists()

    def test_unreadable_corpus_returns_two(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Plan M1-T14: an unreadable corpus is a config error."""
        monkeypatch.setenv("ANTHROPIC_API_KEY", API_KEY)
        install_call_api(monkeypatch, FakeCallApi())

        assert aa.main(predict_argv(tmp_path / "none.jsonl", tmp_path / "o.jsonl")) == 2


class TestFailureRateExit:
    def _run(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        replies: list[str],
        *extra: str,
    ) -> tuple[int, Path]:
        monkeypatch.setenv("ANTHROPIC_API_KEY", API_KEY)
        feed = iter(replies)
        install_call_api(monkeypatch, FakeCallApi(lambda _msg: next(feed)))
        corpus = write_corpus_file(tmp_path, heldout_rows(len(replies)))
        out = tmp_path / "pred.jsonl"
        return aa.main(predict_argv(corpus, out, *extra)), out

    def test_majority_failures_write_the_file_then_exit_three(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Premortem R2: more than half failing at 5+ calls exits 3, file still written."""
        replies = ["bad", "bad", "bad", GOOD, GOOD]

        code, out = self._run(tmp_path, monkeypatch, replies)

        assert code == 3
        statuses = [r["status"] for r in read_jsonl_file(out)]
        assert statuses == ["parse_error", "parse_error", "parse_error", "ok", "ok"]

    def test_exactly_half_failing_is_not_over_the_limit(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Premortem R2: the rule is strictly greater than the rate."""
        replies = ["bad", "bad", "bad", GOOD, GOOD, GOOD, "bad", GOOD]

        code, _ = self._run(tmp_path, monkeypatch, replies)

        assert code == 0

    def test_failures_under_five_attempts_do_not_trip_the_rate_exit(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Premortem R2: four calls is too few to judge a rate when one of them worked."""
        code, out = self._run(tmp_path, monkeypatch, ["bad", "bad", "bad", GOOD])

        assert code == 0
        assert len(read_jsonl_file(out)) == 4

    def test_max_failure_rate_is_configurable(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Premortem R2: --max-failure-rate moves the line."""
        replies = ["bad", GOOD, GOOD, GOOD, GOOD]

        code, _ = self._run(tmp_path, monkeypatch, replies, "--max-failure-rate", "0.1")

        assert code == 3

    def test_transport_errors_count_as_failures(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Premortem R2: call_error rows count toward the failure rate."""
        monkeypatch.setenv("ANTHROPIC_API_KEY", API_KEY)

        def _fail(_msg: str) -> str:
            raise RuntimeError("down")

        install_call_api(monkeypatch, FakeCallApi(_fail))
        out = tmp_path / "pred.jsonl"

        code = aa.main(predict_argv(write_corpus_file(tmp_path, heldout_rows(5)), out))

        assert code == 3
        assert {r["status"] for r in read_jsonl_file(out)} == {"call_error"}


class TestPredictEmptyModel:
    @pytest.mark.parametrize("model", ["", "   "])
    def test_blank_model_returns_two_before_any_call(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, model: str
    ) -> None:
        """Hygiene 6d: a blank --model is a config error, never a call."""
        monkeypatch.setenv("ANTHROPIC_API_KEY", API_KEY)
        fake = install_call_api(monkeypatch, FakeCallApi())
        out = tmp_path / "pred.jsonl"

        code = aa.main(predict_argv(write_corpus_file(tmp_path, heldout_rows(1)), out, model=model))

        assert code == 2
        assert not out.exists()
        assert fake.calls == []
