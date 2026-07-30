"""Tests for the memory health result parser (#3541).

The shell this replaces derived a ``has_stale`` flag from a ``jq`` read and
tolerated both a missing report and a missing key. Those two tolerances are
the reason the downstream comment step never breaks, so they are pinned here.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.ci import parse_memory_health_results as parser

REPO_ROOT = Path(__file__).resolve().parents[2]


def _report(tmp_path: Path, summary: object) -> Path:
    path = tmp_path / "health-report.json"
    path.write_text(json.dumps({"summary": summary}), encoding="utf-8")
    return path


def _outputs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    out = tmp_path / "gh-output"
    out.write_text("", encoding="utf-8")
    monkeypatch.setenv("GITHUB_OUTPUT", str(out))
    return out


def _parsed(out: Path) -> dict[str, str]:
    return dict(
        line.split("=", 1) for line in out.read_text(encoding="utf-8").splitlines() if line
    )


class TestMissingReport:
    """A missing report is not a failure."""

    def test_missing_report_succeeds(self, tmp_path: Path, monkeypatch) -> None:
        """Positive: the step exits zero so the comment step still runs."""
        out = _outputs(tmp_path, monkeypatch)
        rc = parser.main(["--results", str(tmp_path / "absent.json")])
        assert rc == 0
        assert _parsed(out) == {"has_stale": "false", "total": "0"}

    def test_missing_report_emits_no_other_fields(self, tmp_path: Path, monkeypatch) -> None:
        """Negative: the summary fields must stay absent, not empty."""
        out = _outputs(tmp_path, monkeypatch)
        parser.main(["--results", str(tmp_path / "absent.json")])
        assert "healthy=" not in out.read_text(encoding="utf-8")


class TestStaleFlag:
    """``has_stale`` drives whether a PR comment is posted."""

    def test_positive_stale_count_sets_the_flag(self, tmp_path: Path, monkeypatch) -> None:
        """Positive: any stale memory raises the flag."""
        out = _outputs(tmp_path, monkeypatch)
        summary = {"total": 9, "healthy": 6, "stale": 3, "exempt": 0, "errors": 0}
        results = _report(tmp_path, summary)
        assert parser.main(["--results", str(results)]) == 0
        assert _parsed(out)["has_stale"] == "true"

    def test_zero_stale_count_clears_the_flag(self, tmp_path: Path, monkeypatch) -> None:
        """Negative: a healthy repository must not post a comment."""
        out = _outputs(tmp_path, monkeypatch)
        summary = {"total": 9, "healthy": 9, "stale": 0, "exempt": 0, "errors": 0}
        results = _report(tmp_path, summary)
        parser.main(["--results", str(results)])
        assert _parsed(out)["has_stale"] == "false"

    def test_all_summary_fields_are_emitted(self, tmp_path: Path, monkeypatch) -> None:
        """Positive: every value the comment step reads is present."""
        out = _outputs(tmp_path, monkeypatch)
        summary = {"total": 9, "healthy": 6, "stale": 3, "exempt": 1, "errors": 2}
        results = _report(tmp_path, summary)
        parser.main(["--results", str(results)])
        parsed = _parsed(out)
        assert parsed["total"] == "9"
        assert parsed["healthy"] == "6"
        assert parsed["stale"] == "3"
        assert parsed["exempt"] == "1"
        assert parsed["errors"] == "2"

    def test_a_missing_stale_key_is_not_stale(self, tmp_path: Path, monkeypatch) -> None:
        """Edge: ``jq`` emitted ``null`` and the shell test errored to false."""
        out = _outputs(tmp_path, monkeypatch)
        results = _report(tmp_path, {"total": 9})
        assert parser.main(["--results", str(results)]) == 0
        parsed = _parsed(out)
        assert parsed["has_stale"] == "false"
        assert parsed["stale"] == "null"

    def test_a_non_numeric_stale_value_is_not_stale(self, tmp_path: Path, monkeypatch) -> None:
        """Edge: a string count must not crash the step."""
        out = _outputs(tmp_path, monkeypatch)
        results = _report(tmp_path, {"stale": "many"})
        assert parser.main(["--results", str(results)]) == 0
        assert _parsed(out)["has_stale"] == "false"

    def test_a_boolean_stale_value_is_not_stale(self, tmp_path: Path, monkeypatch) -> None:
        """Edge: ``True`` is an int in Python but was never a count."""
        out = _outputs(tmp_path, monkeypatch)
        results = _report(tmp_path, {"stale": True})
        parser.main(["--results", str(results)])
        assert _parsed(out)["has_stale"] == "false"

    def test_a_negative_stale_count_is_not_stale(self, tmp_path: Path, monkeypatch) -> None:
        """Edge: the shell used ``-gt 0``, not "non-zero"."""
        out = _outputs(tmp_path, monkeypatch)
        results = _report(tmp_path, {"stale": -1})
        parser.main(["--results", str(results)])
        assert _parsed(out)["has_stale"] == "false"

    def test_an_absent_summary_object_is_tolerated(self, tmp_path: Path, monkeypatch) -> None:
        """Edge: a report with no summary reads as all null, not a crash."""
        out = _outputs(tmp_path, monkeypatch)
        path = tmp_path / "health-report.json"
        path.write_text(json.dumps({"other": 1}), encoding="utf-8")
        assert parser.main(["--results", str(path)]) == 0
        assert _parsed(out)["total"] == "null"

    @pytest.mark.parametrize("payload", [[], "x", 1, {"summary": []}, {"summary": "x"}])
    def test_a_non_object_shape_reads_as_absent(
        self, tmp_path: Path, monkeypatch, payload
    ) -> None:
        """Edge: jq emitted null for non-object shapes instead of crashing."""
        out = _outputs(tmp_path, monkeypatch)
        path = tmp_path / "health-report.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        assert parser.main(["--results", str(path)]) == 0
        assert _parsed(out)["total"] == "null"
        assert _parsed(out)["has_stale"] == "false"


class TestFailureModes:
    """Only an unreadable report is an error."""

    def test_malformed_json_fails_loudly(self, tmp_path: Path, monkeypatch, capsys) -> None:
        """Negative: a truncated report must not read as zero stale."""
        _outputs(tmp_path, monkeypatch)
        path = tmp_path / "health-report.json"
        path.write_text("{not json", encoding="utf-8")
        assert parser.main(["--results", str(path)]) == 1
        assert "::error::" in capsys.readouterr().out

    def test_the_error_names_the_report(self, tmp_path: Path, monkeypatch, capsys) -> None:
        """Edge: the annotation must identify which file failed."""
        _outputs(tmp_path, monkeypatch)
        path = tmp_path / "health-report.json"
        path.write_text("{not json", encoding="utf-8")
        parser.main(["--results", str(path)])
        assert "health-report.json" in capsys.readouterr().out


class TestOutputHandling:
    """Step outputs append; they never truncate."""

    def test_existing_output_content_is_preserved(self, tmp_path: Path, monkeypatch) -> None:
        """Edge: a prior step's outputs must survive."""
        out = _outputs(tmp_path, monkeypatch)
        out.write_text("earlier=kept\n", encoding="utf-8")
        results = _report(tmp_path, {"stale": 0})
        parser.main(["--results", str(results)])
        assert _parsed(out)["earlier"] == "kept"

    def test_without_the_env_var_values_go_to_stdout(
        self, tmp_path: Path, monkeypatch, capsys
    ) -> None:
        """Edge: running outside Actions must still be inspectable."""
        monkeypatch.delenv("GITHUB_OUTPUT", raising=False)
        results = _report(tmp_path, {"stale": 2})
        assert parser.main(["--results", str(results)]) == 0
        assert "has_stale=true" in capsys.readouterr().out


class TestWorkflowWiring:
    """The workflow must call the script this module tests."""

    def test_memory_health_calls_the_parser(self) -> None:
        """Positive: extraction is only real once the YAML points here."""
        text = (REPO_ROOT / ".github" / "workflows" / "memory-health.yml").read_text(
            encoding="utf-8"
        )
        assert "scripts/ci/parse_memory_health_results.py" in text

    def test_memory_health_no_longer_shells_out_to_jq(self) -> None:
        """Negative: the replaced shell must be gone, not merely bypassed."""
        text = (REPO_ROOT / ".github" / "workflows" / "memory-health.yml").read_text(
            encoding="utf-8"
        )
        assert "jq '.summary.total'" not in text


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
