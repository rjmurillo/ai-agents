"""Provenance for the corpus and the score report (group 5).

Rows record the seed and head they were sampled at, the score report records what
it read and when, and the two must agree. Shared helpers:
_actionability_arms_test_support.py and _actionability_corpus_test_support.py.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest

from tests.eval._actionability_arms_test_support import (
    aa,
    make_prediction,
    make_row,
    write_jsonl_file,
)
from tests.eval._actionability_corpus_test_support import cc, corpus_prs, read_rows, write_prs

io_module = __import__("scripts.eval.actionability_io", fromlist=["x"])

pytestmark = pytest.mark.usefixtures("freeze_actionability_clock")

_HEAD = "0123456789abcdef0123456789abcdef01234567"
_NOW = "2026-11-24T12:00:00+00:00"


@pytest.fixture(autouse=True)
def _freeze(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cc, "utc_now_iso", lambda: _NOW)
    monkeypatch.setattr(cc, "head_sha", lambda: _HEAD)
    monkeypatch.setattr(aa, "utc_now_iso", lambda: _NOW)
    monkeypatch.setattr(aa, "head_sha", lambda: "scorehead")


def _sample(tmp_path: Path, *extra: str) -> tuple[int, Path]:
    prs = write_prs(tmp_path / "prs.json", corpus_prs(band=4, outside=2))
    out = tmp_path / "corpus.jsonl"
    argv = ["sample", "--prs", str(prs), "--output", str(out)]
    argv += ["--band-count", "3", "--outside-count", "2", "--dev-count", "1", *extra]
    return cc.main(argv), out


class TestSampleProvenance:
    def test_every_row_records_the_seed_and_head_it_was_sampled_at(self, tmp_path: Path) -> None:
        """Group 5a: corpus_seed and corpus_head_sha on each row."""
        code, out = _sample(tmp_path, "--seed", "77")

        rows = read_rows(out)
        assert code == 0
        assert {r["corpus_seed"] for r in rows} == {77}
        assert {r["corpus_head_sha"] for r in rows} == {_HEAD}

    def test_default_seed_is_recorded_when_none_is_given(self, tmp_path: Path) -> None:
        """Group 5a: the default seed is a value too."""
        code, out = _sample(tmp_path)

        assert code == 0
        assert {r["corpus_seed"] for r in read_rows(out)} == {20261124}

    def test_stdout_prints_the_seed_and_head(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Group 5a: the run states what it used."""
        code, _ = _sample(tmp_path, "--seed", "9")

        out = capsys.readouterr().out
        assert code == 0
        assert "seed 9" in out
        assert f"head {_HEAD}" in out

    def test_unknown_head_is_recorded_as_unknown(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Group 5a: a git failure does not stop sampling, and the row says so."""
        monkeypatch.setattr(cc, "head_sha", lambda: "unknown")

        code, out = _sample(tmp_path)

        assert code == 0
        assert {r["corpus_head_sha"] for r in read_rows(out)} == {"unknown"}

    def test_the_blinded_sheet_never_carries_the_provenance(self, tmp_path: Path) -> None:
        """Group 5a and premortem R3: seed and head are not labeler-visible fields."""
        code, corpus = _sample(tmp_path)
        assert code == 0
        sheet = tmp_path / "sheet.jsonl"

        assert cc.main(["sheet", "--corpus", str(corpus), "--output", str(sheet)]) == 0

        text = sheet.read_text(encoding="utf-8")
        assert _HEAD not in text
        assert "corpus_seed" not in text
        assert "corpus_head_sha" not in text


def _rows(**provenance: Any) -> list[dict[str, Any]]:
    truths = ["actionable"] * 3 + ["not_actionable"] * 3
    rows = [make_row(f"H{i}", label=t, **provenance) for i, t in enumerate(truths)]
    rows.append(
        make_row("O0", split="outside", in_band=False, score=0.9, label="actionable", **provenance)
    )
    return rows


def _score(
    tmp_path: Path, rows: list[dict[str, Any]], preds: list[dict[str, Any]] | None = None
) -> tuple[int, Path, Path, Path]:
    corpus = write_jsonl_file(tmp_path / "c.jsonl", rows)
    predictions = write_jsonl_file(
        tmp_path / "p.jsonl", preds or [make_prediction(f"H{i}") for i in range(6)]
    )
    out = tmp_path / "report.json"
    argv = ["score", "--corpus", str(corpus), "--predictions", str(predictions)]
    code = aa.main([*argv, "--output", str(out), "--bootstrap", "50", "--seed", "3"])
    return code, out, corpus, predictions


class TestScoreProvenance:
    def test_report_records_when_where_and_what_was_read(self, tmp_path: Path) -> None:
        """Group 5b: scored_at, head_sha, and the sha256 of both input files."""
        code, out, corpus, predictions = _score(
            tmp_path, _rows(corpus_seed=5, corpus_head_sha=_HEAD)
        )

        report = json.loads(out.read_text(encoding="utf-8"))
        assert code == 0
        assert report["scored_at"] == _NOW
        assert report["head_sha"] == "scorehead"
        assert report["corpus_sha256"] == hashlib.sha256(corpus.read_bytes()).hexdigest()
        assert report["predictions_sha256"] == hashlib.sha256(predictions.read_bytes()).hexdigest()

    def test_report_copies_the_corpus_seed_and_head_from_the_rows(self, tmp_path: Path) -> None:
        """Group 5b: the sampling provenance travels into the report."""
        code, out, _, _ = _score(tmp_path, _rows(corpus_seed=5, corpus_head_sha=_HEAD))

        report = json.loads(out.read_text(encoding="utf-8"))
        assert code == 0
        assert report["corpus_seed"] == 5
        assert report["corpus_head_sha"] == _HEAD
        assert report["seed"] == 3

    def test_a_corpus_without_provenance_reports_nulls(self, tmp_path: Path) -> None:
        """Group 5b: a corpus sampled before this field existed still scores."""
        code, out, _, _ = _score(tmp_path, _rows())

        report = json.loads(out.read_text(encoding="utf-8"))
        assert code == 0
        assert report["corpus_seed"] is None
        assert report["corpus_head_sha"] is None

    def test_different_input_bytes_give_different_hashes(self, tmp_path: Path) -> None:
        """Group 5b: the hash follows the file, not the parsed content."""
        _, first, _, _ = _score(tmp_path, _rows())
        other = tmp_path / "other"
        other.mkdir()
        altered = [make_prediction(f"H{i}", reason=f"r{i}") for i in range(6)]
        _, second, _, _ = _score(other, _rows(), altered)

        a = json.loads(first.read_text(encoding="utf-8"))
        b = json.loads(second.read_text(encoding="utf-8"))
        assert a["predictions_sha256"] != b["predictions_sha256"]
        assert a["corpus_sha256"] == b["corpus_sha256"]

    @pytest.mark.parametrize("field", ["corpus_seed", "corpus_head_sha"])
    def test_rows_that_disagree_exit_two_naming_the_field(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str], field: str
    ) -> None:
        """Group 5b: one corpus, one seed, one head. A mixed file is two corpora."""
        rows = _rows(corpus_seed=5, corpus_head_sha=_HEAD)
        rows[2][field] = 6 if field == "corpus_seed" else "f" * 40

        code, out, _, _ = _score(tmp_path, rows)

        assert code == 2
        assert not out.exists()
        assert field in capsys.readouterr().err

    def test_a_row_missing_the_provenance_among_rows_that_have_it_exits_two(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Group 5b: a null among values is a disagreement, not a gap to ignore."""
        rows = _rows(corpus_seed=5, corpus_head_sha=_HEAD)
        del rows[0]["corpus_seed"]

        code, _, _, _ = _score(tmp_path, rows)

        assert code == 2
        assert "corpus_seed" in capsys.readouterr().err

    @pytest.mark.parametrize(
        ("field", "value"),
        [("corpus_seed", "5"), ("corpus_seed", True), ("corpus_seed", 1.5), ("corpus_head_sha", 7)],
    )
    def test_wrong_typed_provenance_exits_two(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str], field: str, value: Any
    ) -> None:
        """Group 5b: seed is an int, head is a string."""
        rows = _rows(corpus_seed=5, corpus_head_sha=_HEAD)
        for row in rows:
            row[field] = value

        code, _, _, _ = _score(tmp_path, rows)

        assert code == 2
        assert field in capsys.readouterr().err

    def test_unreadable_inputs_still_exit_two_before_hashing(self, tmp_path: Path) -> None:
        """Group 5b: a missing file is a config error, not a traceback from read_bytes."""
        out = tmp_path / "r.json"
        argv = ["score", "--corpus", str(tmp_path / "no.jsonl")]
        argv += ["--predictions", str(tmp_path / "no2.jsonl"), "--output", str(out)]

        assert aa.main(argv) == 2


class TestClock:
    def test_utc_now_iso_is_a_utc_iso_timestamp_in_seconds(self) -> None:
        """Group 5b: the shared clock returns an aware UTC time with no fraction."""
        stamp = io_module.utc_now_iso()

        parsed = datetime.fromisoformat(stamp)
        assert parsed.utcoffset() is not None
        assert parsed.microsecond == 0
