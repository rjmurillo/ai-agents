"""Tests for invoke_memory_cross_reference.py."""

import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

SCRIPT_DIR = Path(__file__).resolve().parents[3] / ".claude" / "skills" / "memory" / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

import invoke_memory_cross_reference


class TestBuildParser:
    """Tests for build_parser function."""

    def test_parser_has_expected_args(self):
        parser = invoke_memory_cross_reference.build_parser()
        args = parser.parse_args([])
        assert hasattr(args, "output_json")
        assert hasattr(args, "memories_path")

    def test_output_json_flag(self):
        parser = invoke_memory_cross_reference.build_parser()
        args = parser.parse_args(["--output-json"])
        assert args.output_json is True


class TestMainAlwaysExitsZero:
    """Test that main always returns 0 (fail-open for hooks)."""

    def test_returns_zero_on_success(self, tmp_path):
        # Create a memories directory with files for processing
        (tmp_path / "test-memory.md").write_text("# Test")
        result = invoke_memory_cross_reference.main([
            "--memories-path", str(tmp_path),
            "--output-json",
            "--skip-path-validation",
        ])
        assert result == 0

    def test_returns_zero_on_empty_dir(self, tmp_path):
        result = invoke_memory_cross_reference.main([
            "--memories-path", str(tmp_path),
            "--output-json",
            "--skip-path-validation",
        ])
        assert result == 0

    def test_returns_zero_with_files_flag(self, tmp_path):
        test_file = tmp_path / "test-index.md"
        test_file.write_text("| key | val |")
        result = invoke_memory_cross_reference.main([
            "--memories-path", str(tmp_path),
            "--files", str(test_file),
            "--output-json",
            "--skip-path-validation",
        ])
        assert result == 0


class TestMainOutputJson:
    """Tests for JSON output from main."""

    def test_json_output_has_success_field(self, tmp_path, capsys):
        (tmp_path / "test.md").write_text("# Test")
        invoke_memory_cross_reference.main([
            "--memories-path", str(tmp_path),
            "--output-json",
            "--skip-path-validation",
        ])
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert "Success" in data

    def test_json_output_has_error_list(self, tmp_path, capsys):
        invoke_memory_cross_reference.main([
            "--memories-path", str(tmp_path),
            "--output-json",
            "--skip-path-validation",
        ])
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert "Errors" in data
        assert isinstance(data["Errors"], list)
