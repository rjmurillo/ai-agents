"""Tests for sync_session_documentation.py."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

SCRIPT = str(
    Path(__file__).resolve().parents[2]
    / ".claude"
    / "skills"
    / "workflow"
    / "scripts"
    / "sync_session_documentation.py"
)


def _run_script(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, SCRIPT, *args],
        capture_output=True,
        text=True,
        timeout=30,
    )


class TestDryRun:
    def test_produces_output_without_writing_files(self):
        result = _run_script("--dry-run")
        assert "DRY RUN" in result.stdout
        assert "Structured Output" in result.stdout

    def test_emits_valid_json(self):
        result = _run_script("--dry-run")
        # Extract JSON after "Structured Output:" line
        lines = result.stdout.splitlines()
        json_lines = []
        capture = False
        for line in lines:
            if "Structured Output" in line:
                capture = True
                continue
            if capture:
                json_lines.append(line)

        data = json.loads("\n".join(json_lines))
        assert isinstance(data, dict)

    def test_json_contains_required_fields(self):
        result = _run_script("--dry-run")
        lines = result.stdout.splitlines()
        json_lines = []
        capture = False
        for line in lines:
            if "Structured Output" in line:
                capture = True
                continue
            if capture:
                json_lines.append(line)

        data = json.loads("\n".join(json_lines))
        assert "date" in data
        assert "branch" in data
        assert "commits" in data
        assert "agents" in data
        assert "learnings" in data


class TestReportContent:
    def test_generates_mermaid_diagram(self):
        result = _run_script("--dry-run")
        assert "mermaid" in result.stdout
        assert "sequenceDiagram" in result.stdout

    def test_includes_workflow_sections(self):
        result = _run_script("--dry-run")
        assert "Agents Invoked" in result.stdout
        assert "Decisions Made" in result.stdout
        assert "Artifacts Created" in result.stdout
        assert "Retrospective Learnings" in result.stdout


class TestLookbackHours:
    def test_accepts_custom_lookback(self):
        result = _run_script("--dry-run", "--lookback-hours", "1")
        assert "Lookback: 1 hours" in result.stdout


class TestQueryAgentsHistory:
    """Tests for MCP agents://history integration."""

    def test_returns_none_when_no_mcp(self, monkeypatch):
        """Without MCP env or cache, should return None."""
        monkeypatch.delenv("AGENTS_HISTORY_JSON", raising=False)
        sys.path.insert(
            0,
            str(
                Path(__file__).resolve().parents[2]
                / ".claude"
                / "skills"
                / "workflow"
                / "scripts"
            ),
        )
        from sync_session_documentation import query_agents_history

        result = query_agents_history(8)
        assert result is None

    def test_returns_list_from_env(self, monkeypatch):
        """When AGENTS_HISTORY_JSON is set with valid JSON list, returns it."""
        monkeypatch.setenv(
            "AGENTS_HISTORY_JSON",
            json.dumps([{"agent": "implementer", "ts": "2026-01-01T00:00:00Z"}]),
        )
        sys.path.insert(
            0,
            str(
                Path(__file__).resolve().parents[2]
                / ".claude"
                / "skills"
                / "workflow"
                / "scripts"
            ),
        )
        from sync_session_documentation import query_agents_history

        result = query_agents_history(8)
        assert isinstance(result, list)
        assert len(result) == 1
        assert result[0]["agent"] == "implementer"

    def test_returns_none_on_invalid_json(self, monkeypatch):
        """Invalid JSON in env var should fall through gracefully."""
        monkeypatch.setenv("AGENTS_HISTORY_JSON", "not-json{{{")
        sys.path.insert(
            0,
            str(
                Path(__file__).resolve().parents[2]
                / ".claude"
                / "skills"
                / "workflow"
                / "scripts"
            ),
        )
        from sync_session_documentation import query_agents_history

        result = query_agents_history(8)
        assert result is None


class TestSyncSerenaMemory:
    """Tests for Serena memory synchronization."""

    def test_writes_memory_file(self, tmp_path):
        """Should write memory markdown to .serena/memories/."""
        memory_dir = tmp_path / ".serena" / "memories"
        memory_dir.mkdir(parents=True)

        sys.path.insert(
            0,
            str(
                Path(__file__).resolve().parents[2]
                / ".claude"
                / "skills"
                / "workflow"
                / "scripts"
            ),
        )
        from sync_session_documentation import sync_serena_memory

        result = sync_serena_memory(
            str(tmp_path),
            agents=["implementer", "qa"],
            decisions=["Used Python per ADR-042"],
            learnings=["Test early"],
            branch="feature/test",
            date="2026-03-09",
        )
        assert result is True
        mem_file = memory_dir / "session-sync-2026-03-09.md"
        assert mem_file.exists()
        content = mem_file.read_text()
        assert "implementer" in content
        assert "Used Python per ADR-042" in content
        assert "Test early" in content

    def test_returns_false_when_no_serena(self, tmp_path):
        """Without .serena/memories/ dir, should return False gracefully."""
        sys.path.insert(
            0,
            str(
                Path(__file__).resolve().parents[2]
                / ".claude"
                / "skills"
                / "workflow"
                / "scripts"
            ),
        )
        from sync_session_documentation import sync_serena_memory

        result = sync_serena_memory(
            str(tmp_path),
            agents=[],
            decisions=[],
            learnings=[],
            branch="main",
            date="2026-03-09",
        )
        assert result is False


class TestPathTraversalPrevention:
    """CWE-22: Verify path traversal is blocked."""

    def test_rejects_path_outside_repo(self):
        traversal_path = os.path.join(tempfile.gettempdir(), "pwned.md")
        result = _run_script("--output-path", traversal_path)
        combined = result.stdout + result.stderr
        assert (
            "Path traversal attempt detected" in combined
            or "outside the repository root" in combined
            or result.returncode != 0
        )
