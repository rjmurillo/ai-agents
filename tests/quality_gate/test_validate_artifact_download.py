"""Tests for scripts/quality_gate/validate_artifact_download.py.

Pins the missing-file detection of the extracted ``Validate artifact
download`` workflow step.
"""

from __future__ import annotations

from pathlib import Path

from scripts.quality_gate.validate_artifact_download import find_missing, main

_AGENTS = (
    "security",
    "qa",
    "analyst",
    "architect",
    "devops",
    "roadmap",
    "reliability",
    "observability",
    "agent-safety",
    "decision-rigor",
)


def _write_all_verdicts(results_dir: Path) -> None:
    results_dir.mkdir(parents=True, exist_ok=True)
    for agent in _AGENTS:
        (results_dir / f"{agent}-verdict.txt").write_text("PASS", encoding="utf-8")


# ---------------------------------------------------------------------------
# find_missing
# ---------------------------------------------------------------------------


class TestFindMissing:
    def test_no_missing_when_all_present(self, tmp_path: Path) -> None:
        _write_all_verdicts(tmp_path)
        assert find_missing(tmp_path) == []

    def test_all_missing_when_dir_empty(self, tmp_path: Path) -> None:
        missing = find_missing(tmp_path)
        assert len(missing) == 10
        assert "security-verdict.txt" in missing

    def test_detects_single_missing(self, tmp_path: Path) -> None:
        _write_all_verdicts(tmp_path)
        (tmp_path / "qa-verdict.txt").unlink()
        assert find_missing(tmp_path) == ["qa-verdict.txt"]

    def test_nonexistent_dir_reports_all_missing(self, tmp_path: Path) -> None:
        missing = find_missing(tmp_path / "does-not-exist")
        assert len(missing) == 10


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------


class TestMain:
    def test_all_present_returns_zero(self, tmp_path: Path) -> None:
        _write_all_verdicts(tmp_path)
        rc = main(["--results-dir", str(tmp_path)])
        assert rc == 0

    def test_missing_returns_one_and_annotates(self, tmp_path: Path, capsys) -> None:
        _write_all_verdicts(tmp_path)
        (tmp_path / "analyst-verdict.txt").unlink()
        rc = main(["--results-dir", str(tmp_path)])
        assert rc == 1
        captured = capsys.readouterr()
        assert "::error::Artifact download incomplete" in captured.out
        assert "analyst-verdict.txt" in captured.out

    def test_empty_dir_returns_one(self, tmp_path: Path) -> None:
        rc = main(["--results-dir", str(tmp_path)])
        assert rc == 1
