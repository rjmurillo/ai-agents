"""JSONL files must split on newline only (review finding 1).

`write_jsonl` keeps ensure_ascii=False, so U+2028, U+2029, and U+0085 reach the file raw.
`str.splitlines()` treats them as line breaks and cuts a record in half. Every reader
splits on "\\n" alone.
"""

from __future__ import annotations

import importlib
import json
from pathlib import Path
from typing import Any

import pytest

from tests.eval._actionability_arms_test_support import (
    FakeCallApi,
    aa,
    heldout_rows,
    install_call_api,
    ok_record,
    provider_argv,
    write_corpus_file,
)
from tests.eval._actionability_corpus_test_support import cc, corpus_row, write_corpus

io_module = importlib.import_module("scripts.eval.actionability_io")

_LINE_BREAKERS = [" ", " ", "\x85", "\x1c", "\x1d", "\x1e", "\x0b", "\x0c"]


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("EVAL_PROVIDER", raising=False)


def _rows(ch: str) -> list[dict[str, Any]]:
    return [{"id": "A", "body": f"before{ch}after"}, {"id": "B", "body": "plain"}]


class TestWriteThenLoad:
    @pytest.mark.parametrize("ch", _LINE_BREAKERS)
    def test_a_record_holding_a_unicode_line_break_loads_whole(
        self, tmp_path: Path, ch: str
    ) -> None:
        """Plan M1-T7 follow-up: write_jsonl then load_jsonl returns the same rows."""
        path = tmp_path / "rows.jsonl"

        io_module.write_jsonl(path, _rows(ch))

        assert io_module.load_jsonl(path) == _rows(ch)

    def test_the_raw_characters_really_reach_the_file(self, tmp_path: Path) -> None:
        """Premise check: ensure_ascii=False writes U+2028, U+2029, and U+0085 unescaped."""
        path = tmp_path / "rows.jsonl"

        io_module.write_jsonl(path, [{"body": "a b c\x85d"}])

        text = path.read_text(encoding="utf-8")
        assert " " in text and " " in text and "\x85" in text
        assert len(text.split("\n")) == 2

    def test_crlf_line_endings_still_load(self, tmp_path: Path) -> None:
        """A file saved with Windows line endings is valid JSONL."""
        path = tmp_path / "rows.jsonl"
        path.write_bytes(b'{"id": "A"}\r\n{"id": "B"}\r\n')

        assert io_module.load_jsonl(path) == [{"id": "A"}, {"id": "B"}]

    def test_blank_and_whitespace_lines_are_skipped(self, tmp_path: Path) -> None:
        """Blank lines carry no record."""
        path = tmp_path / "rows.jsonl"
        path.write_text('{"id": "A"}\n\n   \n{"id": "B"}\n', encoding="utf-8")

        assert [r["id"] for r in io_module.load_jsonl(path) or []] == ["A", "B"]

    def test_a_genuinely_bad_line_is_still_rejected(self, tmp_path: Path) -> None:
        """Splitting on newline only must not hide a corrupt record."""
        path = tmp_path / "rows.jsonl"
        path.write_text('{"id": "A"}\nnot json\n', encoding="utf-8")

        assert io_module.load_jsonl(path) is None


class TestPredictResumeReader:
    @pytest.mark.parametrize("ch", _LINE_BREAKERS)
    def test_resume_reads_a_record_holding_a_unicode_line_break(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
        ch: str,
    ) -> None:
        """Plan M1-T14 follow-up: the resume reader splits on newline only, like load_jsonl."""
        corpus = write_corpus_file(tmp_path, heldout_rows(2))
        out = tmp_path / "pred.jsonl"
        io_module.write_jsonl(out, [ok_record("H0", reason=f"one{ch}two")])
        fake = install_call_api(monkeypatch, FakeCallApi())

        code = aa.main(provider_argv(corpus, out))

        assert code == 0
        assert "resuming, 1 done" in capsys.readouterr().out
        assert len(fake.calls) == 1
        saved = io_module.load_jsonl(out) or []
        assert [r["id"] for r in saved] == ["H0", "H1"]
        assert saved[0]["reason"] == f"one{ch}two"


class TestCliRoundTrip:
    @pytest.mark.parametrize("ch", [" ", " ", "\x85"])
    def test_sheet_then_merge_labels_survive_a_line_break_in_the_body(
        self, tmp_path: Path, ch: str
    ) -> None:
        """Plan M1-T10 follow-up: the labeling round trip works through main(argv)."""
        corpus = write_corpus(tmp_path / "c.jsonl", [corpus_row("A", body=f"x{ch}y")])
        sheet = tmp_path / "sheet.jsonl"
        merged = tmp_path / "merged.jsonl"

        assert cc.main(["sheet", "--corpus", str(corpus), "--output", str(sheet)]) == 0
        filled = [dict(r, label="actionable") for r in io_module.load_jsonl(sheet) or []]
        io_module.write_jsonl(sheet, filled)
        argv = ["merge-labels", "--corpus", str(corpus), "--sheet", str(sheet)]
        code = cc.main([*argv, "--output", str(merged)])

        assert code == 0
        (row,) = io_module.load_jsonl(merged) or []
        assert row["body"] == f"x{ch}y"
        assert row["label"] == "actionable"
        assert json.dumps(row)
