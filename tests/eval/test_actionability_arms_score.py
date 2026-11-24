"""Tests for the score subcommand of scripts/eval/actionability_arms.py.

Plan M1-T15, premortem R1 and R2. Shared helpers: _actionability_arms_test_support.py.
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
    read_jsonl_file,
    write_jsonl_file,
)


def _rows() -> list[dict[str, Any]]:
    truths = ["actionable"] * 5 + ["not_actionable"] * 5
    heldout = [make_row(f"H{i}", label=truth) for i, truth in enumerate(truths)]
    dev = [make_row("D0", split="dev", label="actionable")]
    outside = [make_row("O0", split="outside", in_band=False, score=0.9, label="actionable")]
    return heldout + dev + outside


def _preds() -> list[dict[str, Any]]:
    return [make_prediction(f"H{i}", is_actionable=i < 5, confidence=0.9) for i in range(10)]


def _argv(corpus: Path, preds: Path, out: Path, *extra: str) -> list[str]:
    return [
        "score",
        "--corpus",
        str(corpus),
        "--predictions",
        str(preds),
        "--output",
        str(out),
        "--seed",
        "9",
        "--bootstrap",
        "500",
        *extra,
    ]


def _files(
    tmp_path: Path, rows: list[dict[str, Any]], preds: list[dict[str, Any]]
) -> tuple[Path, Path, Path]:
    corpus = write_jsonl_file(tmp_path / "corpus.jsonl", rows)
    predictions = write_jsonl_file(tmp_path / "pred.jsonl", preds)
    return corpus, predictions, tmp_path / "report.json"


class TestScoreCli:
    def test_writes_the_report_and_returns_zero(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Plan M1-T15: end to end through main(argv)."""
        corpus, preds, out = _files(tmp_path, _rows(), _preds())

        code = aa.main(_argv(corpus, preds, out))

        report = json.loads(out.read_text(encoding="utf-8"))
        assert code == 0
        assert report["heldout_band"]["n"] == 10
        assert report["heldout_band"]["arms"]["C"]["accuracy"] == 1.0
        assert report["non_dev"]["n"] == 11
        assert report["verdict"] == "pass"
        assert "verdict" in capsys.readouterr().out

    def test_same_inputs_and_seed_give_byte_identical_reports(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Plan M1-T15: with the clock and head frozen, the report bytes repeat."""
        monkeypatch.setattr(aa, "utc_now_iso", lambda: "2026-11-24T12:00:00+00:00")
        monkeypatch.setattr(aa, "head_sha", lambda: "deadbeef")
        corpus, preds, first = _files(tmp_path, _rows(), _preds())
        second = tmp_path / "second.json"

        assert aa.main(_argv(corpus, preds, first)) == 0
        assert aa.main(_argv(corpus, preds, second)) == 0

        assert first.read_bytes() == second.read_bytes()

    def test_unlabeled_rows_return_two_and_name_the_count(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Plan M1-T15: a null label is a config error."""
        rows = _rows()
        rows[0]["label"] = None
        rows[1]["label"] = None
        corpus, preds, out = _files(tmp_path, rows, _preds())

        code = aa.main(_argv(corpus, preds, out))

        assert code == 2
        assert not out.exists()
        assert "2 unlabeled" in capsys.readouterr().err

    def test_mixed_prompt_hashes_return_two(self, tmp_path: Path) -> None:
        """Plan M1-T15: predictions from two prompts cannot share a report."""
        preds = _preds()
        preds[0]["prompt_sha256"] = "q" * 64
        corpus, pred_path, out = _files(tmp_path, _rows(), preds)

        assert aa.main(_argv(corpus, pred_path, out)) == 2
        assert not out.exists()

    def test_mixed_models_return_two(self, tmp_path: Path) -> None:
        """Plan M1-T15: predictions from two models cannot share a report."""
        preds = _preds()
        preds[0]["model"] = "other-model"
        corpus, pred_path, out = _files(tmp_path, _rows(), preds)

        assert aa.main(_argv(corpus, pred_path, out)) == 2

    def test_unreadable_inputs_return_two(self, tmp_path: Path) -> None:
        """Plan M1-T15: missing files are config errors."""
        corpus, preds, out = _files(tmp_path, _rows(), _preds())

        assert aa.main(_argv(tmp_path / "none.jsonl", preds, out)) == 2
        assert aa.main(_argv(corpus, tmp_path / "none.jsonl", out)) == 2
        assert not out.exists()

    def test_non_positive_bootstrap_returns_two(self, tmp_path: Path) -> None:
        """Plan M1-T15: the bootstrap needs at least one iteration."""
        corpus, preds, out = _files(tmp_path, _rows(), _preds())
        argv = _argv(corpus, preds, out)
        argv[argv.index("500")] = "0"

        assert aa.main(argv) == 2

    def test_missing_heldout_predictions_are_reported_not_hidden(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Premortem R2: rows with no prediction are counted and warned about."""
        corpus, preds, out = _files(tmp_path, _rows(), _preds()[:6])

        code = aa.main(_argv(corpus, preds, out))

        report = json.loads(out.read_text(encoding="utf-8"))
        assert code == 0
        assert report["predictions"]["missing"] == 4
        assert "4" in capsys.readouterr().err

    def test_scoring_never_rescores_with_the_heuristic(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Premortem R1: score all arms with the production scorer patched to raise."""

        def _boom(*_args: object, **_kwargs: object) -> None:
            raise AssertionError("get_actionability_score was called")

        import scripts.eval.actionability_corpus as corpus_module
        import scripts.update_reviewer_signal_stats as stats

        monkeypatch.setattr(stats, "get_actionability_score", _boom)
        monkeypatch.setattr(corpus_module, "get_actionability_score", _boom)
        corpus, preds, out = _files(tmp_path, _rows(), _preds())

        assert aa.main(_argv(corpus, preds, out)) == 0
        assert read_jsonl_file(preds)

    def test_score_subcommand_does_not_need_a_model_or_a_key(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Plan M1-T15: scoring is offline."""
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        corpus, preds, out = _files(tmp_path, _rows(), _preds())

        assert aa.main(_argv(corpus, preds, out)) == 0
