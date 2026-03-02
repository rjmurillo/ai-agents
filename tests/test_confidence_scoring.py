"""Tests for confidence scoring module (Phase 4).

Covers decay computation, trend classification, history parsing,
dashboard rendering, and CLI integration.
"""

from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest
from memory_enhancement.confidence import (
    ConfidenceRecord,
    apply_decay,
    classify_trend,
    compute_decay,
    load_confidence_history,
    parse_confidence_history,
    record_confidence,
    render_dashboard,
    render_dashboard_json,
)
from memory_enhancement.models import Memory


class TestComputeDecay:
    """Tests for the exponential decay function."""

    def test_no_last_verified_returns_one(self) -> None:
        assert compute_decay(None) == 1.0

    def test_zero_elapsed_returns_one(self) -> None:
        now = datetime(2026, 1, 15, tzinfo=UTC)
        assert compute_decay(now, now) == 1.0

    def test_one_half_life_returns_half(self) -> None:
        now = datetime(2026, 2, 14, tzinfo=UTC)
        last = datetime(2026, 1, 15, tzinfo=UTC)
        result = compute_decay(last, now, half_life_days=30.0)
        assert result == pytest.approx(0.5, abs=0.01)

    def test_two_half_lives_returns_quarter(self) -> None:
        now = datetime(2026, 3, 16, tzinfo=UTC)
        last = datetime(2026, 1, 15, tzinfo=UTC)
        result = compute_decay(last, now, half_life_days=30.0)
        assert result == pytest.approx(0.25, abs=0.01)

    def test_future_last_verified_returns_one(self) -> None:
        now = datetime(2026, 1, 1, tzinfo=UTC)
        last = datetime(2026, 2, 1, tzinfo=UTC)
        result = compute_decay(last, now, half_life_days=30.0)
        assert result == 1.0

    def test_naive_datetime_handled(self) -> None:
        now = datetime(2026, 2, 14)
        last = datetime(2026, 1, 15)
        result = compute_decay(last, now, half_life_days=30.0)
        assert result == pytest.approx(0.5, abs=0.01)

    def test_custom_half_life(self) -> None:
        now = datetime(2026, 1, 22, tzinfo=UTC)
        last = datetime(2026, 1, 15, tzinfo=UTC)
        result = compute_decay(last, now, half_life_days=7.0)
        assert result == pytest.approx(0.5, abs=0.01)


class TestApplyDecay:
    """Tests for applying decay to memory confidence."""

    def test_no_verification_no_decay(self) -> None:
        memory = Memory(
            id="test", subject="test", path=Path("x.md"),
            content="", confidence=0.8,
        )
        assert apply_decay(memory) == pytest.approx(0.8, abs=0.01)

    def test_recent_verification_minimal_decay(self) -> None:
        now = datetime(2026, 1, 16, tzinfo=UTC)
        memory = Memory(
            id="test", subject="test", path=Path("x.md"),
            content="", confidence=1.0,
            last_verified=datetime(2026, 1, 15, tzinfo=UTC),
        )
        result = apply_decay(memory, now=now, half_life_days=30.0)
        assert result > 0.95

    def test_old_verification_significant_decay(self) -> None:
        now = datetime(2026, 3, 16, tzinfo=UTC)
        memory = Memory(
            id="test", subject="test", path=Path("x.md"),
            content="", confidence=1.0,
            last_verified=datetime(2026, 1, 15, tzinfo=UTC),
        )
        result = apply_decay(memory, now=now, half_life_days=30.0)
        assert result < 0.3

    def test_clamps_to_zero(self) -> None:
        memory = Memory(
            id="test", subject="test", path=Path("x.md"),
            content="", confidence=0.0,
        )
        assert apply_decay(memory) == 0.0

    def test_clamps_to_one(self) -> None:
        memory = Memory(
            id="test", subject="test", path=Path("x.md"),
            content="", confidence=1.0,
        )
        result = apply_decay(memory)
        assert result <= 1.0


class TestRecordConfidence:
    """Tests for creating confidence records."""

    def test_creates_record_with_score(self) -> None:
        memory = Memory(
            id="test", subject="test", path=Path("x.md"), content="",
        )
        record = record_confidence(memory, valid_count=3, total_count=4)
        assert record.score == pytest.approx(0.75)
        assert record.valid_count == 3
        assert record.total_count == 4

    def test_zero_total_returns_default(self) -> None:
        memory = Memory(
            id="test", subject="test", path=Path("x.md"), content="",
        )
        record = record_confidence(memory, valid_count=0, total_count=0)
        assert record.score == 0.5

    def test_custom_timestamp(self) -> None:
        ts = datetime(2026, 1, 15, tzinfo=UTC)
        memory = Memory(
            id="test", subject="test", path=Path("x.md"), content="",
        )
        record = record_confidence(memory, valid_count=1, total_count=1, timestamp=ts)
        assert record.timestamp == ts


class TestClassifyTrend:
    """Tests for trend classification."""

    def test_empty_history_is_stable(self) -> None:
        assert classify_trend([]) == "stable"

    def test_single_record_is_stable(self) -> None:
        records = [ConfidenceRecord(datetime.now(UTC), 0.8, 4, 5)]
        assert classify_trend(records) == "stable"

    def test_improving_trend(self) -> None:
        ts = datetime(2026, 1, 1, tzinfo=UTC)
        records = [
            ConfidenceRecord(ts, 0.3, 1, 3),
            ConfidenceRecord(ts + timedelta(days=7), 0.4, 2, 5),
            ConfidenceRecord(ts + timedelta(days=14), 0.8, 4, 5),
            ConfidenceRecord(ts + timedelta(days=21), 0.9, 9, 10),
        ]
        assert classify_trend(records) == "improving"

    def test_declining_trend(self) -> None:
        ts = datetime(2026, 1, 1, tzinfo=UTC)
        records = [
            ConfidenceRecord(ts, 0.9, 9, 10),
            ConfidenceRecord(ts + timedelta(days=7), 0.85, 8, 10),
            ConfidenceRecord(ts + timedelta(days=14), 0.4, 4, 10),
            ConfidenceRecord(ts + timedelta(days=21), 0.3, 3, 10),
        ]
        assert classify_trend(records) == "declining"

    def test_stable_trend(self) -> None:
        ts = datetime(2026, 1, 1, tzinfo=UTC)
        records = [
            ConfidenceRecord(ts, 0.8, 4, 5),
            ConfidenceRecord(ts + timedelta(days=7), 0.82, 4, 5),
            ConfidenceRecord(ts + timedelta(days=14), 0.79, 4, 5),
            ConfidenceRecord(ts + timedelta(days=21), 0.81, 4, 5),
        ]
        assert classify_trend(records) == "stable"


class TestParseConfidenceHistory:
    """Tests for parsing YAML frontmatter history."""

    def test_parses_valid_entries(self) -> None:
        raw = [
            {
                "timestamp": "2026-01-15T10:00:00+00:00",
                "score": 0.8,
                "valid_count": 4,
                "total_count": 5,
            },
            {
                "timestamp": "2026-01-22T10:00:00+00:00",
                "score": 0.6,
                "valid_count": 3,
                "total_count": 5,
            },
        ]
        records = parse_confidence_history(raw)
        assert len(records) == 2
        assert records[0].score == 0.8
        assert records[1].valid_count == 3

    def test_skips_entries_without_timestamp(self) -> None:
        raw = [
            {"score": 0.8, "valid_count": 4, "total_count": 5},
        ]
        records = parse_confidence_history(raw)
        assert len(records) == 0

    def test_handles_datetime_objects(self) -> None:
        ts = datetime(2026, 1, 15, 10, 0, 0, tzinfo=UTC)
        raw = [
            {"timestamp": ts, "score": 0.9, "valid_count": 9, "total_count": 10},
        ]
        records = parse_confidence_history(raw)
        assert len(records) == 1
        assert records[0].timestamp == ts

    def test_empty_list(self) -> None:
        assert parse_confidence_history([]) == []


class TestLoadConfidenceHistory:
    """Tests for loading history from memory files."""

    def test_loads_from_file_with_history(self, tmp_path: Path) -> None:
        memory_file = tmp_path / "test-mem.md"
        memory_file.write_text(
            "---\n"
            "id: test-mem\n"
            "subject: Test\n"
            "confidence: 0.8\n"
            "confidence_history:\n"
            "  - timestamp: '2026-01-15T10:00:00+00:00'\n"
            "    score: 1.0\n"
            "    valid_count: 5\n"
            "    total_count: 5\n"
            "  - timestamp: '2026-01-22T10:00:00+00:00'\n"
            "    score: 0.8\n"
            "    valid_count: 4\n"
            "    total_count: 5\n"
            "---\n"
            "Test content\n"
        )
        records = load_confidence_history(memory_file)
        assert len(records) == 2
        assert records[0].score == 1.0
        assert records[1].score == 0.8

    def test_returns_empty_for_no_history(self, tmp_path: Path) -> None:
        memory_file = tmp_path / "no-history.md"
        memory_file.write_text(
            "---\n"
            "id: no-history\n"
            "subject: Test\n"
            "---\n"
            "Content\n"
        )
        records = load_confidence_history(memory_file)
        assert records == []


class TestRenderDashboard:
    """Tests for dashboard markdown rendering."""

    def test_empty_directory(self, tmp_path: Path) -> None:
        result = render_dashboard(tmp_path)
        assert result == "No memories found."

    def test_nonexistent_directory(self, tmp_path: Path) -> None:
        result = render_dashboard(tmp_path / "nonexistent")
        assert result == "No memories directory found."

    def test_renders_markdown_table(self, tmp_path: Path) -> None:
        now = datetime(2026, 2, 1, tzinfo=UTC)
        mem_file = tmp_path / "test-mem.md"
        mem_file.write_text(
            "---\n"
            "id: test-mem\n"
            "subject: Test Memory\n"
            "confidence: 0.9\n"
            "last_verified: '2026-01-31T10:00:00+00:00'\n"
            "---\n"
            "Content\n"
        )
        result = render_dashboard(tmp_path, now=now)
        assert "## Confidence Dashboard" in result
        assert "test-mem" in result
        assert "90%" in result

    def test_flags_low_confidence(self, tmp_path: Path) -> None:
        now = datetime(2026, 6, 1, tzinfo=UTC)
        mem_file = tmp_path / "old-mem.md"
        mem_file.write_text(
            "---\n"
            "id: old-mem\n"
            "subject: Old Memory\n"
            "confidence: 0.5\n"
            "last_verified: '2026-01-01T10:00:00+00:00'\n"
            "---\n"
            "Content\n"
        )
        result = render_dashboard(tmp_path, now=now)
        assert "below 50%" in result


class TestRenderDashboardJson:
    """Tests for dashboard JSON output."""

    def test_empty_directory(self, tmp_path: Path) -> None:
        result = render_dashboard_json(tmp_path)
        assert result == []

    def test_returns_list_of_dicts(self, tmp_path: Path) -> None:
        now = datetime(2026, 2, 1, tzinfo=UTC)
        mem_file = tmp_path / "test-mem.md"
        mem_file.write_text(
            "---\n"
            "id: test-mem\n"
            "subject: Test\n"
            "confidence: 0.85\n"
            "last_verified: '2026-01-31T10:00:00+00:00'\n"
            "---\n"
            "Content\n"
        )
        result = render_dashboard_json(tmp_path, now=now)
        assert len(result) == 1
        entry = result[0]
        assert entry["memory_id"] == "test-mem"
        assert entry["raw_confidence"] == 0.85
        assert entry["trend"] == "stable"
        assert entry["decayed_confidence"] <= 0.85


class TestCLIConfidence:
    """Tests for the confidence CLI subcommand."""

    def test_dashboard_json_output(self, tmp_path: Path) -> None:
        mem_file = tmp_path / "cli-mem.md"
        mem_file.write_text(
            "---\n"
            "id: cli-mem\n"
            "subject: CLI Test\n"
            "confidence: 0.7\n"
            "---\n"
            "Content\n"
        )
        from memory_enhancement.__main__ import main

        with patch(
            "sys.argv",
            [
                "memory_enhancement", "confidence",
                "--dir", str(tmp_path),
                "--repo-root", str(tmp_path),
                "--json",
            ],
        ):
            with patch("sys.stdout"):
                try:
                    exit_code = main()
                except SystemExit as e:
                    exit_code = e.code
                assert exit_code == 0

    def test_single_memory_json(self, tmp_path: Path) -> None:
        mem_file = tmp_path / "single-mem.md"
        mem_file.write_text(
            "---\n"
            "id: single-mem\n"
            "subject: Single Test\n"
            "confidence: 0.9\n"
            "---\n"
            "Content\n"
        )
        from memory_enhancement.__main__ import main

        with patch(
            "sys.argv",
            [
                "memory_enhancement", "confidence", "single-mem",
                "--dir", str(tmp_path),
                "--repo-root", str(tmp_path),
                "--json",
            ],
        ):
            try:
                exit_code = main()
            except SystemExit as e:
                exit_code = e.code
            assert exit_code == 0
