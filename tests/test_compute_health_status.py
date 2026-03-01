"""Tests for the health status computation module."""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import pytest

from scripts.compute_health_status import (
    ComponentHealth,
    HealthLevel,
    HealthStatusReport,
    Threshold,
    classify_level,
    compute_health,
    compute_memory_health,
    compute_session_health,
)

# ---------------------------------------------------------------------------
# HealthLevel enum tests
# ---------------------------------------------------------------------------


class TestHealthLevel:
    """Tests for HealthLevel enum values."""

    def test_all_levels_exist(self) -> None:
        assert HealthLevel.HEALTHY.value == "healthy"
        assert HealthLevel.WARNING.value == "warning"
        assert HealthLevel.ERROR.value == "error"


# ---------------------------------------------------------------------------
# Threshold tests
# ---------------------------------------------------------------------------


class TestThreshold:
    """Tests for Threshold dataclass."""

    def test_frozen(self) -> None:
        t = Threshold(warning=0.1, error=0.25)
        with pytest.raises(AttributeError):
            t.warning = 0.5  # type: ignore[misc]

    def test_defaults(self) -> None:
        t = Threshold(warning=0.1, error=0.25)
        assert t.higher_is_worse is True


# ---------------------------------------------------------------------------
# classify_level tests
# ---------------------------------------------------------------------------


class TestClassifyLevel:
    """Tests for threshold classification logic."""

    def test_healthy_when_below_warning(self) -> None:
        t = Threshold(warning=0.10, error=0.25)
        assert classify_level(0.05, t) == HealthLevel.HEALTHY

    def test_warning_at_threshold(self) -> None:
        t = Threshold(warning=0.10, error=0.25)
        assert classify_level(0.10, t) == HealthLevel.WARNING

    def test_warning_between_thresholds(self) -> None:
        t = Threshold(warning=0.10, error=0.25)
        assert classify_level(0.15, t) == HealthLevel.WARNING

    def test_error_at_threshold(self) -> None:
        t = Threshold(warning=0.10, error=0.25)
        assert classify_level(0.25, t) == HealthLevel.ERROR

    def test_error_above_threshold(self) -> None:
        t = Threshold(warning=0.10, error=0.25)
        assert classify_level(0.50, t) == HealthLevel.ERROR

    def test_zero_is_healthy(self) -> None:
        t = Threshold(warning=0.10, error=0.25)
        assert classify_level(0.0, t) == HealthLevel.HEALTHY

    def test_lower_is_worse_healthy(self) -> None:
        t = Threshold(warning=0.30, error=0.10, higher_is_worse=False)
        assert classify_level(0.50, t) == HealthLevel.HEALTHY

    def test_lower_is_worse_warning(self) -> None:
        t = Threshold(warning=0.30, error=0.10, higher_is_worse=False)
        assert classify_level(0.30, t) == HealthLevel.WARNING

    def test_lower_is_worse_error(self) -> None:
        t = Threshold(warning=0.30, error=0.10, higher_is_worse=False)
        assert classify_level(0.05, t) == HealthLevel.ERROR


# ---------------------------------------------------------------------------
# ComponentHealth tests
# ---------------------------------------------------------------------------


class TestComponentHealth:
    """Tests for ComponentHealth dataclass."""

    def test_to_dict(self) -> None:
        comp = ComponentHealth(
            name="test_metric",
            level=HealthLevel.WARNING,
            value=0.12345,
            threshold_warning=0.10,
            threshold_error=0.25,
            detail="test detail",
        )
        d = comp.to_dict()
        assert d["name"] == "test_metric"
        assert d["level"] == "warning"
        assert d["value"] == 0.1235  # rounded to 4 decimal places
        assert d["detail"] == "test detail"

    def test_default_detail(self) -> None:
        comp = ComponentHealth(
            name="x", level=HealthLevel.HEALTHY, value=0.0,
            threshold_warning=0.1, threshold_error=0.25,
        )
        assert comp.detail == ""


# ---------------------------------------------------------------------------
# HealthStatusReport tests
# ---------------------------------------------------------------------------


class TestHealthStatusReport:
    """Tests for HealthStatusReport aggregate properties."""

    def test_empty_report(self) -> None:
        report = HealthStatusReport()
        assert report.overall_level == HealthLevel.HEALTHY
        assert report.error_count == 0
        assert report.warning_count == 0
        assert report.healthy_count == 0

    def test_all_healthy(self) -> None:
        report = HealthStatusReport(components=[
            ComponentHealth(
                name="a", level=HealthLevel.HEALTHY, value=0.01,
                threshold_warning=0.1, threshold_error=0.25,
            ),
            ComponentHealth(
                name="b", level=HealthLevel.HEALTHY, value=0.02,
                threshold_warning=0.1, threshold_error=0.25,
            ),
        ])
        assert report.overall_level == HealthLevel.HEALTHY
        assert report.healthy_count == 2

    def test_warning_escalates_overall(self) -> None:
        report = HealthStatusReport(components=[
            ComponentHealth(
                name="a", level=HealthLevel.HEALTHY, value=0.01,
                threshold_warning=0.1, threshold_error=0.25,
            ),
            ComponentHealth(
                name="b", level=HealthLevel.WARNING, value=0.15,
                threshold_warning=0.1, threshold_error=0.25,
            ),
        ])
        assert report.overall_level == HealthLevel.WARNING

    def test_error_escalates_over_warning(self) -> None:
        report = HealthStatusReport(components=[
            ComponentHealth(
                name="a", level=HealthLevel.WARNING, value=0.15,
                threshold_warning=0.1, threshold_error=0.25,
            ),
            ComponentHealth(
                name="b", level=HealthLevel.ERROR, value=0.30,
                threshold_warning=0.1, threshold_error=0.25,
            ),
        ])
        assert report.overall_level == HealthLevel.ERROR
        assert report.error_count == 1
        assert report.warning_count == 1

    def test_to_dict_structure(self) -> None:
        report = HealthStatusReport(components=[
            ComponentHealth(
                name="test", level=HealthLevel.HEALTHY, value=0.05,
                threshold_warning=0.1, threshold_error=0.25,
            ),
        ])
        d = report.to_dict()
        assert "checked_at" in d
        assert d["overall"] == "healthy"
        assert d["summary"]["total"] == 1
        assert d["summary"]["healthy"] == 1
        assert len(d["components"]) == 1

    def test_to_dict_json_serializable(self) -> None:
        report = HealthStatusReport(components=[
            ComponentHealth(
                name="test", level=HealthLevel.ERROR, value=0.30,
                threshold_warning=0.1, threshold_error=0.25, detail="bad",
            ),
        ])
        serialized = json.dumps(report.to_dict())
        parsed = json.loads(serialized)
        assert parsed["overall"] == "error"

    def test_to_markdown_empty(self) -> None:
        report = HealthStatusReport()
        md = report.to_markdown()
        assert "No components checked" in md

    def test_to_markdown_healthy(self) -> None:
        report = HealthStatusReport(components=[
            ComponentHealth(
                name="test_metric", level=HealthLevel.HEALTHY, value=0.02,
                threshold_warning=0.1, threshold_error=0.25, detail="ok",
            ),
        ])
        md = report.to_markdown()
        assert "[PASS]" in md
        assert "test_metric" in md
        assert "Recommendations" not in md

    def test_to_markdown_with_warnings(self) -> None:
        report = HealthStatusReport(components=[
            ComponentHealth(
                name="memory_stale_rate", level=HealthLevel.WARNING, value=0.15,
                threshold_warning=0.1, threshold_error=0.25,
                detail="3/20 memories stale",
            ),
        ])
        md = report.to_markdown()
        assert "[WARN]" in md
        assert "Recommendations" in md
        assert "stale" in md.lower()

    def test_to_markdown_with_error(self) -> None:
        report = HealthStatusReport(components=[
            ComponentHealth(
                name="session_failure_rate", level=HealthLevel.ERROR, value=0.30,
                threshold_warning=0.1, threshold_error=0.25,
                detail="15/50 sessions failed",
            ),
        ])
        md = report.to_markdown()
        assert "[FAIL]" in md
        assert "Recommendations" in md


# ---------------------------------------------------------------------------
# compute_memory_health tests
# ---------------------------------------------------------------------------


class TestComputeMemoryHealth:
    """Tests for memory health computation."""

    def test_nonexistent_dir(self, tmp_path: Path) -> None:
        result = compute_memory_health(tmp_path / "nonexistent")
        assert result == []

    def test_empty_dir(self, tmp_path: Path) -> None:
        empty = tmp_path / "memories"
        empty.mkdir()
        result = compute_memory_health(empty)
        assert result == []

    def test_all_healthy_memories(self, tmp_path: Path) -> None:
        mem_dir = tmp_path / "memories"
        mem_dir.mkdir()
        (mem_dir / "good.md").write_text(
            "---\nid: good\nsubject: Good\n---\nContent.\n",
            encoding="utf-8",
        )
        (mem_dir / "also-good.md").write_text(
            "---\nid: also-good\nsubject: Also Good\n---\nMore content.\n",
            encoding="utf-8",
        )
        result = compute_memory_health(mem_dir)
        assert len(result) == 2
        # Both stale_rate and error_rate should be 0
        for comp in result:
            assert comp.level == HealthLevel.HEALTHY
            assert comp.value == 0.0

    def test_stale_memories_detected(self, tmp_path: Path) -> None:
        mem_dir = tmp_path / "memories"
        mem_dir.mkdir()
        (mem_dir / "good.md").write_text(
            "---\nid: good\nsubject: Good\n---\nOK.\n",
            encoding="utf-8",
        )
        (mem_dir / "stale.md").write_text(
            "---\nid: stale\nsubject: Stale\nstale: true\n---\nOld.\n",
            encoding="utf-8",
        )
        result = compute_memory_health(mem_dir)
        stale_comp = next(c for c in result if c.name == "memory_stale_rate")
        assert stale_comp.value == 0.5  # 1/2 = 50%
        assert stale_comp.level == HealthLevel.ERROR

    def test_parse_errors_detected(self, tmp_path: Path) -> None:
        mem_dir = tmp_path / "memories"
        mem_dir.mkdir()
        (mem_dir / "good.md").write_text(
            "---\nid: good\nsubject: Good\n---\nOK.\n",
            encoding="utf-8",
        )
        (mem_dir / "bad.md").write_text(
            "no frontmatter here\n",
            encoding="utf-8",
        )
        result = compute_memory_health(mem_dir)
        error_comp = next(c for c in result if c.name == "memory_error_rate")
        assert error_comp.value == 0.5  # 1/2 = 50%
        assert error_comp.level == HealthLevel.ERROR

    def test_deprecated_detected_as_stale(self, tmp_path: Path) -> None:
        mem_dir = tmp_path / "memories"
        mem_dir.mkdir()
        (mem_dir / "dep.md").write_text(
            "---\nid: dep\nsubject: Dep\ndeprecated: true\n---\nOld.\n",
            encoding="utf-8",
        )
        result = compute_memory_health(mem_dir)
        stale_comp = next(c for c in result if c.name == "memory_stale_rate")
        assert stale_comp.value == 1.0


# ---------------------------------------------------------------------------
# compute_session_health tests
# ---------------------------------------------------------------------------


class TestComputeSessionHealth:
    """Tests for session health computation."""

    def test_nonexistent_dir(self, tmp_path: Path) -> None:
        result = compute_session_health(tmp_path / "nonexistent")
        assert result == []

    def test_empty_dir(self, tmp_path: Path) -> None:
        empty = tmp_path / "sessions"
        empty.mkdir()
        result = compute_session_health(empty)
        assert result == []

    def test_all_successful_sessions(self, tmp_path: Path) -> None:
        sess_dir = tmp_path / "sessions"
        sess_dir.mkdir()
        for i in range(3):
            (sess_dir / f"session-{i}.json").write_text(
                json.dumps({"status": "completed"}),
                encoding="utf-8",
            )
        result = compute_session_health(sess_dir)
        failure_comp = next(
            (c for c in result if c.name == "session_failure_rate"), None
        )
        assert failure_comp is not None
        assert failure_comp.value == 0.0
        assert failure_comp.level == HealthLevel.HEALTHY

    def test_failed_sessions_detected(self, tmp_path: Path) -> None:
        sess_dir = tmp_path / "sessions"
        sess_dir.mkdir()
        (sess_dir / "ok.json").write_text(
            json.dumps({"status": "completed"}), encoding="utf-8",
        )
        (sess_dir / "bad.json").write_text(
            json.dumps({"status": "failed"}), encoding="utf-8",
        )
        result = compute_session_health(sess_dir)
        failure_comp = next(c for c in result if c.name == "session_failure_rate")
        assert failure_comp.value == 0.5
        assert failure_comp.level == HealthLevel.ERROR

    def test_context_retrieval_tracking(self, tmp_path: Path) -> None:
        sess_dir = tmp_path / "sessions"
        sess_dir.mkdir()
        (sess_dir / "invoked.json").write_text(
            json.dumps({
                "status": "completed",
                "classification": {
                    "complexity": "medium",
                    "context_retrieval": "INVOKED",
                },
            }),
            encoding="utf-8",
        )
        (sess_dir / "skipped.json").write_text(
            json.dumps({
                "status": "completed",
                "classification": {
                    "complexity": "simple",
                    "context_retrieval": "SKIPPED",
                },
            }),
            encoding="utf-8",
        )
        result = compute_session_health(sess_dir)
        skip_comp = next(
            c for c in result if c.name == "context_retrieval_skip_rate"
        )
        assert skip_comp.value == 0.5  # 1 skipped / 2 eligible

    def test_invalid_json_skipped(self, tmp_path: Path) -> None:
        sess_dir = tmp_path / "sessions"
        sess_dir.mkdir()
        (sess_dir / "bad.json").write_text("not json", encoding="utf-8")
        (sess_dir / "good.json").write_text(
            json.dumps({"status": "completed"}), encoding="utf-8",
        )
        result = compute_session_health(sess_dir)
        # Should only count the valid session
        failure_comp = next(
            (c for c in result if c.name == "session_failure_rate"), None
        )
        assert failure_comp is not None
        assert failure_comp.detail == "0/1 sessions failed"

    def test_limit_respected(self, tmp_path: Path) -> None:
        sess_dir = tmp_path / "sessions"
        sess_dir.mkdir()
        for i in range(10):
            (sess_dir / f"session-{i:02d}.json").write_text(
                json.dumps({"status": "completed"}), encoding="utf-8",
            )
        result = compute_session_health(sess_dir, limit=3)
        failure_comp = next(c for c in result if c.name == "session_failure_rate")
        assert failure_comp.detail == "0/3 sessions failed"


# ---------------------------------------------------------------------------
# compute_health integration tests
# ---------------------------------------------------------------------------


class TestComputeHealth:
    """Tests for the aggregate compute_health function."""

    def test_with_both_sources(self, tmp_path: Path) -> None:
        mem_dir = tmp_path / "memories"
        mem_dir.mkdir()
        (mem_dir / "ok.md").write_text(
            "---\nid: ok\nsubject: OK\n---\nContent.\n",
            encoding="utf-8",
        )

        sess_dir = tmp_path / "sessions"
        sess_dir.mkdir()
        (sess_dir / "s1.json").write_text(
            json.dumps({"status": "completed"}), encoding="utf-8",
        )

        report = compute_health(
            tmp_path, memories_dir=mem_dir, sessions_dir=sess_dir,
        )
        assert report.overall_level == HealthLevel.HEALTHY
        assert len(report.components) >= 3  # 2 memory + 1 session

    def test_missing_sources_handled(self, tmp_path: Path) -> None:
        report = compute_health(tmp_path)
        assert report.overall_level == HealthLevel.HEALTHY
        assert len(report.components) == 0

    def test_checked_at_populated(self, tmp_path: Path) -> None:
        report = compute_health(tmp_path)
        assert report.checked_at is not None
        assert isinstance(report.checked_at, datetime)


# ---------------------------------------------------------------------------
# CLI integration tests
# ---------------------------------------------------------------------------


class TestCLI:
    """Tests for the CLI entry point."""

    @staticmethod
    def _script_path() -> str:
        return str(Path(__file__).resolve().parents[1] / "scripts" / "compute_health_status.py")

    def test_json_output(self, tmp_path: Path) -> None:
        mem_dir = tmp_path / "memories"
        mem_dir.mkdir()
        (mem_dir / "ok.md").write_text(
            "---\nid: ok\nsubject: OK\n---\nOK.\n",
            encoding="utf-8",
        )
        result = subprocess.run(
            [
                sys.executable, self._script_path(),
                "--format", "json",
                "--project-root", str(tmp_path),
                "--memories-dir", str(mem_dir),
                "--sessions-dir", str(tmp_path / "sessions"),
            ],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert "overall" in data
        assert "components" in data

    def test_markdown_output(self, tmp_path: Path) -> None:
        result = subprocess.run(
            [
                sys.executable, self._script_path(),
                "--format", "markdown",
                "--project-root", str(tmp_path),
                "--memories-dir", str(tmp_path / "nonexistent"),
                "--sessions-dir", str(tmp_path / "nonexistent"),
            ],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert "Health Status Report" in result.stdout

    def test_table_output(self, tmp_path: Path) -> None:
        result = subprocess.run(
            [
                sys.executable, self._script_path(),
                "--format", "table",
                "--project-root", str(tmp_path),
                "--memories-dir", str(tmp_path / "nonexistent"),
                "--sessions-dir", str(tmp_path / "nonexistent"),
            ],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert "Health Status" in result.stdout

    def test_exit_code_1_on_error_state(self, tmp_path: Path) -> None:
        mem_dir = tmp_path / "memories"
        mem_dir.mkdir()
        # Create many parse-error files to trigger error threshold
        for i in range(10):
            (mem_dir / f"bad-{i}.md").write_text("no frontmatter", encoding="utf-8")
        result = subprocess.run(
            [
                sys.executable, self._script_path(),
                "--format", "json",
                "--project-root", str(tmp_path),
                "--memories-dir", str(mem_dir),
                "--sessions-dir", str(tmp_path / "sessions"),
            ],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 1

    def test_path_traversal_rejected(self, tmp_path: Path) -> None:
        project = tmp_path / "project"
        project.mkdir()
        outside = tmp_path / "outside"
        outside.mkdir()
        result = subprocess.run(
            [
                sys.executable, self._script_path(),
                "--project-root", str(project),
                "--memories-dir", str(outside),
            ],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 2
