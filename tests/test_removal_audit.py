"""Tests for the shared worktree removal audit writer (issue #4790)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.maintenance import removal_audit
from scripts.maintenance.removal_audit import audit_log_path_for as _real_audit_log_path_for


def _lines(log_path: Path) -> list[dict]:
    return [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines()]


class TestAppendRecord:
    def test_writer_fields_are_stamped_on_the_record(self, tmp_path):
        log_path = tmp_path / "audit.jsonl"

        removal_audit.append_record("some_tool", "/wt/a", {"extra": 1}, log_path=log_path)

        [record] = _lines(log_path)
        assert record["schemaVersion"] == removal_audit.SCHEMA_VERSION
        assert record["tool"] == "some_tool"
        assert record["path"] == "/wt/a"
        assert record["extra"] == 1
        assert isinstance(record["ts"], str) and record["ts"]

    def test_caller_fields_cannot_overwrite_the_stamped_ones(self, tmp_path):
        log_path = tmp_path / "audit.jsonl"

        removal_audit.append_record(
            "real_tool",
            "/wt/real",
            {"tool": "spoof", "path": "/wt/spoof", "schemaVersion": 99, "ts": "spoof"},
            log_path=log_path,
        )

        [record] = _lines(log_path)
        assert record["tool"] == "real_tool"
        assert record["path"] == "/wt/real"
        assert record["schemaVersion"] == removal_audit.SCHEMA_VERSION
        assert record["ts"] != "spoof"

    def test_second_call_appends_rather_than_overwrites(self, tmp_path):
        log_path = tmp_path / "audit.jsonl"

        removal_audit.append_record("a", "/wt/1", {}, log_path=log_path)
        removal_audit.append_record("b", "/wt/2", {}, log_path=log_path)

        assert [(r["tool"], r["path"]) for r in _lines(log_path)] == [
            ("a", "/wt/1"),
            ("b", "/wt/2"),
        ]

    def test_creates_missing_parent_directories(self, tmp_path):
        log_path = tmp_path / "nested" / "missing" / "audit.jsonl"

        removal_audit.append_record("a", "/wt/1", {}, log_path=log_path)

        assert len(_lines(log_path)) == 1

    def test_unwritable_log_raises_oserror(self, tmp_path):
        blocker = tmp_path / "blocker"
        blocker.write_text("a file where a directory is needed")

        with pytest.raises(OSError):
            removal_audit.append_record("a", "/wt/1", {}, log_path=blocker / "audit.jsonl")


class TestAuditLogPathFor:
    def test_resolves_under_the_main_worktree(self, tmp_path):
        resolved = _real_audit_log_path_for(str(tmp_path / "main"))

        assert resolved == (
            tmp_path / "main" / ".project-toolkit" / "metrics" / "gc-worktree-removals.jsonl"
        )
