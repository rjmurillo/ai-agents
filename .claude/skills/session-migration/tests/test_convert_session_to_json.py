#!/usr/bin/env python3
"""Tests for session-migration skill convert_session_to_json.py."""

from __future__ import annotations

import importlib
import importlib.util
import json
import os

_SCRIPT = os.path.join(
    os.path.dirname(__file__), "..", "scripts", "convert_session_to_json.py",
)


def _load_module():
    spec = importlib.util.spec_from_file_location("convert_session_to_json", _SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TestConvertMarkdownSession:
    def test_extracts_session_number_from_filename(self):
        mod = _load_module()
        result = mod._convert_markdown_session("# Session", "2026-01-09-session-385.md")
        assert result["session"]["number"] == 385

    def test_extracts_date_from_filename(self):
        mod = _load_module()
        result = mod._convert_markdown_session("# Session", "2026-01-09-session-1.md")
        assert result["session"]["date"] == "2026-01-09"

    def test_extracts_branch(self):
        mod = _load_module()
        content = "**Branch**: `feat/my-feature`\n"
        result = mod._convert_markdown_session(content, "2026-01-09-session-1.md")
        assert result["session"]["branch"] == "feat/my-feature"

    def test_extracts_commit(self):
        mod = _load_module()
        content = "**Starting Commit**: `abc1234`\n"
        result = mod._convert_markdown_session(content, "2026-01-09-session-1.md")
        assert result["session"]["startingCommit"] == "abc1234"

    def test_extracts_objective(self):
        mod = _load_module()
        content = "## Objective\n\nImplement feature X\n\n## Next"
        result = mod._convert_markdown_session(content, "2026-01-09-session-1.md")
        assert result["session"]["objective"] == "Implement feature X"

    def test_default_objective_when_missing(self):
        mod = _load_module()
        result = mod._convert_markdown_session("# Session", "2026-01-09-session-1.md")
        assert result["session"]["objective"] == "[Migrated from markdown]"

    def test_protocol_compliance_structure(self):
        mod = _load_module()
        result = mod._convert_markdown_session("# Session", "2026-01-09-session-1.md")
        pc = result["protocolCompliance"]
        assert "sessionStart" in pc
        assert "sessionEnd" in pc
        assert "serenaActivated" in pc["sessionStart"]
        assert "checklistComplete" in pc["sessionEnd"]


class TestMainFunction:
    def test_nonexistent_path_returns_1(self):
        mod = _load_module()
        result = mod.main(["/nonexistent/path"])
        assert result == 1

    def test_dry_run_no_files_written(self, tmp_path):
        md_file = tmp_path / "2026-01-09-session-1.md"
        md_file.write_text("**Branch**: `feat/test`\n## Objective\n\nTest\n")

        mod = _load_module()
        result = mod.main([str(md_file), "--dry-run"])
        assert result == 0

        json_file = tmp_path / "2026-01-09-session-1.json"
        assert not json_file.exists()

    def test_converts_single_file(self, tmp_path):
        md_file = tmp_path / "2026-01-09-session-1.md"
        md_file.write_text("**Branch**: `feat/test`\n## Objective\n\nTest obj\n")

        mod = _load_module()
        result = mod.main([str(md_file)])
        assert result == 0

        json_file = tmp_path / "2026-01-09-session-1.json"
        assert json_file.exists()
        data = json.loads(json_file.read_text())
        assert data["session"]["branch"] == "feat/test"
        assert data["session"]["objective"] == "Test obj"

    def test_skips_existing_json(self, tmp_path):
        md_file = tmp_path / "2026-01-09-session-1.md"
        md_file.write_text("# Session\n")
        json_file = tmp_path / "2026-01-09-session-1.json"
        json_file.write_text('{"existing": true}')

        mod = _load_module()
        result = mod.main([str(md_file)])
        assert result == 0

        data = json.loads(json_file.read_text())
        assert data == {"existing": True}

    def test_force_overwrites_existing(self, tmp_path):
        md_file = tmp_path / "2026-01-09-session-1.md"
        md_file.write_text("**Branch**: `feat/new`\n## Objective\n\nNew\n")
        json_file = tmp_path / "2026-01-09-session-1.json"
        json_file.write_text('{"existing": true}')

        mod = _load_module()
        result = mod.main([str(md_file), "--force"])
        assert result == 0

        data = json.loads(json_file.read_text())
        assert data["session"]["branch"] == "feat/new"
