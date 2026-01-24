"""Tests for CLI citation management commands."""

import json
import pytest
from pathlib import Path
from unittest.mock import patch
from scripts.memory_enhancement.__main__ import (
    cmd_add_citation,
    cmd_update_confidence,
    cmd_list_citations,
)
from scripts.memory_enhancement.models import Memory


class TestCmdAddCitation:
    """Tests for add-citation CLI command."""

    def test_add_citation_command_success(self, tmp_path, monkeypatch, capsys):
        """CLI adds citation successfully."""
        # Create memory file
        memory_file = tmp_path / ".serena" / "memories" / "test-memory.md"
        memory_file.parent.mkdir(parents=True)
        memory_file.write_text("---\nsubject: Test\n---\n# Content")

        # Create cited file
        cited_file = tmp_path / "src" / "test.py"
        cited_file.parent.mkdir(parents=True)
        cited_file.write_text("def example():\n    pass\n")

        # Change to tmp_path so memory ID resolution works
        monkeypatch.chdir(tmp_path)

        # Mock args
        class Args:
            memory = "test-memory"
            file = "src/test.py"
            line = 1
            snippet = "def example"
            dry_run = False

        with pytest.raises(SystemExit) as exc_info:
            cmd_add_citation(Args())

        assert exc_info.value.code == 0
        captured = capsys.readouterr()
        assert "✅ Citation added" in captured.out
        assert "src/test.py:1" in captured.out

    def test_add_citation_dry_run(self, tmp_path, monkeypatch, capsys):
        """Dry run previews without modifying file."""
        memory_file = tmp_path / ".serena" / "memories" / "test-memory.md"
        memory_file.parent.mkdir(parents=True)
        memory_file.write_text("---\nsubject: Test\n---\n# Content")

        monkeypatch.chdir(tmp_path)

        class Args:
            memory = "test-memory"
            file = "src/test.py"
            line = 10
            snippet = None
            dry_run = True

        with pytest.raises(SystemExit) as exc_info:
            cmd_add_citation(Args())

        assert exc_info.value.code == 0
        captured = capsys.readouterr()
        assert "[DRY RUN]" in captured.out
        assert "src/test.py" in captured.out

        # Verify file not modified
        memory = Memory.from_serena_file(memory_file)
        assert len(memory.citations) == 0

    def test_add_citation_invalid_file(self, tmp_path, monkeypatch, capsys):
        """Error handling for invalid citation."""
        memory_file = tmp_path / ".serena" / "memories" / "test-memory.md"
        memory_file.parent.mkdir(parents=True)
        memory_file.write_text("---\nsubject: Test\n---\n# Content")

        monkeypatch.chdir(tmp_path)

        class Args:
            memory = "test-memory"
            file = "src/missing.py"
            line = 10
            snippet = None
            dry_run = False

        with pytest.raises(SystemExit) as exc_info:
            cmd_add_citation(Args())

        assert exc_info.value.code == 2
        captured = capsys.readouterr()
        assert "Error" in captured.err
        assert "Invalid citation" in captured.err

    def test_add_citation_memory_not_found(self, tmp_path, monkeypatch, capsys):
        """Error when memory file doesn't exist."""
        monkeypatch.chdir(tmp_path)

        class Args:
            memory = "nonexistent"
            file = "src/test.py"
            line = 10
            snippet = None
            dry_run = False

        with pytest.raises(SystemExit) as exc_info:
            cmd_add_citation(Args())

        assert exc_info.value.code == 2
        captured = capsys.readouterr()
        assert "Memory not found" in captured.err


class TestCmdUpdateConfidence:
    """Tests for update-confidence CLI command."""

    def test_update_confidence_command_all_valid(self, tmp_path, monkeypatch, capsys):
        """CLI updates confidence successfully."""
        # Create memory with valid citation
        memory_file = tmp_path / ".serena" / "memories" / "test-memory.md"
        memory_file.parent.mkdir(parents=True)
        memory_file.write_text(
            """---
subject: Test
citations:
  - path: src/test.py
    line: 1
---
# Content
"""
        )

        # Create cited file
        cited_file = tmp_path / "src" / "test.py"
        cited_file.parent.mkdir(parents=True)
        cited_file.write_text("def test():\n    pass\n")

        monkeypatch.chdir(tmp_path)

        class Args:
            memory = "test-memory"

        with pytest.raises(SystemExit) as exc_info:
            cmd_update_confidence(Args())

        assert exc_info.value.code == 0
        captured = capsys.readouterr()
        assert "✅ Confidence updated" in captured.out
        assert "100.0%" in captured.out
        assert "1/1 valid" in captured.out

    def test_update_confidence_command_with_stale(self, tmp_path, monkeypatch, capsys):
        """Exit code 1 when stale citations found."""
        memory_file = tmp_path / ".serena" / "memories" / "test-memory.md"
        memory_file.parent.mkdir(parents=True)
        memory_file.write_text(
            """---
subject: Test
citations:
  - path: src/test.py
    line: 1
  - path: src/missing.py
    line: 10
---
# Content
"""
        )

        # Create only first cited file
        cited_file = tmp_path / "src" / "test.py"
        cited_file.parent.mkdir(parents=True)
        cited_file.write_text("def test():\n    pass\n")

        monkeypatch.chdir(tmp_path)

        class Args:
            memory = "test-memory"

        with pytest.raises(SystemExit) as exc_info:
            cmd_update_confidence(Args())

        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "✅ Confidence updated" in captured.out
        assert "50.0%" in captured.out
        assert "⚠️  1 stale citation(s) found" in captured.out

    def test_update_confidence_memory_not_found(self, tmp_path, monkeypatch, capsys):
        """Error when memory doesn't exist."""
        monkeypatch.chdir(tmp_path)

        class Args:
            memory = "nonexistent"

        with pytest.raises(SystemExit) as exc_info:
            cmd_update_confidence(Args())

        assert exc_info.value.code == 2
        captured = capsys.readouterr()
        assert "Memory not found" in captured.err


class TestCmdListCitations:
    """Tests for list-citations CLI command."""

    def test_list_citations_command_human_readable(self, tmp_path, monkeypatch, capsys):
        """CLI displays citations with status indicators."""
        memory_file = tmp_path / ".serena" / "memories" / "test-memory.md"
        memory_file.parent.mkdir(parents=True)
        memory_file.write_text(
            """---
subject: Test Memory
citations:
  - path: src/valid.py
    line: 1
    snippet: "def valid"
  - path: src/missing.py
    line: 10
---
# Content
"""
        )

        # Create valid file only
        valid_file = tmp_path / "src" / "valid.py"
        valid_file.parent.mkdir(parents=True)
        valid_file.write_text("def valid():\n    pass\n")

        monkeypatch.chdir(tmp_path)

        class Args:
            memory = "test-memory"
            json = False

        with pytest.raises(SystemExit) as exc_info:
            cmd_list_citations(Args())

        assert exc_info.value.code == 0
        captured = capsys.readouterr()
        assert "Citations for test-memory" in captured.out
        assert "Total: 2" in captured.out
        assert "✅ src/valid.py:1" in captured.out
        assert "❌ src/missing.py:10" in captured.out
        assert "Reason: File not found" in captured.out

    def test_list_citations_command_json_output(self, tmp_path, monkeypatch, capsys):
        """JSON output for programmatic usage."""
        memory_file = tmp_path / ".serena" / "memories" / "test-memory.md"
        memory_file.parent.mkdir(parents=True)
        memory_file.write_text(
            """---
subject: Test
citations:
  - path: src/test.py
    line: 1
---
# Content
"""
        )

        # Create cited file
        cited_file = tmp_path / "src" / "test.py"
        cited_file.parent.mkdir(parents=True)
        cited_file.write_text("def test():\n    pass\n")

        monkeypatch.chdir(tmp_path)

        class Args:
            memory = "test-memory"
            json = True

        with pytest.raises(SystemExit) as exc_info:
            cmd_list_citations(Args())

        assert exc_info.value.code == 0
        captured = capsys.readouterr()

        # Verify valid JSON
        output = json.loads(captured.out)
        assert "citations" in output
        assert len(output["citations"]) == 1
        assert output["citations"][0]["path"] == "src/test.py"
        assert output["citations"][0]["valid"] is True

    def test_list_citations_no_citations(self, tmp_path, monkeypatch, capsys):
        """Display message when memory has no citations."""
        memory_file = tmp_path / ".serena" / "memories" / "test-memory.md"
        memory_file.parent.mkdir(parents=True)
        memory_file.write_text("---\nsubject: Test\n---\n# Content")

        monkeypatch.chdir(tmp_path)

        class Args:
            memory = "test-memory"
            json = False

        with pytest.raises(SystemExit) as exc_info:
            cmd_list_citations(Args())

        assert exc_info.value.code == 0
        captured = capsys.readouterr()
        assert "No citations found" in captured.out

    def test_list_citations_memory_not_found(self, tmp_path, monkeypatch, capsys):
        """Error when memory doesn't exist."""
        monkeypatch.chdir(tmp_path)

        class Args:
            memory = "nonexistent"
            json = False

        with pytest.raises(SystemExit) as exc_info:
            cmd_list_citations(Args())

        assert exc_info.value.code == 2
        captured = capsys.readouterr()
        assert "Memory not found" in captured.err
