"""PR-clustered bootstrap and the report fields around it (review round 2, group A).

Plan M1-T15. Comments in one PR are correlated, so resampling single rows gives an interval
that is too narrow. The bootstrap draws whole PRs and recomputes the gap from every row of
the drawn PRs.
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


def _one_pr_holds_every_win() -> tuple[list[int], list[int]]:
    """20 rows. PR 1 holds 10 C wins. PRs 2 to 11 hold one neutral row each."""
    diffs = [1] * 10 + [0] * 10
    clusters = [1] * 10 + list(range(2, 12))
    return diffs, clusters


class TestClusterBootstrap:
    def test_one_pr_holding_every_win_gives_a_wider_interval_than_the_row_bootstrap(self) -> None:
        """A draw that misses PR 1 has gap 0, which a row-level draw almost never produces."""
        diffs, clusters = _one_pr_holds_every_win()

        row_low, row_high = sc.paired_bootstrap_ci(diffs, seed=3, iterations=4000)
        pr_low, pr_high = sc.paired_bootstrap_ci(diffs, seed=3, iterations=4000, clusters=clusters)

        assert pr_low < row_low
        assert (pr_high - pr_low) > (row_high - row_low)
        assert pr_low == 0.0

    def test_seeded_results_reproduce(self) -> None:
        """Same seed, same clusters, same interval."""
        diffs, clusters = _one_pr_holds_every_win()

        first = sc.paired_bootstrap_ci(diffs, seed=9, iterations=1500, clusters=clusters)
        again = sc.paired_bootstrap_ci(diffs, seed=9, iterations=1500, clusters=clusters)

        assert first == again

    def test_the_seed_drives_the_cluster_draws(self) -> None:
        """With few iterations different seeds give different intervals."""
        diffs, clusters = _one_pr_holds_every_win()

        intervals = {
            sc.paired_bootstrap_ci(diffs, seed=s, iterations=3, clusters=clusters)
            for s in range(1, 9)
        }

        assert len(intervals) > 1

    def test_the_gap_is_recomputed_from_all_rows_of_the_drawn_prs(self) -> None:
        """A 3-row PR of wins and a 1-row PR of zero: drawing both is 3/4, not a mean of means."""
        diffs = [1, 1, 1, 0]
        clusters = [10, 10, 10, 20]

        gaps = sc.bootstrap_gaps(diffs, seed=1, iterations=400, clusters=clusters)

        assert set(gaps) == {0.0, 0.75, 1.0}

    def test_without_clusters_every_row_is_its_own_cluster(self) -> None:
        """clusters=None is the row-level bootstrap, kept for comparison."""
        diffs = [1, 0, 0, 1, 0]

        by_row = sc.bootstrap_gaps(diffs, seed=2, iterations=300)
        singletons = sc.bootstrap_gaps(diffs, seed=2, iterations=300, clusters=[1, 2, 3, 4, 5])

        assert by_row == singletons

    def test_one_cluster_collapses_to_a_point(self) -> None:
        """Nothing to resample: the interval is the gap itself."""
        assert sc.paired_bootstrap_ci([1, 0, 1], seed=1, iterations=50, clusters=[7, 7, 7]) == (
            pytest.approx(2 / 3),
            pytest.approx(2 / 3),
        )

    def test_mismatched_lengths_are_rejected(self) -> None:
        """diffs and clusters must line up."""
        with pytest.raises(ValueError, match="length"):
            sc.paired_bootstrap_ci([1, 0], seed=1, iterations=10, clusters=[1])


def _scenario_rows(pr_of: dict[int, int]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """20 heldout band rows: H0..H9 not_actionable (C flips them right), H10..H19 actionable."""
    rows, preds = [], []
    for i in range(20):
        truth = "not_actionable" if i < 10 else "actionable"
        rows.append(make_row(f"H{i}", label=truth, pr_number=pr_of[i]))
        if i < 10:
            preds.append(make_prediction(f"H{i}", is_actionable=False, confidence=0.9))
    preds.append(make_prediction("H19", is_actionable=True, confidence=0.9))
    return rows, preds


class TestReportClusters:
    def test_the_report_names_the_unit_and_the_cluster_count(self) -> None:
        """bootstrap_unit is pr and n_clusters counts the PRs of the scored heldout band rows."""
        rows, preds = _scenario_rows({i: i + 1 for i in range(20)})
        rows.append(make_row("D0", split="dev", label="actionable", pr_number=999))
        rows.append(
            make_row("O0", split="outside", in_band=False, label="actionable", pr_number=998)
        )

        report = sc.build_report(rows, preds, aa.ARM_FUNCTIONS, seed=5, iterations=500)

        assert report["bootstrap_unit"] == "pr"
        assert report["n_clusters"] == 20

    def test_rows_of_one_pr_count_once(self) -> None:
        """Ten rows in PR 1 and ten PRs of one row each make 11 clusters."""
        pr_of = {i: 1 if i < 10 else i for i in range(20)}
        rows, preds = _scenario_rows(pr_of)

        report = sc.build_report(rows, preds, aa.ARM_FUNCTIONS, seed=5, iterations=500)

        assert report["n_clusters"] == 11

    def test_the_report_interval_is_wider_when_one_pr_holds_every_win(self) -> None:
        """Same rows and predictions, different PR layout: clustering widens the interval."""
        independent, preds = _scenario_rows({i: i + 1 for i in range(20)})
        grouped, _ = _scenario_rows({i: 1 if i < 10 else i for i in range(20)})

        wide = sc.build_report(grouped, preds, aa.ARM_FUNCTIONS, seed=5, iterations=3000)
        narrow = sc.build_report(independent, preds, aa.ARM_FUNCTIONS, seed=5, iterations=3000)

        assert wide["gap"] == narrow["gap"]
        assert (wide["gap_ci"][1] - wide["gap_ci"][0]) > (narrow["gap_ci"][1] - narrow["gap_ci"][0])

    def test_a_single_pr_cannot_be_bootstrapped(self) -> None:
        """One cluster would give a zero-width interval and a false pass."""
        rows, preds = _scenario_rows({i: 1 for i in range(20)})

        with pytest.raises(sc.ScoreInputError, match="at least 2 PRs"):
            sc.build_report(rows, preds, aa.ARM_FUNCTIONS, seed=5, iterations=100)


def _argv(tmp_path: Path, rows: list[dict[str, Any]], preds: list[dict[str, Any]]) -> list[str]:
    corpus = write_jsonl_file(tmp_path / "c.jsonl", rows)
    predictions = write_jsonl_file(tmp_path / "p.jsonl", preds)
    return [
        "score",
        "--corpus",
        str(corpus),
        "--predictions",
        str(predictions),
        "--output",
        str(tmp_path / "report.json"),
        "--bootstrap",
        "300",
    ]


class TestPrNumberValidation:
    @pytest.mark.parametrize("value", [None, "12", True, 1.5, [1]])
    def test_a_missing_or_wrong_typed_pr_number_exits_two(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
        value: Any,
    ) -> None:
        """Through main(argv): the clustering needs an int PR number on every row."""
        rows, preds = _scenario_rows({i: i + 1 for i in range(20)})
        rows[3]["pr_number"] = value

        code = aa.main(_argv(tmp_path, rows, preds))

        err = capsys.readouterr().err
        assert code == 2
        assert not (tmp_path / "report.json").exists()
        assert "pr_number" in err
        assert "corpus row 4" in err

    def test_an_absent_pr_number_exits_two(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """A row with no pr_number key at all is the same error."""
        rows, preds = _scenario_rows({i: i + 1 for i in range(20)})
        del rows[0]["pr_number"]

        code = aa.main(_argv(tmp_path, rows, preds))

        assert code == 2
        assert "pr_number" in capsys.readouterr().err

    def test_one_pr_exits_two_through_main(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """All rows in one PR is a config error, not a verdict."""
        rows, preds = _scenario_rows({i: 1 for i in range(20)})

        code = aa.main(_argv(tmp_path, rows, preds))

        assert code == 2
        assert "at least 2 PRs" in capsys.readouterr().err


class TestSummaryLine:
    def test_the_ci_label_comes_from_the_report_level(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """A level of 0.9 in the report prints as 90% CI, so nothing is hard coded."""
        real = aa.build_report

        def patched(*args: Any, **kwargs: Any) -> dict[str, Any]:
            report = real(*args, **kwargs)
            report["gap_ci_level"] = 0.9
            return report

        monkeypatch.setattr(aa, "build_report", patched)
        rows, preds = _scenario_rows({i: i + 1 for i in range(20)})

        assert aa.main(_argv(tmp_path, rows, preds)) == 0

        out = capsys.readouterr().out
        assert "90% CI" in out
        assert "95% CI" not in out

    def test_the_real_label_is_97_5_percent(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """With the shipped interval the line says 97.5% CI."""
        rows, preds = _scenario_rows({i: i + 1 for i in range(20)})

        assert aa.main(_argv(tmp_path, rows, preds)) == 0

        assert "97.5% CI" in capsys.readouterr().out

    def test_the_line_reports_unsure_count_and_share(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Group A4: unsure rows are dropped and the line says how many."""
        rows, preds = _scenario_rows({i: i + 1 for i in range(20)})
        rows[12]["label"] = "unsure"

        assert aa.main(_argv(tmp_path, rows, preds)) == 0

        assert "unsure 1 (5.0%)" in capsys.readouterr().out


class TestReportFields:
    def test_unsure_share_is_in_the_report(self, tmp_path: Path) -> None:
        """unsure_dropped and unsure_share, with no cap applied."""
        rows, preds = _scenario_rows({i: i + 1 for i in range(20)})
        for i in (11, 12, 13, 14):
            rows[i]["label"] = "unsure"

        assert aa.main(_argv(tmp_path, rows, preds)) == 0

        labels = json.loads((tmp_path / "report.json").read_text(encoding="utf-8"))["labels"]
        assert labels["unsure_dropped"] == 4
        assert labels["unsure_share"] == pytest.approx(0.2)
        assert labels["scored"] == 16

    def test_a_high_unsure_share_is_reported_not_refused(self, tmp_path: Path) -> None:
        """The cap is an owner decision, so a run with half the rows unsure still scores."""
        rows, preds = _scenario_rows({i: i + 1 for i in range(20)})
        for i in range(10, 20):
            rows[i]["label"] = "unsure"

        code = aa.main(_argv(tmp_path, rows, preds))

        assert code == 0
        labels = json.loads((tmp_path / "report.json").read_text(encoding="utf-8"))["labels"]
        assert labels["unsure_share"] == 0.5

    def test_the_observed_gap_is_labeled_descriptive(self) -> None:
        """A7: the post-hoc minimum detectable gap is named so nobody reads it as a power claim."""
        rows, preds = _scenario_rows({i: i + 1 for i in range(20)})

        mdg = sc.build_report(rows, preds, aa.ARM_FUNCTIONS, seed=1, iterations=100)[
            "minimum_detectable_gap"
        ]

        assert "observed_descriptive" in mdg
        assert "observed" not in mdg
        assert set(mdg["assumed"]) == {"0.1", "0.2", "0.3"}

    def test_the_verdict_does_not_depend_on_the_descriptive_gap(self) -> None:
        """The verdict function has no input for it, so changing it cannot move the verdict."""
        assert sc.verdict.__code__.co_varnames[:3] == ("gap", "ci_low", "ci_high")
        assert sc.verdict(0.2, 0.05, 0.4) == "pass"


class TestDocumentedRules:
    def test_min_detectable_gap_is_marked_approximate(self) -> None:
        """A6: the formula is a normal approximation."""
        assert "approximate (normal approximation)" in (sc.min_detectable_gap.__doc__ or "")

    def test_the_tie_rule_is_documented_where_the_baseline_is_chosen(self) -> None:
        """A5: arm A wins a tie between the baselines."""
        assert "A wins ties" in (sc._gap_section.__doc__ or "")

    def test_the_tie_rule_holds(self) -> None:
        """Equal baseline accuracy picks A."""
        rows = [
            make_row(f"H{i}", label="actionable" if i % 2 else "not_actionable") for i in range(10)
        ]
        preds = [make_prediction("H0", is_actionable=False, confidence=0.9)]

        report = sc.build_report(rows, preds, aa.ARM_FUNCTIONS, seed=1, iterations=50)

        assert (
            report["heldout_band"]["arms"]["A"]["accuracy"]
            == report["heldout_band"]["arms"]["B"]["accuracy"]
        )
        assert report["best_baseline"] == "A"
