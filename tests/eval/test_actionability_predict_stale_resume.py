"""Resume reuses a verdict only while the row still sends the same text (review finding 4)."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.eval._actionability_arms_test_support import (
    FakeCallApi,
    aa,
    install_call_api,
    make_row,
    ok_record,
    pm,
    provider_argv,
    read_jsonl_file,
    write_corpus_file,
    write_jsonl_file,
)


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("EVAL_PROVIDER", raising=False)


class TestInputHash:
    def test_the_hash_follows_the_text_the_model_sees(self) -> None:
        """Body, reply, and path all move the hash. The heuristic score does not."""
        base = pm.input_sha256(make_row("A"))

        assert pm.input_sha256(make_row("A", body="changed")) != base
        assert pm.input_sha256(make_row("A", thread_replies=["new reply"])) != base
        assert pm.input_sha256(make_row("A", path="src/b.py")) != base
        assert pm.input_sha256(make_row("A", score=0.9)) == base

    def test_text_past_the_send_limits_does_not_move_the_hash(self) -> None:
        """Edge: a body edit beyond MAX_BODY_CHARS is never sent, so it needs no new call."""
        long_body = "x" * pm.MAX_BODY_CHARS
        base = pm.input_sha256(make_row("A", body=long_body))

        assert pm.input_sha256(make_row("A", body=long_body + "tail")) == base


class TestResumeAfterTheCorpusChanges:
    def test_an_edited_body_is_predicted_again_and_the_old_verdict_is_gone(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """The record for H0 hashes the old body, so H0 is called again; H1 is reused."""
        fake = install_call_api(monkeypatch, FakeCallApi())
        old = ok_record("H0", is_actionable=False)
        old["input_sha256"] = pm.input_sha256(make_row("H0", body="old text"))
        out = write_jsonl_file(tmp_path / "pred.jsonl", [old, ok_record("H1")])
        corpus = write_corpus_file(tmp_path, [make_row("H0"), make_row("H1")])

        code = aa.main(provider_argv(corpus, out))

        records = {r["id"]: r for r in read_jsonl_file(out)}
        assert code == 0
        assert len(fake.calls) == 1
        assert "body of H0" in fake.calls[0]["messages"][0]["content"]
        assert records["H0"]["is_actionable"] is True
        assert records["H0"]["input_sha256"] == pm.input_sha256(make_row("H0"))
        assert len(read_jsonl_file(out)) == 2
        assert "1 carried records no longer match" in capsys.readouterr().out

    def test_a_record_with_no_input_hash_is_predicted_again(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A record written before the hash existed cannot be shown to match."""
        fake = install_call_api(monkeypatch, FakeCallApi())
        legacy = ok_record("H0")
        del legacy["input_sha256"]
        out = write_jsonl_file(tmp_path / "pred.jsonl", [legacy])

        code = aa.main(provider_argv(write_corpus_file(tmp_path, [make_row("H0")]), out))

        assert code == 0
        assert len(fake.calls) == 1

    def test_an_unchanged_row_is_not_called_again(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """No over-fire: a matching hash keeps the carried verdict and makes no call."""
        fake = install_call_api(monkeypatch, FakeCallApi())
        out = write_jsonl_file(tmp_path / "pred.jsonl", [ok_record("H0")])

        code = aa.main(provider_argv(write_corpus_file(tmp_path, [make_row("H0")]), out))

        assert code == 0
        assert fake.calls == []

    def test_a_record_of_another_split_survives_untouched(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Only rows of the selected split are judged for staleness."""
        install_call_api(monkeypatch, FakeCallApi())
        other = ok_record("D0")
        out = write_jsonl_file(tmp_path / "pred.jsonl", [other])
        rows = [make_row("H0"), make_row("D0", split="dev", body="edited since")]

        code = aa.main(provider_argv(write_corpus_file(tmp_path, rows), out))

        assert code == 0
        assert "D0" in {r["id"] for r in read_jsonl_file(out)}
