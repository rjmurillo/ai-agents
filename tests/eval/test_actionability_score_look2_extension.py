"""Look 2 needs the look-1 report and 100 more heldout band rows (review finding 5)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from tests.eval._actionability_arms_test_support import (
    aa,
    make_prediction,
    make_row,
    sc,
    write_jsonl_file,
)


def _corpus(n: int) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """n heldout band rows, one PR each. Row 0 is labeled not actionable and C flips it."""
    rows = [make_row(f"H{i}", label="actionable") for i in range(n)]
    rows[0]["label"] = "not_actionable"
    preds = [make_prediction("H0", is_actionable=False, confidence=0.9)]
    return rows, preds


def _argv(tmp_path: Path, rows: list, preds: list, *extra: str) -> list[str]:
    corpus = write_jsonl_file(tmp_path / "c.jsonl", rows)
    predictions = write_jsonl_file(tmp_path / "p.jsonl", preds)
    return [
        "score",
        "--corpus",
        str(corpus),
        "--predictions",
        str(predictions),
        "--output",
        str(tmp_path / "out.json"),
        "--bootstrap",
        "300",
        *extra,
    ]


def _look1_report(tmp_path: Path, n: int, verdict: str = "inconclusive") -> Path:
    rows, preds = _corpus(n)
    assert aa.main(_argv(tmp_path, rows, preds)) == 0
    report = json.loads((tmp_path / "out.json").read_text(encoding="utf-8"))
    report["verdict"] = verdict
    path = tmp_path / "look1.json"
    path.write_text(json.dumps(report), encoding="utf-8")
    (tmp_path / "out.json").unlink()
    return path


class TestLookTwoExtension:
    def test_the_look_one_report_records_the_band_row_count(self, tmp_path: Path) -> None:
        """Look 1 stores what look 2 compares against."""
        look1 = _look1_report(tmp_path, 12)

        assert json.loads(look1.read_text(encoding="utf-8"))["heldout_band_rows"] == 12

    def test_an_unchanged_corpus_at_look_two_exits_two_and_writes_nothing(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """The defect: the same corpus used to be scored and marked final."""
        look1 = _look1_report(tmp_path, 12)
        rows, preds = _corpus(12)

        code = aa.main(_argv(tmp_path, rows, preds, "--look", "2", "--look1-report", str(look1)))

        assert code == 2
        assert not (tmp_path / "out.json").exists()
        assert "adds 0" in capsys.readouterr().err

    def test_ninety_nine_added_rows_is_refused_and_one_hundred_is_scored(
        self, tmp_path: Path
    ) -> None:
        """Edge: the bar is 100 added rows."""
        look1 = _look1_report(tmp_path, 12)
        short_rows, preds = _corpus(12 + 99)
        enough_rows, _ = _corpus(12 + 100)
        extra = ("--look", "2", "--look1-report", str(look1))

        assert aa.main(_argv(tmp_path, short_rows, preds, *extra)) == 2
        assert aa.main(_argv(tmp_path, enough_rows, preds, *extra)) == 0

        report = json.loads((tmp_path / "out.json").read_text(encoding="utf-8"))
        assert report["look"] == 2
        assert report["final"] is True

    def test_look_two_without_a_look_one_report_exits_two(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        rows, preds = _corpus(120)

        code = aa.main(_argv(tmp_path, rows, preds, "--look", "2"))

        assert code == 2
        assert "--look1-report" in capsys.readouterr().err

    def test_a_look_one_report_is_refused_at_look_one(self, tmp_path: Path) -> None:
        """No silent ignore of a flag that cannot apply."""
        look1 = _look1_report(tmp_path, 12)
        rows, preds = _corpus(12)

        assert aa.main(_argv(tmp_path, rows, preds, "--look1-report", str(look1))) == 2

    def test_a_decided_look_one_cannot_be_extended(self, tmp_path: Path) -> None:
        """The extension is only for an inconclusive look 1."""
        look1 = _look1_report(tmp_path, 12, verdict="pass")
        rows, preds = _corpus(120)

        assert (
            aa.main(_argv(tmp_path, rows, preds, "--look", "2", "--look1-report", str(look1))) == 2
        )

    def test_an_unreadable_look_one_report_exits_two(self, tmp_path: Path) -> None:
        rows, preds = _corpus(120)
        bad = tmp_path / "bad.json"
        bad.write_text("{not json", encoding="utf-8")

        assert aa.main(_argv(tmp_path, rows, preds, "--look", "2", "--look1-report", str(bad))) == 2


class TestCheckExtension:
    @pytest.mark.parametrize("report", [[], "x", None, {}, {"look": 1, "verdict": "inconclusive"}])
    def test_malformed_look_one_reports_are_rejected(self, report: Any) -> None:
        rows, _ = _corpus(120)

        with pytest.raises(sc.ScoreInputError):
            sc.check_extension(report, rows)

    def test_unsure_rows_count_toward_the_added_total(self) -> None:
        """A labeler who marks some of the 100 new rows unsure still labeled 100."""
        rows, _ = _corpus(112)
        for row in rows[-5:]:
            row["label"] = "unsure"
        report = {"look": 1, "verdict": "inconclusive", "heldout_band_rows": 12}

        sc.check_extension(report, rows)
