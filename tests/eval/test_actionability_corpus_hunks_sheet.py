"""Tests for fetch-hunks and sheet in scripts/eval/actionability_corpus.py.

Plan M1-T8 and M1-T10. Shared helpers: _actionability_corpus_test_support.py.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.eval._actionability_corpus_test_support import (
    FROZEN_NOW,
    FakeGraphql,
    cc,
    corpus_row,
    read_rows,
    write_corpus,
)


@pytest.fixture(autouse=True)
def _frozen_clock(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cc, "utc_now_iso", lambda: FROZEN_NOW)


class TestFetchHunks:
    def test_fills_hunks_prints_counts_and_returns_zero(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Plan M1-T8: each row gets its hunk and the run prints fetched, no_hunk, total."""
        fake = FakeGraphql({"A": "@@ -1 +1 @@\n-a\n+b", "B": "@@ -2 +2 @@\n-c\n+d"})
        monkeypatch.setattr(cc, "gh_graphql", fake)
        corpus = write_corpus(tmp_path / "c.jsonl", [corpus_row("A"), corpus_row("B")])
        out = tmp_path / "with-hunks.jsonl"

        code = cc.main(["fetch-hunks", "--corpus", str(corpus), "--output", str(out)])

        assert code == 0
        rows = read_rows(out)
        assert [r["diff_hunk"] for r in rows] == ["@@ -1 +1 @@\n-a\n+b", "@@ -2 +2 @@\n-c\n+d"]
        assert "fetched 2, no_hunk 0, of 2 rows" in capsys.readouterr().out

    def test_row_with_no_hunk_is_flagged_and_kept(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Plan M1-T8: a null node or empty hunk keeps diff_hunk null and counts as no_hunk."""
        monkeypatch.setattr(cc, "gh_graphql", FakeGraphql({"A": "@@ hunk", "B": None, "C": ""}))
        rows_in = [corpus_row("A"), corpus_row("B"), corpus_row("C")]
        corpus = write_corpus(tmp_path / "c.jsonl", rows_in)
        out = tmp_path / "o.jsonl"

        code = cc.main(["fetch-hunks", "--corpus", str(corpus), "--output", str(out)])

        assert code == 0
        rows = read_rows(out)
        assert [r["id"] for r in rows] == ["A", "B", "C"]
        assert [r["diff_hunk"] for r in rows] == ["@@ hunk", None, None]
        assert "fetched 1, no_hunk 2, of 3 rows" in capsys.readouterr().out

    def test_graphql_error_writes_nothing_names_the_row_and_returns_three(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Plan M1-T8: a RuntimeError on any row aborts the run with exit 3."""
        monkeypatch.setattr(cc, "gh_graphql", FakeGraphql({"A": "@@ a"}, fail_on="B"))
        corpus = write_corpus(tmp_path / "c.jsonl", [corpus_row("A"), corpus_row("B")])
        out = tmp_path / "o.jsonl"

        code = cc.main(["fetch-hunks", "--corpus", str(corpus), "--output", str(out)])

        assert code == 3
        assert not out.exists()
        assert "B" in capsys.readouterr().err

    def test_query_is_parameterized_and_never_interpolates_the_id(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Plan M1-T8: the id travels as a GraphQL variable, never in the query text."""
        fake = FakeGraphql({"PRRC_unique_id": "@@ h"})
        monkeypatch.setattr(cc, "gh_graphql", fake)
        corpus = write_corpus(tmp_path / "c.jsonl", [corpus_row("PRRC_unique_id")])

        code = cc.main(
            ["fetch-hunks", "--corpus", str(corpus), "--output", str(tmp_path / "o.jsonl")]
        )

        assert code == 0
        ((query, variables),) = fake.calls
        assert variables == {"id": "PRRC_unique_id"}
        assert "PRRC_unique_id" not in query
        assert "$id: ID!" in query
        assert "diffHunk" in query

    def test_rows_that_already_hold_a_hunk_are_not_refetched(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Plan M1-T8: only rows with a null hunk cost a call."""
        fake = FakeGraphql({"B": "@@ new"})
        monkeypatch.setattr(cc, "gh_graphql", fake)
        rows_in = [corpus_row("A", diff_hunk="@@ old"), corpus_row("B")]
        corpus = write_corpus(tmp_path / "c.jsonl", rows_in)
        out = tmp_path / "o.jsonl"

        assert cc.main(["fetch-hunks", "--corpus", str(corpus), "--output", str(out)]) == 0

        assert [v["id"] for _, v in fake.calls] == ["B"]
        assert [r["diff_hunk"] for r in read_rows(out)] == ["@@ old", "@@ new"]

    def test_returns_two_on_unreadable_corpus(self, tmp_path: Path) -> None:
        """Plan M1-T8: an unreadable corpus is a config error."""
        out = tmp_path / "o.jsonl"

        code = cc.main(
            ["fetch-hunks", "--corpus", str(tmp_path / "none.jsonl"), "--output", str(out)]
        )

        assert code == 2
        assert not out.exists()

    def test_returns_two_on_malformed_corpus_line(self, tmp_path: Path) -> None:
        """Plan M1-T8: a line that is not a JSON object is a config error."""
        corpus = tmp_path / "c.jsonl"
        corpus.write_text('{"id": "A"}\nnot json\n', encoding="utf-8")

        code = cc.main(
            ["fetch-hunks", "--corpus", str(corpus), "--output", str(tmp_path / "o.jsonl")]
        )

        assert code == 2


_SHEET_ALLOWLIST = {"id", "path", "diff_hunk", "body", "label"}
_LEAK_MARKERS = ("leaky-reviewer", "REPLY_MARKER", "heuristic", "in_band", "heldout", "thread_")


def _sheet_fixture(tmp_path: Path, count: int = 20) -> Path:
    rows = [
        corpus_row(
            f"ROW{i:02d}",
            reviewer="leaky-reviewer",
            thread_replies=["REPLY_MARKER reply"],
            heuristic_score=0.5 if i % 2 else 0.9,
            heuristic_reasons=["matched"],
            in_band=bool(i % 2),
            split=("dev", "heldout", "outside")[i % 3],
            diff_hunk=f"@@ hunk {i}",
            label="actionable",
        )
        for i in range(count)
    ]
    return write_corpus(tmp_path / "corpus.jsonl", rows)


def _make_sheet(tmp_path: Path, corpus: Path, seed: int = 11, name: str = "sheet.jsonl") -> Path:
    out = tmp_path / name
    argv = ["sheet", "--corpus", str(corpus), "--output", str(out), "--seed", str(seed)]
    assert cc.main(argv) == 0
    return out


class TestSheet:
    def test_every_row_carries_exactly_the_allowlisted_keys(self, tmp_path: Path) -> None:
        """Plan M1-T10, premortem R3: the sheet key set equals the allowlist for every row."""
        sheet = _make_sheet(tmp_path, _sheet_fixture(tmp_path))

        rows = read_rows(sheet)

        assert len(rows) == 20
        assert all(set(row) == _SHEET_ALLOWLIST for row in rows)

    def test_labels_start_null_even_when_the_corpus_row_is_labeled(self, tmp_path: Path) -> None:
        """Plan M1-T10: the sheet is a blank form, not a copy of prior labels."""
        sheet = _make_sheet(tmp_path, _sheet_fixture(tmp_path))

        assert all(row["label"] is None for row in read_rows(sheet))

    def test_no_reviewer_score_split_reply_or_band_text_reaches_the_sheet(
        self, tmp_path: Path
    ) -> None:
        """Plan M1-T10, premortem R3: nothing outside the allowlist leaks into the file."""
        sheet = _make_sheet(tmp_path, _sheet_fixture(tmp_path))

        text = sheet.read_text(encoding="utf-8")

        for marker in _LEAK_MARKERS:
            assert marker not in text

    def test_dev_rows_are_included(self, tmp_path: Path) -> None:
        """Plan M1-T10: dev rows need labels too, so the sheet holds every corpus row."""
        corpus = _sheet_fixture(tmp_path)
        sheet = _make_sheet(tmp_path, corpus)

        corpus_ids = {r["id"] for r in read_rows(corpus)}

        assert {r["id"] for r in read_rows(sheet)} == corpus_ids

    def test_order_differs_from_corpus_order(self, tmp_path: Path) -> None:
        """Plan M1-T10, premortem R3: a seeded shuffle breaks band-grouped order."""
        corpus = _sheet_fixture(tmp_path)
        sheet = _make_sheet(tmp_path, corpus)

        corpus_order = [r["id"] for r in read_rows(corpus)]
        sheet_order = [r["id"] for r in read_rows(sheet)]

        assert sorted(sheet_order) == sorted(corpus_order)
        assert sheet_order != corpus_order

    def test_same_seed_is_reproducible_and_a_new_seed_reorders(self, tmp_path: Path) -> None:
        """Plan M1-T10: the shuffle is seeded."""
        corpus = _sheet_fixture(tmp_path)
        first = _make_sheet(tmp_path, corpus, seed=3, name="a.jsonl")
        again = _make_sheet(tmp_path, corpus, seed=3, name="b.jsonl")
        other = _make_sheet(tmp_path, corpus, seed=4, name="c.jsonl")

        assert first.read_bytes() == again.read_bytes()
        assert first.read_bytes() != other.read_bytes()

    def test_returns_two_on_unreadable_corpus(self, tmp_path: Path) -> None:
        """Plan M1-T10: an unreadable corpus is a config error and writes nothing."""
        out = tmp_path / "sheet.jsonl"

        code = cc.main(["sheet", "--corpus", str(tmp_path / "none.jsonl"), "--output", str(out)])

        assert code == 2
        assert not out.exists()
