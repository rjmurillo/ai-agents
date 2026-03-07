#!/usr/bin/env python3
"""Tests for observability query_logs.py script."""

from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path

_SCRIPT = os.path.join(os.path.dirname(__file__), "..", "query_logs.py")


def _load_module():
    spec = importlib.util.spec_from_file_location("query_logs", _SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _write_log_file(tmp_path: Path, lines: list[str]) -> Path:
    log_file = tmp_path / "test.jsonl"
    log_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return log_file


class TestParseTimestamp:
    def test_iso_with_z(self):
        mod = _load_module()
        dt = mod.parse_timestamp("2026-03-07T01:15:00Z")
        assert dt.year == 2026
        assert dt.month == 3

    def test_iso_with_offset(self):
        mod = _load_module()
        dt = mod.parse_timestamp("2026-03-07T01:15:00+00:00")
        assert dt.year == 2026


class TestMatchesFilters:
    def test_no_filters_matches_all(self):
        mod = _load_module()
        assert mod.matches_filters({"level": "INFO", "message": "hello"})

    def test_level_filter(self):
        mod = _load_module()
        assert mod.matches_filters({"level": "ERROR"}, level="ERROR")
        assert not mod.matches_filters({"level": "INFO"}, level="ERROR")

    def test_level_filter_case_insensitive(self):
        mod = _load_module()
        assert mod.matches_filters({"level": "error"}, level="ERROR")

    def test_service_filter(self):
        mod = _load_module()
        assert mod.matches_filters({"service": "api"}, service="api")
        assert not mod.matches_filters({"service": "web"}, service="api")

    def test_pattern_filter(self):
        mod = _load_module()
        assert mod.matches_filters({"message": "Connection timeout"}, pattern="timeout")
        assert not mod.matches_filters({"message": "Success"}, pattern="timeout")

    def test_pattern_filter_msg_field(self):
        mod = _load_module()
        assert mod.matches_filters({"msg": "Connection timeout"}, pattern="timeout")

    def test_since_filter(self):
        mod = _load_module()
        since = mod.parse_timestamp("2026-03-07T01:00:00Z")
        entry = {"timestamp": "2026-03-07T02:00:00Z"}
        assert mod.matches_filters(entry, since=since)
        old_entry = {"timestamp": "2026-03-06T23:00:00Z"}
        assert not mod.matches_filters(old_entry, since=since)

    def test_until_filter(self):
        mod = _load_module()
        until = mod.parse_timestamp("2026-03-07T03:00:00Z")
        entry = {"timestamp": "2026-03-07T02:00:00Z"}
        assert mod.matches_filters(entry, until=until)
        future_entry = {"timestamp": "2026-03-07T04:00:00Z"}
        assert not mod.matches_filters(future_entry, until=until)

    def test_missing_timestamp_with_time_filter(self):
        mod = _load_module()
        since = mod.parse_timestamp("2026-03-07T01:00:00Z")
        assert not mod.matches_filters({"message": "no ts"}, since=since)

    def test_ts_field_variant(self):
        mod = _load_module()
        since = mod.parse_timestamp("2026-03-07T01:00:00Z")
        entry = {"ts": "2026-03-07T02:00:00Z"}
        assert mod.matches_filters(entry, since=since)

    def test_combined_filters(self):
        mod = _load_module()
        entry = {
            "timestamp": "2026-03-07T02:00:00Z",
            "level": "ERROR",
            "service": "api",
            "message": "Connection timeout",
        }
        since = mod.parse_timestamp("2026-03-07T01:00:00Z")
        assert mod.matches_filters(
            entry, level="ERROR", service="api", pattern="timeout", since=since,
        )
        assert not mod.matches_filters(
            entry, level="INFO", service="api", pattern="timeout", since=since,
        )


class TestQueryLogFile:
    def test_basic_query(self, tmp_path):
        mod = _load_module()
        log_file = _write_log_file(tmp_path, [
            json.dumps({"level": "INFO", "message": "start"}),
            json.dumps({"level": "ERROR", "message": "fail"}),
            json.dumps({"level": "INFO", "message": "end"}),
        ])
        results = mod.query_log_file(log_file)
        assert len(results) == 3

    def test_level_filter(self, tmp_path):
        mod = _load_module()
        log_file = _write_log_file(tmp_path, [
            json.dumps({"level": "INFO", "message": "start"}),
            json.dumps({"level": "ERROR", "message": "fail"}),
        ])
        results = mod.query_log_file(log_file, level="ERROR")
        assert len(results) == 1
        assert results[0]["message"] == "fail"

    def test_limit(self, tmp_path):
        mod = _load_module()
        lines = [json.dumps({"level": "INFO", "message": f"msg{i}"}) for i in range(10)]
        log_file = _write_log_file(tmp_path, lines)
        results = mod.query_log_file(log_file, limit=3)
        assert len(results) == 3

    def test_skips_blank_lines(self, tmp_path):
        mod = _load_module()
        log_file = _write_log_file(tmp_path, [
            json.dumps({"level": "INFO", "message": "ok"}),
            "",
            json.dumps({"level": "ERROR", "message": "bad"}),
        ])
        results = mod.query_log_file(log_file)
        assert len(results) == 2

    def test_skips_invalid_json(self, tmp_path):
        mod = _load_module()
        log_file = _write_log_file(tmp_path, [
            json.dumps({"level": "INFO", "message": "ok"}),
            "not valid json {",
            json.dumps({"level": "ERROR", "message": "bad"}),
        ])
        results = mod.query_log_file(log_file)
        assert len(results) == 2

    def test_source_line_tracking(self, tmp_path):
        mod = _load_module()
        log_file = _write_log_file(tmp_path, [
            json.dumps({"level": "INFO", "message": "first"}),
            json.dumps({"level": "ERROR", "message": "second"}),
        ])
        results = mod.query_log_file(log_file)
        assert results[0]["_source_line"] == 1
        assert results[1]["_source_line"] == 2


class TestQueryMetricsFile:
    def test_valid_metrics(self, tmp_path):
        mod = _load_module()
        metrics_file = tmp_path / "metrics.json"
        data = {"startup_time_ms": 450, "error_rate": 0.02}
        metrics_file.write_text(json.dumps(data), encoding="utf-8")
        result = mod.query_metrics_file(metrics_file)
        assert result["startup_time_ms"] == 450


class TestSummarize:
    def test_level_counts(self):
        mod = _load_module()
        entries = [
            {"level": "INFO"},
            {"level": "ERROR"},
            {"level": "INFO"},
            {"level": "WARN"},
        ]
        summary = mod.summarize(entries)
        assert summary["total"] == 4
        assert summary["by_level"]["INFO"] == 2
        assert summary["by_level"]["ERROR"] == 1
        assert summary["by_level"]["WARN"] == 1


class TestMainCLI:
    def test_file_not_found(self):
        mod = _load_module()
        rc = mod.main(["/nonexistent/file.jsonl"])
        assert rc == 1

    def test_query_logs(self, tmp_path, capsys):
        mod = _load_module()
        log_file = _write_log_file(tmp_path, [
            json.dumps({"level": "ERROR", "message": "fail"}),
        ])
        rc = mod.main([str(log_file), "--level", "ERROR"])
        assert rc == 0
        output = json.loads(capsys.readouterr().out)
        assert len(output) == 1

    def test_summary_mode(self, tmp_path, capsys):
        mod = _load_module()
        log_file = _write_log_file(tmp_path, [
            json.dumps({"level": "INFO", "message": "a"}),
            json.dumps({"level": "ERROR", "message": "b"}),
        ])
        rc = mod.main([str(log_file), "--summary"])
        assert rc == 0
        output = json.loads(capsys.readouterr().out)
        assert output["total"] == 2

    def test_metrics_mode(self, tmp_path, capsys):
        mod = _load_module()
        metrics_file = tmp_path / "m.json"
        metrics_file.write_text(json.dumps({"cpu": 42}), encoding="utf-8")
        rc = mod.main([str(metrics_file), "--metrics"])
        assert rc == 0
        output = json.loads(capsys.readouterr().out)
        assert output["cpu"] == 42
