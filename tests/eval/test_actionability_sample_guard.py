"""Sample refuses a split with no heldout rows; score times only the scored rows.

Review finding 10. Plan M1-T7 (dev-count versus band rows) and M1-T15 (latency).
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
from tests.eval._actionability_corpus_test_support import (
    FROZEN_NOW,
    cc,
    corpus_prs,
    read_rows,
    write_prs,
)

pytestmark = pytest.mark.usefixtures("freeze_actionability_clock")


@pytest.fixture(autouse=True)
def _frozen(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cc, "utc_now_iso", lambda: FROZEN_NOW)
    monkeypatch.setattr(cc, "head_sha", lambda: "abc")


def _sample(tmp_path: Path, *, band_pool: int, band_count: int, dev_count: int) -> tuple[int, Path]:
    prs = write_prs(tmp_path / "prs.json", corpus_prs(band=band_pool, outside=2))
    out = tmp_path / "corpus.jsonl"
    argv = ["sample", "--prs", str(prs), "--output", str(out)]
    argv += ["--band-count", str(band_count), "--outside-count", "2"]
    return cc.main([*argv, "--dev-count", str(dev_count)]), out


class TestDevCountGuard:
    @pytest.mark.parametrize("dev_count", [4, 5, 40])
    def test_dev_rows_that_take_every_band_row_exit_two(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
        dev_count: int,
    ) -> None:
        """Four band rows and dev-count 4 or more leaves no heldout row, so there is no result."""
        code, out = _sample(tmp_path, band_pool=6, band_count=4, dev_count=dev_count)

        err = capsys.readouterr().err
        assert code == 2
        assert not out.exists()
        assert f"--dev-count {dev_count}" in err
        assert "4 band rows" in err
        assert "no heldout" in err

    def test_the_message_names_the_pool_and_the_requested_count(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """A shortfall explains itself: asked for 10, the pool held 3."""
        code, _ = _sample(tmp_path, band_pool=3, band_count=10, dev_count=3)

        err = capsys.readouterr().err
        assert code == 2
        assert "3 band rows" in err
        assert "band pool 3" in err
        assert "--band-count 10" in err

    def test_one_heldout_row_is_enough(self, tmp_path: Path) -> None:
        """The guard trips only when heldout would be empty."""
        code, out = _sample(tmp_path, band_pool=6, band_count=4, dev_count=3)

        rows = read_rows(out)
        assert code == 0
        assert [r["split"] for r in rows].count("heldout") == 1
        assert [r["split"] for r in rows].count("dev") == 3

    def test_a_zero_dev_count_is_allowed(self, tmp_path: Path) -> None:
        """No dev split is a valid choice, and every band row is heldout."""
        code, out = _sample(tmp_path, band_pool=4, band_count=4, dev_count=0)

        assert code == 0
        assert {r["split"] for r in read_rows(out) if r["in_band"]} == {"heldout"}

    def test_an_empty_band_pool_is_not_this_guard(self, tmp_path: Path) -> None:
        """No band rows at all is a different situation, handled by the shortfall warning."""
        prs = write_prs(tmp_path / "prs.json", corpus_prs(band=0, outside=3))
        out = tmp_path / "corpus.jsonl"
        argv = ["sample", "--prs", str(prs), "--output", str(out)]

        code = cc.main([*argv, "--band-count", "5", "--outside-count", "3", "--dev-count", "2"])

        assert code == 0
        assert {r["split"] for r in read_rows(out)} == {"outside"}


def _rows() -> list[dict[str, Any]]:
    truths = ["actionable"] * 3 + ["not_actionable"] * 3
    rows = [make_row(f"H{i}", label=t) for i, t in enumerate(truths)]
    rows.append(make_row("D0", split="dev", label="actionable"))
    rows.append(make_row("O0", split="outside", in_band=False, score=0.9, label="actionable"))
    return rows


class TestLatencyScope:
    def test_dev_and_outside_predictions_do_not_enter_the_percentiles(self, tmp_path: Path) -> None:
        """Only the scored heldout band rows set p50 and p95."""
        preds = [make_prediction(f"H{i}", latency_s=float(i + 1)) for i in range(4)]
        preds += [make_prediction("D0", latency_s=99.0), make_prediction("O0", latency_s=88.0)]
        corpus = write_jsonl_file(tmp_path / "c.jsonl", _rows())
        predictions = write_jsonl_file(tmp_path / "p.jsonl", preds)
        out = tmp_path / "report.json"
        argv = ["score", "--corpus", str(corpus), "--predictions", str(predictions)]

        code = aa.main([*argv, "--output", str(out), "--bootstrap", "20"])

        latency = json.loads(out.read_text(encoding="utf-8"))["latency_s"]
        assert code == 0
        assert latency == {
            "p50": 2.0,
            "p95": 4.0,
            "n_ok": 4,
            "n_call_error": 0,
            "call_error_s_total": 0,
        }

    def test_a_dropped_unsure_row_is_not_timed(self) -> None:
        """An unsure heldout row is not scored, so its call does not count either."""
        rows = _rows()
        rows[0]["label"] = "unsure"
        preds = [make_prediction(f"H{i}", latency_s=float(i + 1) * 10) for i in range(6)]

        report = sc.build_report(rows, preds, aa.ARM_FUNCTIONS, seed=1, iterations=20)

        assert report["latency_s"]["n_ok"] == 5
        assert report["latency_s"]["p95"] == 60.0

    def test_failed_predictions_for_scored_rows_stay_out(self) -> None:
        """Failed calls stay out of the percentiles but are counted with their wall time."""
        preds = [
            make_prediction("H0", latency_s=1.0),
            make_prediction("H1", status="call_error", is_actionable=None, latency_s=50.0),
        ]

        report = sc.build_report(_rows(), preds, aa.ARM_FUNCTIONS, seed=1, iterations=20)

        assert report["latency_s"] == {
            "p50": 1.0,
            "p95": 1.0,
            "n_ok": 1,
            "n_call_error": 1,
            "call_error_s_total": 50.0,
        }

    def test_no_scored_ok_prediction_gives_null_percentiles(self) -> None:
        """The empty case still returns nulls."""
        preds = [make_prediction("D0", latency_s=5.0), make_prediction("H0", status="call_error")]

        report = sc.build_report(_rows(), preds, aa.ARM_FUNCTIONS, seed=1, iterations=20)

        assert report["latency_s"]["p50"] is None
        assert report["latency_s"]["p95"] is None
        assert report["latency_s"]["n_ok"] == 0
        assert report["latency_s"]["n_call_error"] == 1
