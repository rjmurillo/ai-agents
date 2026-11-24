"""Tests for the merge-labels subcommand of scripts/eval/actionability_corpus.py.

Labels come back from the blinded sheet into the corpus. Shared helpers:
_actionability_corpus_test_support.py.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from tests.eval._actionability_corpus_test_support import (
    FROZEN_NOW,
    cc,
    corpus_row,
    read_rows,
    write_corpus,
)


@pytest.fixture(autouse=True)
def _frozen_clock(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cc, "utc_now_iso", lambda: FROZEN_NOW)


def _sheet_row(row_id: str, label: Any, **extra: Any) -> dict[str, Any]:
    return {"id": row_id, "path": "p", "diff_hunk": None, "body": "b", "label": label, **extra}


def _setup(
    tmp_path: Path, corpus_ids: list[str], sheet: list[dict[str, Any]]
) -> tuple[list[str], Path]:
    corpus = write_corpus(tmp_path / "c.jsonl", [corpus_row(i) for i in corpus_ids])
    sheet_path = write_corpus(tmp_path / "s.jsonl", sheet)
    out = tmp_path / "o.jsonl"
    argv = ["merge-labels", "--corpus", str(corpus), "--sheet", str(sheet_path)]
    return [*argv, "--output", str(out)], out


class TestMergeLabels:
    def test_copies_labels_by_id_and_prints_the_counts(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Labels return to the corpus by id; the summary line counts each kind."""
        sheet = [
            _sheet_row("C", "not_actionable"),
            _sheet_row("A", "actionable"),
            _sheet_row("E", None),
            _sheet_row("B", "actionable"),
            _sheet_row("D", "unsure"),
        ]
        argv, out = _setup(tmp_path, ["A", "B", "C", "D", "E"], sheet)

        code = cc.main(argv)

        assert code == 0
        assert [(r["id"], r["label"]) for r in read_rows(out)] == [
            ("A", "actionable"),
            ("B", "actionable"),
            ("C", "not_actionable"),
            ("D", "unsure"),
            ("E", None),
        ]
        assert "merged 3 labels, unlabeled 1, unsure 1" in capsys.readouterr().out

    def test_corpus_order_and_other_fields_are_preserved(self, tmp_path: Path) -> None:
        """Only label changes; row order and every other field stay as in the corpus."""
        argv, out = _setup(
            tmp_path, ["B", "A"], [_sheet_row("A", "actionable"), _sheet_row("B", "unsure")]
        )

        assert cc.main(argv) == 0

        rows = read_rows(out)
        assert [r["id"] for r in rows] == ["B", "A"]
        for row in rows:
            expected = corpus_row(row["id"])
            expected["label"] = row["label"]
            assert row == expected

    def test_extra_sheet_keys_never_overwrite_corpus_fields(self, tmp_path: Path) -> None:
        """Premortem R3: a sheet carrying heuristic_score or split cannot change the corpus."""
        sheet = [_sheet_row("A", "actionable", heuristic_score=0.99, split="dev", body="forged")]
        argv, out = _setup(tmp_path, ["A"], sheet)

        assert cc.main(argv) == 0

        (row,) = read_rows(out)
        assert row["heuristic_score"] == 0.5
        assert row["split"] == "heldout"
        assert row["body"] == "body A"
        assert row["label"] == "actionable"

    def test_sheet_null_label_replaces_an_existing_corpus_label(self, tmp_path: Path) -> None:
        """The sheet is the source of truth for label, null included."""
        corpus = write_corpus(tmp_path / "c.jsonl", [corpus_row("A", label="actionable")])
        sheet = write_corpus(tmp_path / "s.jsonl", [_sheet_row("A", None)])
        out = tmp_path / "o.jsonl"

        code = cc.main(
            ["merge-labels", "--corpus", str(corpus), "--sheet", str(sheet), "--output", str(out)]
        )

        assert code == 0
        assert read_rows(out)[0]["label"] is None

    def test_sheet_row_without_a_label_key_counts_as_unlabeled(self, tmp_path: Path) -> None:
        """A missing label key is the same as null."""
        argv, out = _setup(tmp_path, ["A"], [{"id": "A", "body": "b"}])

        assert cc.main(argv) == 0
        assert read_rows(out)[0]["label"] is None

    @pytest.mark.parametrize("bad", ["maybe", "ACTIONABLE", "", 1, True, ["actionable"]])
    def test_invalid_label_value_exits_two_and_names_the_row(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
        bad: Any,
    ) -> None:
        """Any value outside the rubric set is a config error naming the row id."""
        argv, out = _setup(
            tmp_path, ["A", "BAD_ROW"], [_sheet_row("A", "actionable"), _sheet_row("BAD_ROW", bad)]
        )

        code = cc.main(argv)

        assert code == 2
        assert not out.exists()
        assert "BAD_ROW" in capsys.readouterr().err

    def test_sheet_id_not_in_corpus_exits_two_with_the_count(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """A sheet from another corpus must not merge."""
        sheet = [_sheet_row("A", "actionable"), _sheet_row("X", None), _sheet_row("Y", None)]
        argv, out = _setup(tmp_path, ["A"], sheet)

        code = cc.main(argv)

        assert code == 2
        assert not out.exists()
        assert "2 sheet ids not in the corpus" in capsys.readouterr().err

    def test_duplicate_sheet_id_exits_two_with_the_count(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Two labels for one row are ambiguous."""
        sheet = [_sheet_row("A", "actionable"), _sheet_row("A", "unsure")]
        argv, out = _setup(tmp_path, ["A"], sheet)

        code = cc.main(argv)

        assert code == 2
        assert not out.exists()
        assert "1 duplicate sheet ids" in capsys.readouterr().err

    def test_corpus_id_missing_from_the_sheet_exits_two_with_the_count(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """A partial sheet would silently leave rows unlabeled."""
        argv, out = _setup(tmp_path, ["A", "B", "C"], [_sheet_row("A", "actionable")])

        code = cc.main(argv)

        assert code == 2
        assert not out.exists()
        assert "2 corpus ids missing from the sheet" in capsys.readouterr().err

    def test_sheet_row_without_an_id_exits_two(self, tmp_path: Path) -> None:
        """A row with no id cannot be joined."""
        argv, out = _setup(tmp_path, ["A"], [_sheet_row("A", None), {"label": "actionable"}])

        assert cc.main(argv) == 2
        assert not out.exists()

    @pytest.mark.parametrize("which", ["corpus", "sheet"])
    def test_unreadable_input_exits_two(self, tmp_path: Path, which: str) -> None:
        """A missing or malformed file is a config error."""
        argv, out = _setup(tmp_path, ["A"], [_sheet_row("A", None)])
        path = Path(argv[argv.index(f"--{which}") + 1])
        path.write_text("not json\n", encoding="utf-8")

        assert cc.main(argv) == 2
        assert not out.exists()

    def test_output_is_valid_jsonl_for_the_score_step(self, tmp_path: Path) -> None:
        """The merged file is one JSON object per line."""
        argv, out = _setup(tmp_path, ["A", "B"], [_sheet_row("A", "unsure"), _sheet_row("B", None)])

        assert cc.main(argv) == 0

        lines = out.read_text(encoding="utf-8").splitlines()
        assert [json.loads(line)["id"] for line in lines] == ["A", "B"]


class TestMergeLabelsCorpusProblems:
    def test_corpus_row_without_an_id_exits_two(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Hygiene 6d: a corpus row with no id cannot be joined."""
        no_id = corpus_row("X")
        del no_id["id"]
        corpus = write_corpus(tmp_path / "c.jsonl", [corpus_row("A"), no_id])
        sheet = write_corpus(tmp_path / "s.jsonl", [_sheet_row("A", None)])
        out = tmp_path / "o.jsonl"

        code = cc.main(
            ["merge-labels", "--corpus", str(corpus), "--sheet", str(sheet), "--output", str(out)]
        )

        assert code == 2
        assert not out.exists()
        assert "corpus rows without an id" in capsys.readouterr().err

    def test_duplicate_corpus_id_exits_two(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Hygiene 6d: two corpus rows with one id make the join ambiguous."""
        corpus = write_corpus(tmp_path / "c.jsonl", [corpus_row("A"), corpus_row("A")])
        sheet = write_corpus(tmp_path / "s.jsonl", [_sheet_row("A", "actionable")])
        out = tmp_path / "o.jsonl"

        code = cc.main(
            ["merge-labels", "--corpus", str(corpus), "--sheet", str(sheet), "--output", str(out)]
        )

        assert code == 2
        assert not out.exists()
        assert "duplicate corpus ids" in capsys.readouterr().err
