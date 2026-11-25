"""A torn multibyte character at the output tail does not stop a resume (review finding 9)."""

from __future__ import annotations

import json
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
)

_EURO = "€".encode()  # three bytes: e2 82 ac


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("EVAL_PROVIDER", raising=False)


def _good_line(row_id: str) -> bytes:
    return json.dumps(ok_record(row_id), ensure_ascii=False).encode("utf-8") + b"\n"


def _torn_tail(row_id: str, keep: int) -> bytes:
    """A record line cut inside a multibyte character: ``keep`` of the euro's 3 bytes survive."""
    record = json.dumps(ok_record(row_id, reason="cost €"), ensure_ascii=False)
    head = record.split("€")[0].encode("utf-8")
    return head + _EURO[:keep]


class TestReadPriorRecords:
    @pytest.mark.parametrize("keep", [1, 2])
    def test_a_torn_multibyte_tail_is_dropped(self, tmp_path: Path, keep: int) -> None:
        """Both partial euro prefixes are invalid UTF-8 and used to raise UnicodeDecodeError."""
        path = tmp_path / "pred.jsonl"
        path.write_bytes(_good_line("H0") + _torn_tail("H1", keep))

        records = pm._read_prior_records(path)

        assert [r["id"] for r in records] == ["H0"]

    def test_a_valid_multibyte_record_is_kept(self, tmp_path: Path) -> None:
        """No over-fire: a complete euro sign decodes."""
        path = tmp_path / "pred.jsonl"
        path.write_bytes(
            json.dumps(ok_record("H0", reason="cost €"), ensure_ascii=False).encode() + b"\n"
        )

        (record,) = pm._read_prior_records(path)

        assert record["reason"] == "cost €"

    def test_invalid_utf8_before_the_last_line_is_an_output_error(self, tmp_path: Path) -> None:
        """Damage that is not a torn tail still fails loudly, as a typed error."""
        path = tmp_path / "pred.jsonl"
        path.write_bytes(_torn_tail("H0", 1) + b"\n" + _good_line("H1"))

        with pytest.raises(pm.OutputError, match="line 1"):
            pm._read_prior_records(path)

    def test_invalid_bytes_on_a_lone_line_are_dropped(self, tmp_path: Path) -> None:
        """Edge: a file that is only a torn line holds no records."""
        path = tmp_path / "pred.jsonl"
        path.write_bytes(_torn_tail("H0", 2))

        assert pm._read_prior_records(path) == []

    def test_an_unreadable_file_is_an_output_error(self, tmp_path: Path) -> None:
        with pytest.raises(pm.OutputError, match="cannot read"):
            pm._read_prior_records(tmp_path / "missing.jsonl")


class TestResumeThroughMain:
    def test_resume_survives_a_torn_multibyte_tail(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The CLI keeps the finished row, retries the torn one, and exits 0."""
        fake = install_call_api(monkeypatch, FakeCallApi())
        out = tmp_path / "pred.jsonl"
        out.write_bytes(_good_line("H0") + _torn_tail("H1", 1))
        corpus = write_corpus_file(tmp_path, [make_row("H0"), make_row("H1")])

        code = aa.main(provider_argv(corpus, out))

        assert code == 0
        assert len(fake.calls) == 1
        assert [r["id"] for r in read_jsonl_file(out)] == ["H0", "H1"]
