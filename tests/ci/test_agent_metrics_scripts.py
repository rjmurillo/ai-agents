"""Tests for agent-metrics CI scripts (issue #3531).

Covers:
  - collect_metrics_and_report.py
  - check_metrics_thresholds.py
  - write_metrics_threshold_summary.py
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts" / "ci"))

import check_metrics_thresholds as cmt
import collect_metrics_and_report as cmr
import write_metrics_threshold_summary as wmts

# ---------------------------------------------------------------------------
# collect_metrics_and_report
# ---------------------------------------------------------------------------

_MOCK_METRICS_OUTPUT = "# Metrics\n\nCoverage: 75%\n"
_MOCK_JSON_OUTPUT = '{"metric_2_coverage": {"coverage_rate": 75}}\n'


class TestCollectMetricsAndReport:
    def test_ok_writes_report_file(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(tmp_path)
        mock_proc = MagicMock(returncode=0, stdout=_MOCK_METRICS_OUTPUT, stderr="")
        with patch("subprocess.run", return_value=mock_proc):
            rc = cmr.main(["--since", "7", "--format", "markdown"])
        assert rc == cmr.EXIT_OK
        assert (tmp_path / "metrics-report.txt").read_text() == _MOCK_METRICS_OUTPUT

    def test_error_on_collect_failure(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        mock_proc = MagicMock(returncode=1, stdout="", stderr="")
        with patch("subprocess.run", return_value=mock_proc):
            rc = cmr.main(["--since", "7", "--format", "markdown"])
        assert rc == cmr.EXIT_ERROR

    def test_writes_step_summary_markdown(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        summary = tmp_path / "summary.md"
        monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
        mock_proc = MagicMock(returncode=0, stdout=_MOCK_METRICS_OUTPUT, stderr="")
        with patch("subprocess.run", return_value=mock_proc):
            cmr.main(["--since", "7", "--format", "markdown"])
        content = summary.read_text()
        assert "Agent Metrics Summary" in content
        assert _MOCK_METRICS_OUTPUT in content
        assert "```json" not in content

    def test_writes_step_summary_json_with_fences(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        summary = tmp_path / "summary.md"
        monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
        mock_proc = MagicMock(returncode=0, stdout=_MOCK_JSON_OUTPUT, stderr="")
        with patch("subprocess.run", return_value=mock_proc):
            cmr.main(["--since", "7", "--format", "json"])
        content = summary.read_text()
        assert "```json" in content

    def test_uses_env_var_defaults(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("PERIOD_DAYS", "14")
        monkeypatch.setenv("PERIOD_FORMAT", "summary")
        captured_cmd: list[list] = []
        mock_proc = MagicMock(returncode=0, stdout="", stderr="")

        def fake_run(cmd, **kwargs):
            captured_cmd.append(cmd)
            return mock_proc

        with patch("subprocess.run", side_effect=fake_run):
            cmr.main([])

        assert "--since" in captured_cmd[0]
        assert "14" in captured_cmd[0]
        assert "summary" in captured_cmd[0]


# ---------------------------------------------------------------------------
# check_metrics_thresholds
# ---------------------------------------------------------------------------

_OK_METRICS = {
    "metric_2_coverage": {"coverage_rate": 60.0},
    "metric_4_infrastructure_review": {"review_rate": 100.0, "infrastructure_commits": 5},
}

_LOW_COVERAGE = {
    "metric_2_coverage": {"coverage_rate": 30.0},
    "metric_4_infrastructure_review": {"review_rate": 100.0, "infrastructure_commits": 0},
}

_LOW_INFRA_RATE = {
    "metric_2_coverage": {"coverage_rate": 80.0},
    "metric_4_infrastructure_review": {"review_rate": 90.0, "infrastructure_commits": 3},
}


class TestCheckMetricsThresholds:
    def test_ok_metrics_no_alert(self) -> None:
        coverage, infra_rate, infra_commits, alert = cmt.check_thresholds(_OK_METRICS)
        assert coverage == 60.0
        assert infra_rate == 100.0
        assert not alert

    def test_low_coverage_triggers_alert(self, capsys: pytest.CaptureFixture) -> None:
        _, _, _, alert = cmt.check_thresholds(_LOW_COVERAGE)
        assert alert
        out = capsys.readouterr().out
        assert "::warning::" in out
        assert "coverage" in out.lower()

    def test_low_infra_rate_with_commits_triggers_alert(
        self, capsys: pytest.CaptureFixture
    ) -> None:
        _, _, _, alert = cmt.check_thresholds(_LOW_INFRA_RATE)
        assert alert
        out = capsys.readouterr().out
        assert "::warning::" in out

    def test_low_infra_rate_zero_commits_no_alert(self) -> None:
        metrics = {
            "metric_2_coverage": {"coverage_rate": 80.0},
            "metric_4_infrastructure_review": {"review_rate": 50.0, "infrastructure_commits": 0},
        }
        _, _, _, alert = cmt.check_thresholds(metrics)
        assert not alert

    def test_writes_github_output(self, tmp_path: Path) -> None:
        out_file = tmp_path / "output.txt"
        cmt.write_github_output(75.0, 100.0, False, str(out_file))
        content = out_file.read_text()
        assert "coverage=75.0" in content
        assert "infra_rate=100.0" in content
        assert "alert=false" in content

    def test_alert_true_in_output(self, tmp_path: Path) -> None:
        out_file = tmp_path / "output.txt"
        cmt.write_github_output(30.0, 80.0, True, str(out_file))
        content = out_file.read_text()
        assert "alert=true" in content

    def test_main_ok(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        out_file = tmp_path / "gh_output.txt"
        monkeypatch.setenv("GITHUB_OUTPUT", str(out_file))
        with patch.object(cmt, "collect_metrics_json", return_value=_OK_METRICS):
            rc = cmt.main()
        assert rc == cmt.EXIT_OK
        content = out_file.read_text()
        assert "coverage=" in content

    def test_main_error_on_bad_collect(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("GITHUB_OUTPUT", raising=False)
        with patch.object(cmt, "collect_metrics_json", side_effect=RuntimeError("boom")):
            rc = cmt.main()
        assert rc == cmt.EXIT_ERROR

    def test_infra_commits_int_not_string(self) -> None:
        metrics = {
            "metric_2_coverage": {"coverage_rate": 80.0},
            "metric_4_infrastructure_review": {"review_rate": 50.0, "infrastructure_commits": 3},
        }
        _, _, infra_commits, _ = cmt.check_thresholds(metrics)
        assert isinstance(infra_commits, int)
        assert infra_commits == 3


# ---------------------------------------------------------------------------
# write_metrics_threshold_summary
# ---------------------------------------------------------------------------


class TestWriteMetricsThresholdSummary:
    def test_builds_passing_table(self) -> None:
        text = wmts.build_summary(75.0, 100.0)
        assert ":white_check_mark:" in text
        assert ":x:" not in text
        assert "75.0%" in text

    def test_builds_failing_coverage(self) -> None:
        text = wmts.build_summary(30.0, 100.0)
        assert ":x:" in text

    def test_builds_warning_infra_rate(self) -> None:
        text = wmts.build_summary(80.0, 90.0)
        assert ":warning:" in text

    def test_main_writes_to_summary_file(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        summary = tmp_path / "summary.md"
        monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
        monkeypatch.setenv("CHECK_COVERAGE", "75.0")
        monkeypatch.setenv("CHECK_INFRA_RATE", "100.0")
        rc = wmts.main()
        assert rc == wmts.EXIT_OK
        content = summary.read_text()
        assert "Threshold Check Results" in content

    def test_main_error_on_missing_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("CHECK_COVERAGE", raising=False)
        monkeypatch.delenv("CHECK_INFRA_RATE", raising=False)
        rc = wmts.main()
        assert rc == wmts.EXIT_ERROR

    def test_main_error_on_bad_float(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        summary = tmp_path / "summary.md"
        monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
        monkeypatch.setenv("CHECK_COVERAGE", "not-a-float")
        monkeypatch.setenv("CHECK_INFRA_RATE", "100.0")
        rc = wmts.main()
        assert rc == wmts.EXIT_ERROR

    def test_prints_to_stdout_without_summary_env(
        self, capsys: pytest.CaptureFixture, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
        monkeypatch.setenv("CHECK_COVERAGE", "55.0")
        monkeypatch.setenv("CHECK_INFRA_RATE", "100.0")
        rc = wmts.main()
        assert rc == wmts.EXIT_OK
        out = capsys.readouterr().out
        assert "Threshold Check Results" in out
