#!/usr/bin/env python3
"""Tests for observability query_logs.py script."""

from __future__ import annotations

import importlib.util
import json
import os
import sys
import tempfile
from pathlib import Path

_SCRIPT = os.path.join(
    os.path.dirname(__file__), "..", "scripts", "query_logs.py",
)


def _load_module():
    spec = importlib.util.spec_from_file_location("query_logs", _SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _sample_events():
    return [
        {"timestamp": "2026-03-30T10:00:00Z", "event_type": "session_start", "session_id": "sess-001", "agent": "implementer", "level": "INFO", "message": "Session started"},
        {"timestamp": "2026-03-30T10:00:01Z", "event_type": "tool_call", "session_id": "sess-001", "agent": "implementer", "level": "INFO", "tool": {"name": "Read", "duration_ms": 45, "success": True, "input_summary": "src/main.py"}},
        {"timestamp": "2026-03-30T10:00:02Z", "event_type": "tool_call", "session_id": "sess-001", "agent": "implementer", "level": "INFO", "tool": {"name": "Edit", "duration_ms": 800, "success": True}},
        {"timestamp": "2026-03-30T10:00:03Z", "event_type": "decision", "session_id": "sess-001", "agent": "implementer", "level": "INFO", "decision": {"action": "Edit existing function", "reasoning": "Function exists already", "alternatives_considered": ["Rewrite"]}},
        {"timestamp": "2026-03-30T10:00:05Z", "event_type": "error", "session_id": "sess-001", "agent": "implementer", "level": "ERROR", "error": {"message": "Test failed", "category": "test_failure", "recoverable": True}},
        {"timestamp": "2026-03-30T10:00:10Z", "event_type": "tool_call", "session_id": "sess-002", "agent": "qa", "level": "INFO", "tool": {"name": "Bash", "duration_ms": 2000, "success": False}},
        {"timestamp": "2026-03-30T10:00:11Z", "event_type": "metric", "session_id": "sess-002", "agent": "qa", "level": "INFO", "metric": {"name": "test_duration", "value": 12.5, "unit": "seconds"}},
        {"timestamp": "2026-03-30T10:00:12Z", "event_type": "session_end", "session_id": "sess-002", "agent": "qa", "level": "INFO", "message": "Session ended"},
    ]


def _write_jsonl(events):
    """Write events to a temp JSONL file, return path."""
    tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False)
    for event in events:
        tmp.write(json.dumps(event) + "\n")
    tmp.close()
    return Path(tmp.name)


class TestParseEvent:
    def test_valid_json(self):
        mod = _load_module()
        event = mod.parse_event('{"event_type": "error", "session_id": "s1", "timestamp": "2026-01-01T00:00:00Z"}', 1)
        assert event is not None
        assert event["event_type"] == "error"

    def test_empty_line(self):
        mod = _load_module()
        assert mod.parse_event("", 1) is None
        assert mod.parse_event("   ", 1) is None

    def test_invalid_json(self):
        mod = _load_module()
        assert mod.parse_event("{bad json", 1) is None


class TestLoadEvents:
    def test_loads_all_events(self):
        mod = _load_module()
        events = _sample_events()
        path = _write_jsonl(events)
        try:
            loaded = mod.load_events(path)
            assert len(loaded) == len(events)
        finally:
            os.unlink(path)

    def test_skips_blank_lines(self):
        mod = _load_module()
        path = _write_jsonl([])
        with open(path, "a") as f:
            f.write("\n")
            f.write(json.dumps({"timestamp": "t", "event_type": "error", "session_id": "s"}) + "\n")
            f.write("\n")
        try:
            loaded = mod.load_events(path)
            assert len(loaded) == 1
        finally:
            os.unlink(path)


class TestFilterEvents:
    def test_filter_by_event_type(self):
        mod = _load_module()
        events = _sample_events()
        result = mod.filter_events(events, event_type="tool_call")
        assert len(result) == 3
        assert all(e["event_type"] == "tool_call" for e in result)

    def test_filter_by_session_id(self):
        mod = _load_module()
        events = _sample_events()
        result = mod.filter_events(events, session_id="sess-002")
        assert len(result) == 3
        assert all(e["session_id"] == "sess-002" for e in result)

    def test_filter_by_agent(self):
        mod = _load_module()
        events = _sample_events()
        result = mod.filter_events(events, agent="qa")
        assert len(result) == 3

    def test_filter_by_level(self):
        mod = _load_module()
        events = _sample_events()
        result = mod.filter_events(events, level="ERROR")
        assert len(result) == 1
        assert result[0]["event_type"] == "error"

    def test_filter_by_tool_name(self):
        mod = _load_module()
        events = _sample_events()
        result = mod.filter_events(events, tool_name="Read")
        assert len(result) == 1
        assert result[0]["tool"]["name"] == "Read"

    def test_errors_only(self):
        mod = _load_module()
        events = _sample_events()
        result = mod.filter_events(events, errors_only=True)
        assert len(result) == 1
        assert result[0]["event_type"] == "error"

    def test_slow_threshold(self):
        mod = _load_module()
        events = _sample_events()
        result = mod.filter_events(events, slow_threshold_ms=500)
        assert len(result) == 2
        for e in result:
            assert e["tool"]["duration_ms"] >= 500

    def test_since_filter(self):
        mod = _load_module()
        events = _sample_events()
        result = mod.filter_events(events, since="2026-03-30T10:00:05Z")
        assert len(result) == 4

    def test_until_filter(self):
        mod = _load_module()
        events = _sample_events()
        result = mod.filter_events(events, until="2026-03-30T10:00:02Z")
        assert len(result) == 3

    def test_combined_filters(self):
        mod = _load_module()
        events = _sample_events()
        result = mod.filter_events(events, event_type="tool_call", agent="implementer")
        assert len(result) == 2

    def test_no_match(self):
        mod = _load_module()
        events = _sample_events()
        result = mod.filter_events(events, agent="nonexistent")
        assert len(result) == 0


class TestSummarizeSession:
    def test_groups_by_session(self):
        mod = _load_module()
        events = _sample_events()
        summary = mod.summarize_session(events)
        sessions = summary["sessions"]
        assert len(sessions) == 2
        ids = {s["session_id"] for s in sessions}
        assert ids == {"sess-001", "sess-002"}

    def test_counts_events(self):
        mod = _load_module()
        events = _sample_events()
        summary = mod.summarize_session(events)
        sess1 = next(s for s in summary["sessions"] if s["session_id"] == "sess-001")
        assert sess1["event_count"] == 5
        assert sess1["tool_calls"] == 2
        assert sess1["decisions"] == 1
        assert sess1["errors"] == 1

    def test_total_tool_duration(self):
        mod = _load_module()
        events = _sample_events()
        summary = mod.summarize_session(events)
        sess1 = next(s for s in summary["sessions"] if s["session_id"] == "sess-001")
        assert sess1["total_tool_duration_ms"] == 845.0


class TestSummarizeTools:
    def test_groups_by_tool(self):
        mod = _load_module()
        events = _sample_events()
        summary = mod.summarize_tools(events)
        tools = summary["tools"]
        assert len(tools) == 3
        names = {t["name"] for t in tools}
        assert names == {"Read", "Edit", "Bash"}

    def test_tracks_success_failure(self):
        mod = _load_module()
        events = _sample_events()
        summary = mod.summarize_tools(events)
        bash = next(t for t in summary["tools"] if t["name"] == "Bash")
        assert bash["failure_count"] == 1
        assert bash["success_count"] == 0

    def test_calculates_avg_duration(self):
        mod = _load_module()
        events = _sample_events()
        summary = mod.summarize_tools(events)
        read = next(t for t in summary["tools"] if t["name"] == "Read")
        assert read["avg_duration_ms"] == 45.0


class TestFormatTable:
    def test_empty_events(self):
        mod = _load_module()
        result = mod.format_table([])
        assert result == "No events found."

    def test_has_header(self):
        mod = _load_module()
        events = _sample_events()[:1]
        result = mod.format_table(events)
        assert "Timestamp" in result
        assert "Type" in result

    def test_shows_tool_details(self):
        mod = _load_module()
        events = [e for e in _sample_events() if e.get("tool", {}).get("name") == "Read"]
        result = mod.format_table(events)
        assert "Read" in result
        assert "45" in result


class TestMainCLI:
    def test_missing_file(self):
        mod = _load_module()
        sys.argv = ["query_logs.py", "/nonexistent/file.jsonl"]
        assert mod.main() == 1

    def test_json_output(self):
        mod = _load_module()
        path = _write_jsonl(_sample_events())
        try:
            sys.argv = ["query_logs.py", str(path), "--output", "json"]
            assert mod.main() == 0
        finally:
            os.unlink(path)

    def test_table_output(self):
        mod = _load_module()
        path = _write_jsonl(_sample_events())
        try:
            sys.argv = ["query_logs.py", str(path), "--output", "table"]
            assert mod.main() == 0
        finally:
            os.unlink(path)

    def test_summary_sessions_output(self):
        mod = _load_module()
        path = _write_jsonl(_sample_events())
        try:
            sys.argv = ["query_logs.py", str(path), "--output", "summary-sessions"]
            assert mod.main() == 0
        finally:
            os.unlink(path)

    def test_summary_tools_output(self):
        mod = _load_module()
        path = _write_jsonl(_sample_events())
        try:
            sys.argv = ["query_logs.py", str(path), "--output", "summary-tools"]
            assert mod.main() == 0
        finally:
            os.unlink(path)

    def test_filter_flags(self):
        mod = _load_module()
        path = _write_jsonl(_sample_events())
        try:
            sys.argv = [
                "query_logs.py", str(path),
                "--event-type", "error",
                "--errors-only",
                "--output", "json",
            ]
            assert mod.main() == 0
        finally:
            os.unlink(path)
