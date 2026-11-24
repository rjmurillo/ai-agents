"""Input validation for the score step (group 1 of the test-gate findings).

Every malformed input must exit 2 through main(argv) with a named problem, never a
traceback, and never a verdict computed from rows that do not belong together.
Shared helpers: _actionability_arms_test_support.py.
"""

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


def _rows() -> list[dict[str, Any]]:
    truths = ["actionable"] * 3 + ["not_actionable"] * 3
    rows = [make_row(f"H{i}", label=t) for i, t in enumerate(truths)]
    rows.append(make_row("D0", split="dev", label="actionable"))
    rows.append(make_row("O0", split="outside", in_band=False, score=0.9, label="actionable"))
    return rows


def _preds() -> list[dict[str, Any]]:
    return [make_prediction(f"H{i}", is_actionable=i < 3, confidence=0.9) for i in range(6)]


def _run(
    tmp_path: Path, rows: list[dict[str, Any]], preds: list[dict[str, Any]]
) -> tuple[int, Path]:
    corpus = write_jsonl_file(tmp_path / "c.jsonl", rows)
    predictions = write_jsonl_file(tmp_path / "p.jsonl", preds)
    out = tmp_path / "report.json"
    argv = ["score", "--corpus", str(corpus), "--predictions", str(predictions)]
    return aa.main([*argv, "--output", str(out), "--bootstrap", "50", "--seed", "3"]), out


class TestSplitMismatch:
    def test_predictions_for_other_rows_exit_two_naming_the_split(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Group 1a: dev-only predictions share no id with the heldout band, so no verdict."""
        code, out = _run(tmp_path, _rows(), [make_prediction("D0")])

        assert code == 2
        assert not out.exists()
        err = capsys.readouterr().err
        assert "split" in err
        assert "heldout band" in err

    def test_predictions_for_unrelated_ids_exit_two(self, tmp_path: Path) -> None:
        """Group 1a: ids from a different corpus match nothing."""
        code, out = _run(tmp_path, _rows(), [make_prediction("OTHER1"), make_prediction("OTHER2")])

        assert code == 2
        assert not out.exists()

    def test_one_matching_prediction_is_enough_to_score(self, tmp_path: Path) -> None:
        """Group 1a: the rule is no overlap at all, not partial overlap."""
        code, _ = _run(tmp_path, _rows(), [make_prediction("H0")])

        assert code == 0

    def test_failed_predictions_for_every_row_still_score(self, tmp_path: Path) -> None:
        """Group 1a: call_error rows exist, so the ids match. That is a result, not a mismatch."""
        failed = [
            make_prediction(f"H{i}", status="call_error", is_actionable=None, confidence=None)
            for i in range(6)
        ]

        code, out = _run(tmp_path, _rows(), failed)

        assert code == 0
        assert json.loads(out.read_text(encoding="utf-8"))["predictions"]["call_error"] == 6


class TestMalformedCorpusRows:
    @pytest.mark.parametrize(
        ("key", "value"),
        [
            ("id", None),
            ("id", 5),
            ("id", ""),
            ("split", None),
            ("split", 3),
            ("split", "validation"),
            ("in_band", None),
            ("in_band", "true"),
            ("in_band", 1),
            ("heuristic_score", None),
            ("heuristic_score", "0.5"),
            ("heuristic_score", True),
            ("heuristic_score", float("inf")),
            ("label", ["actionable"]),
            ("label", 1),
            ("label", {"x": 1}),
        ],
    )
    def test_wrong_typed_key_exits_two_naming_the_key(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
        key: str,
        value: Any,
    ) -> None:
        """Group 1b: a wrong-typed required corpus key is a config error, not a traceback."""
        rows = _rows()
        rows[1][key] = value

        code, out = _run(tmp_path, rows, _preds())

        assert code == 2
        assert not out.exists()
        err = capsys.readouterr().err
        assert key in err
        assert "corpus row 2" in err

    @pytest.mark.parametrize("key", ["id", "split", "in_band", "heuristic_score"])
    def test_missing_required_key_exits_two_naming_the_key(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str], key: str
    ) -> None:
        """Group 1b: a missing required corpus key is a config error."""
        rows = _rows()
        del rows[0][key]

        code, _ = _run(tmp_path, rows, _preds())

        assert code == 2
        assert key in capsys.readouterr().err

    def test_missing_label_key_counts_as_unlabeled(self, tmp_path: Path) -> None:
        """Group 1b: an absent label is the same as null, so it reports the unlabeled count."""
        rows = _rows()
        del rows[0]["label"]

        code, _ = _run(tmp_path, rows, _preds())

        assert code == 2


class TestMalformedPredictions:
    @pytest.mark.parametrize(
        ("key", "value"),
        [
            ("id", None),
            ("id", 7),
            ("id", ""),
            ("status", None),
            ("status", 1),
            ("status", ["ok"]),
            ("is_actionable", "yes"),
            ("is_actionable", 1),
            ("confidence", "0.9"),
            ("confidence", True),
            ("confidence", float("nan")),
            ("latency_s", "fast"),
            ("model", ["m"]),
            ("provider", 3),
            ("prompt_sha256", {"a": 1}),
        ],
    )
    def test_wrong_typed_key_exits_two_naming_the_key(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
        key: str,
        value: Any,
    ) -> None:
        """Group 1b: a wrong-typed prediction key is a config error, not a traceback."""
        preds = _preds()
        preds[2][key] = value

        code, out = _run(tmp_path, _rows(), preds)

        assert code == 2
        assert not out.exists()
        err = capsys.readouterr().err
        assert key in err
        assert "predictions row 3" in err

    @pytest.mark.parametrize("key", ["id", "status"])
    def test_missing_required_key_exits_two(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str], key: str
    ) -> None:
        """Group 1b: id and status are required on every prediction record."""
        preds = _preds()
        del preds[0][key]

        code, _ = _run(tmp_path, _rows(), preds)

        assert code == 2
        assert key in capsys.readouterr().err

    def test_unknown_status_string_exits_two(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Group 1d: a status outside the known set is rejected by name."""
        preds = _preds()
        preds[0]["status"] = "timeout"

        code, out = _run(tmp_path, _rows(), preds)

        assert code == 2
        assert not out.exists()
        assert "unknown prediction status" in capsys.readouterr().err

    def test_unknown_status_raises_score_input_error_directly(self) -> None:
        """Group 1d: the build_report branch itself, without the CLI."""
        rows = [make_row("H0", label="actionable")]

        with pytest.raises(sc.ScoreInputError, match="unknown prediction status"):
            sc.build_report(
                rows,
                [make_prediction("H0", status="weird")],
                aa.ARM_FUNCTIONS,
                seed=1,
                iterations=5,
            )


class TestAllUnsure:
    def test_every_label_unsure_has_its_own_message(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Group 1c: all-unsure is not 'no heldout band rows', it is nothing to score."""
        rows = _rows()
        for row in rows:
            row["label"] = "unsure"

        code, out = _run(tmp_path, rows, _preds())

        assert code == 2
        assert not out.exists()
        err = capsys.readouterr().err
        assert "every label is unsure" in err
        assert "no heldout band rows" not in err

    def test_all_heldout_band_labels_unsure_is_named_too(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Group 1c: unsure in the band alone must not read as a missing split."""
        rows = _rows()
        for row in rows[:6]:
            row["label"] = "unsure"

        code, _ = _run(tmp_path, rows, _preds())

        assert code == 2
        assert "every heldout band label is unsure" in capsys.readouterr().err


class TestArmCRealBoolOnly:
    @pytest.mark.parametrize("value", ["no", "false", 0, 1, [], {}])
    def test_non_bool_verdict_never_overrides_the_heuristic(self, value: Any) -> None:
        """Group 1e: only a real bool is a verdict, so arm C keeps arm A's answer."""
        row = make_row("r", score=0.5)
        prediction = aa.Prediction.from_dict(
            make_prediction("r", is_actionable=value, confidence=0.99)
        )

        result = aa.arm_c(row, prediction)

        assert result is True
        assert isinstance(result, bool)

    def test_non_numeric_confidence_never_overrides_the_heuristic(self) -> None:
        """Group 1e: a string confidence cannot be compared to 0.7, so it is not applied."""
        row = make_row("r", score=0.5)
        record = make_prediction("r", is_actionable=False)
        record["confidence"] = "0.9"
        prediction = aa.Prediction.from_dict(record)

        assert aa.arm_c(row, prediction) is True

    def test_real_bool_still_applies(self) -> None:
        """Group 1e: the guard narrows, it does not disable, the fallback."""
        row = make_row("r", score=0.5)
        prediction = aa.Prediction.from_dict(
            make_prediction("r", is_actionable=False, confidence=0.9)
        )

        assert aa.arm_c(row, prediction) is False


class TestScoreStdoutAndWarning:
    def test_stdout_reports_prediction_counts_of_the_band(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Group 1f: the stdout line carries ok, parse_error, call_error, missing of N."""
        preds = [
            make_prediction("H0"),
            make_prediction("H1", status="parse_error", is_actionable=None, confidence=None),
            make_prediction("H2", status="call_error", is_actionable=None, confidence=None),
        ]

        code, _ = _run(tmp_path, _rows(), preds)

        assert code == 0
        out = capsys.readouterr().out
        assert "predictions ok 1, parse_error 1, call_error 1, missing 3 of 6" in out

    def test_warns_when_non_ok_exceeds_ten_percent_of_band_rows(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Group 1f: 3 of 6 rows without an ok prediction is over 10 percent."""
        code, _ = _run(tmp_path, _rows(), _preds()[:3])

        assert code == 0
        err = capsys.readouterr().err
        assert "3 of 6 heldout band rows" in err
        assert "no ok prediction" in err

    def test_no_warning_when_every_band_row_has_an_ok_prediction(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Group 1f: a clean run prints no warning."""
        code, _ = _run(tmp_path, _rows(), _preds())

        assert code == 0
        assert "warning" not in capsys.readouterr().err

    def test_exactly_ten_percent_does_not_warn(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Group 1f: the rule is strictly greater than 10 percent."""
        rows = [make_row(f"H{i}", label="actionable") for i in range(10)]
        preds = [make_prediction(f"H{i}") for i in range(9)]

        code, _ = _run(tmp_path, rows, preds)

        assert code == 0
        assert "no ok prediction" not in capsys.readouterr().err


class TestGapFromCounts:
    def test_non_positive_n_is_rejected(self) -> None:
        """Group 1g: the n <= 0 guard is public behavior, so it is tested directly."""
        with pytest.raises(ValueError, match="n must be positive"):
            sc.gap_from_counts(1, 0, 0)
        with pytest.raises(ValueError, match="n must be positive"):
            sc.gap_from_counts(1, 0, -3)
