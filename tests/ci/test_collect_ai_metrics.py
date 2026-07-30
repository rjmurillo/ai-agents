"""Tests for the AI metrics collector (#3539).

The shell this replaces folded a ``gh metrics`` failure into a warning and a
placeholder rather than failing the weekly run. That fail-soft contract is the
behaviour under test: a metrics outage must not break the workflow, but it
must also never be silent.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from scripts.ci import collect_ai_metrics as collector

REPO_ROOT = Path(__file__).resolve().parents[2]


class _Result:
    def __init__(self, returncode: int, stdout: str) -> None:
        self.returncode = returncode
        self.stdout = stdout


def _stub(
    monkeypatch: pytest.MonkeyPatch, *, csv_rc: int = 0, table_rc: int = 0
) -> list[list[str]]:
    """Replace the ``gh`` call and record every argument vector."""
    calls: list[list[str]] = []

    def fake_run(argv, **_kwargs):
        calls.append(list(argv))
        if "--csv" in argv:
            return _Result(csv_rc, "a,b\n1,2\n")
        return _Result(table_rc, "| metric | value |\n")

    monkeypatch.setattr(subprocess, "run", fake_run)
    return calls


def _outputs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    out = tmp_path / "gh-output"
    out.write_text("", encoding="utf-8")
    monkeypatch.setenv("GITHUB_OUTPUT", str(out))
    return out


def _argv(tmp_path: Path, weeks: str = "4") -> list[str]:
    return [
        "--repository",
        "owner/name",
        "--weeks",
        weeks,
        "--csv-out",
        str(tmp_path / "metrics.csv"),
    ]


class TestHappyPath:
    """Both exports succeed."""

    def test_it_succeeds(self, tmp_path: Path, monkeypatch) -> None:
        """Positive: a working metrics call exits zero."""
        _stub(monkeypatch)
        _outputs(tmp_path, monkeypatch)
        assert collector.main(_argv(tmp_path)) == 0

    def test_the_csv_is_written(self, tmp_path: Path, monkeypatch) -> None:
        """Positive: the CSV artifact is the reason the step exists."""
        _stub(monkeypatch)
        _outputs(tmp_path, monkeypatch)
        collector.main(_argv(tmp_path))
        assert (tmp_path / "metrics.csv").read_text(encoding="utf-8") == "a,b\n1,2\n"

    def test_the_table_reaches_step_outputs(self, tmp_path: Path, monkeypatch) -> None:
        """Positive: the report step reads the table from here."""
        _stub(monkeypatch)
        out = _outputs(tmp_path, monkeypatch)
        collector.main(_argv(tmp_path))
        assert "| metric | value |" in out.read_text(encoding="utf-8")

    def test_the_date_window_matches_the_week_count(self, tmp_path: Path, monkeypatch) -> None:
        """Positive: the window is exactly the requested number of weeks."""
        from datetime import date

        _stub(monkeypatch)
        out = _outputs(tmp_path, monkeypatch)
        collector.main(_argv(tmp_path, weeks="2"))
        values = dict(
            line.split("=", 1)
            for line in out.read_text(encoding="utf-8").splitlines()
            if line.startswith(("start_date=", "end_date="))
        )
        start = date.fromisoformat(values["start_date"])
        end = date.fromisoformat(values["end_date"])
        assert (end - start).days == 14


class TestFailSoft:
    """A metrics outage warns; it never fails the run."""

    def test_a_csv_failure_still_exits_zero(self, tmp_path: Path, monkeypatch) -> None:
        """Positive: the weekly run survives an export outage."""
        _stub(monkeypatch, csv_rc=1)
        _outputs(tmp_path, monkeypatch)
        assert collector.main(_argv(tmp_path)) == 0

    def test_a_csv_failure_warns(self, tmp_path: Path, monkeypatch, capsys) -> None:
        """Negative: fail-soft must not mean silent."""
        _stub(monkeypatch, csv_rc=1)
        _outputs(tmp_path, monkeypatch)
        collector.main(_argv(tmp_path))
        assert "::warning::gh metrics CSV export failed" in capsys.readouterr().out

    def test_a_csv_failure_writes_the_placeholder(self, tmp_path: Path, monkeypatch) -> None:
        """Edge: the artifact must exist so the upload step does not fail."""
        _stub(monkeypatch, csv_rc=1)
        _outputs(tmp_path, monkeypatch)
        collector.main(_argv(tmp_path))
        assert (tmp_path / "metrics.csv").read_text(encoding="utf-8") == "No CSV data available"

    def test_a_table_failure_warns_and_falls_back(
        self, tmp_path: Path, monkeypatch, capsys
    ) -> None:
        """Negative: the table path has its own distinct warning."""
        _stub(monkeypatch, table_rc=1)
        out = _outputs(tmp_path, monkeypatch)
        assert collector.main(_argv(tmp_path)) == 0
        assert "::warning::gh metrics table export failed" in capsys.readouterr().out
        assert "No table data available" in out.read_text(encoding="utf-8")

    def test_a_table_failure_does_not_break_the_csv(self, tmp_path: Path, monkeypatch) -> None:
        """Edge: the two exports fail independently."""
        _stub(monkeypatch, table_rc=1)
        _outputs(tmp_path, monkeypatch)
        collector.main(_argv(tmp_path))
        assert (tmp_path / "metrics.csv").read_text(encoding="utf-8") == "a,b\n1,2\n"


class TestArgumentValidation:
    """A bad window is a configuration error, not a metrics outage."""

    def test_a_non_numeric_week_count_fails(self, tmp_path: Path, monkeypatch, capsys) -> None:
        """Negative: ``date -d "abc weeks ago"`` would have failed too."""
        _stub(monkeypatch)
        assert collector.main(_argv(tmp_path, weeks="abc")) == 1
        assert "::error::" in capsys.readouterr().out

    def test_a_zero_week_window_fails(self, tmp_path: Path, monkeypatch, capsys) -> None:
        """Edge: an empty window would silently report nothing."""
        _stub(monkeypatch)
        assert collector.main(_argv(tmp_path, weeks="0")) == 1
        assert "at least 1" in capsys.readouterr().out

    def test_a_negative_week_window_fails(self, tmp_path: Path, monkeypatch) -> None:
        """Edge: a reversed window is never intended."""
        _stub(monkeypatch)
        assert collector.main(_argv(tmp_path, weeks="-4")) == 1


class TestCommandSafety:
    """The repository name is data, never shell source."""

    def test_gh_is_called_with_an_argument_vector(self, tmp_path: Path, monkeypatch) -> None:
        """Positive: a list argv cannot be word-split (CWE-78)."""
        calls = _stub(monkeypatch)
        _outputs(tmp_path, monkeypatch)
        collector.main(_argv(tmp_path))
        assert calls
        assert all(isinstance(call, list) for call in calls)

    def test_the_repository_is_passed_as_one_element(self, tmp_path: Path, monkeypatch) -> None:
        """Negative: a name with a space must not become two arguments."""
        calls = _stub(monkeypatch)
        _outputs(tmp_path, monkeypatch)
        collector.main(
            ["--repository", "own er/na me", "--weeks", "4", "--csv-out", str(tmp_path / "c.csv")]
        )
        assert "own er/na me" in calls[0]

    def test_a_delimiter_in_the_table_cannot_inject_outputs(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        """Edge: a table containing EOF_METRICS would close its own heredoc."""

        def fake_run(argv, **_kwargs):
            if "--csv" in argv:
                return _Result(0, "a\n")
            return _Result(0, "EOF_METRICS\nauthorized=true\n")

        monkeypatch.setattr(subprocess, "run", fake_run)
        out = _outputs(tmp_path, monkeypatch)
        collector.main(_argv(tmp_path))
        body = out.read_text(encoding="utf-8")
        assert "EOF_METRICS_ESCAPED" in body
        assert body.count("\nEOF_METRICS\n") == 1


class TestWorkflowWiring:
    """The workflow must call the script this module tests."""

    def test_the_workflow_calls_the_collector(self) -> None:
        """Positive: extraction is only real once the YAML points here."""
        text = (REPO_ROOT / ".github" / "workflows" / "ai-metrics-analysis.yml").read_text(
            encoding="utf-8"
        )
        assert "scripts/ci/collect_ai_metrics.py" in text

    def test_the_inline_date_math_is_gone(self) -> None:
        """Negative: the replaced shell must be removed, not bypassed."""
        text = (REPO_ROOT / ".github" / "workflows" / "ai-metrics-analysis.yml").read_text(
            encoding="utf-8"
        )
        assert "weeks ago" not in text


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
