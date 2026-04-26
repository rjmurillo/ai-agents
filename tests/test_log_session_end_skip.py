#!/usr/bin/env python3
"""Tests for scripts/log_session_end_skip.py."""

from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
from unittest import mock

import pytest

_SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "log_session_end_skip.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("log_session_end_skip", _SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


class TestBuildEvent:
    def test_populates_required_fields(self):
        mod = _load_module()
        event = mod.build_event(reason="forgot to run", session_id="S-42")

        assert event["event"] == "session_closed_without_session_end"
        assert event["reason"] == "forgot to run"
        assert event["sessionId"] == "S-42"
        assert "timestamp" in event
        assert event["timestamp"].endswith("+00:00")

    def test_falls_back_to_env_session_id(self):
        mod = _load_module()
        with mock.patch.dict(os.environ, {"OPENCLAW_SESSION_ID": "env-session"}):
            event = mod.build_event(reason="x")
        assert event["sessionId"] == "env-session"

    def test_defaults_session_id_when_no_env(self):
        mod = _load_module()
        with mock.patch.dict(os.environ, {}, clear=True):
            event = mod.build_event(reason="x")
        assert event["sessionId"] == "unknown"


class TestAppendEvent:
    def test_appends_jsonl_line_and_creates_parent(self, tmp_path: Path):
        mod = _load_module()
        target = tmp_path / "nested" / "skips.jsonl"
        mod.append_event({"a": "1"}, target)
        mod.append_event({"b": "2"}, target)

        lines = target.read_text(encoding="utf-8").splitlines()
        assert len(lines) == 2
        assert json.loads(lines[0]) == {"a": "1"}
        assert json.loads(lines[1]) == {"b": "2"}


class TestMain:
    def test_logs_skip_and_returns_zero(self, tmp_path: Path, capsys):
        mod = _load_module()
        log = tmp_path / "skips.jsonl"
        rc = mod.main(
            [
                "--reason",
                "timed out",
                "--session-id",
                "abc",
                "--log-path",
                str(log),
            ]
        )
        assert rc == 0
        entries = [json.loads(line) for line in log.read_text().splitlines()]
        assert len(entries) == 1
        assert entries[0]["reason"] == "timed out"
        assert entries[0]["sessionId"] == "abc"
        out = capsys.readouterr().out
        assert str(log) in out

    def test_rejects_empty_reason(self, tmp_path: Path):
        mod = _load_module()
        log = tmp_path / "skips.jsonl"
        rc = mod.main(["--reason", "   ", "--log-path", str(log)])
        assert rc == 2
        assert not log.exists()

    def test_returns_three_on_io_failure(self, tmp_path: Path, monkeypatch):
        mod = _load_module()

        def _raise(*_a, **_k):
            raise OSError("disk full")

        monkeypatch.setattr(mod, "append_event", _raise)
        # Use /tmp path which is allowed by path validation
        rc = mod.main(["--reason", "x", "--log-path", str(tmp_path / "s.jsonl")])
        assert rc == 3

    def test_rejects_path_traversal(self, tmp_path: Path):
        mod = _load_module()
        # Attempt to write outside project root and /tmp
        rc = mod.main(["--reason", "x", "--log-path", "/etc/evil.jsonl"])
        assert rc == 2

    def test_reason_required(self):
        mod = _load_module()
        with pytest.raises(SystemExit):
            mod.parse_args([])
