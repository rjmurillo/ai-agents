"""Tests for .github/scripts/parse_pr_standards.py."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Import the module under test
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / ".github" / "scripts"))
import parse_pr_standards  # noqa: E402


@pytest.fixture
def github_output_file(tmp_path: Path):
    """Create a temp file to act as GITHUB_OUTPUT."""
    f = tmp_path / "github_output"
    f.touch()
    return f


@pytest.fixture
def env_with_output(github_output_file: Path):
    """Minimal env vars for the script."""
    return {
        "PR_TITLE": "feat(test): add new feature",
        "PR_BODY": "## Summary\nTest body\n\nCloses #123\n\n## Changes\n- something",
        "GITHUB_OUTPUT": str(github_output_file),
        "GITHUB_RUN_ID": "12345",
        "GITHUB_RUN_ATTEMPT": "1",
    }


class TestWriteOutputs:
    """Test _write_outputs writes correct format."""

    def test_writes_all_keys(self, github_output_file: Path) -> None:
        parse_pr_standards._write_outputs(
            str(github_output_file), "PASS", "WARN", "Missing sections", "warning1"
        )
        content = github_output_file.read_text()
        assert "keywords_status=PASS" in content
        assert "template_status=WARN" in content
        assert "template_message<<TEMPLATE_EOF" in content
        assert "Missing sections" in content
        assert "TEMPLATE_EOF" in content
        assert "standards_warnings<<STANDARDS_EOF" in content
        assert "warning1" in content
        assert "STANDARDS_EOF" in content

    def test_skip_outputs(self, github_output_file: Path) -> None:
        parse_pr_standards._write_skip_outputs(str(github_output_file))
        content = github_output_file.read_text()
        assert "keywords_status=SKIP" in content
        assert "template_status=SKIP" in content

    def test_no_output_when_empty_path(self) -> None:
        # Should not raise
        parse_pr_standards._write_outputs("", "PASS", "PASS", "", "")


class TestMain:
    """Test main function integration."""

    def test_missing_title_returns_2(self) -> None:
        with patch.dict(os.environ, {"PR_TITLE": "", "GITHUB_OUTPUT": ""}, clear=False):
            assert parse_pr_standards.main() == 2

    def test_valid_input_returns_0(self, env_with_output: dict, github_output_file: Path) -> None:
        valid_output = json.dumps(
            {
                "Success": True,
                "Validations": {
                    "IssueKeywords": {"Status": "PASS", "Message": "Found keywords"},
                    "TemplateCompliance": {
                        "Status": "PASS",
                        "Message": "All sections complete",
                    },
                },
                "Warnings": [],
                "Errors": [],
            }
        )
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = valid_output
        mock_result.stderr = ""

        with (
            patch.dict(os.environ, env_with_output, clear=False),
            patch("parse_pr_standards.subprocess.run", return_value=mock_result),
        ):
            assert parse_pr_standards.main() == 0

        content = github_output_file.read_text()
        assert "keywords_status=PASS" in content
        assert "template_status=PASS" in content

    def test_empty_output_returns_1(self, env_with_output: dict, github_output_file: Path) -> None:
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = ""
        mock_result.stderr = ""

        with (
            patch.dict(os.environ, env_with_output, clear=False),
            patch("parse_pr_standards.subprocess.run", return_value=mock_result),
        ):
            assert parse_pr_standards.main() == 1

        content = github_output_file.read_text()
        assert "keywords_status=SKIP" in content

    def test_invalid_json_returns_1(self, env_with_output: dict, github_output_file: Path) -> None:
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "not json"
        mock_result.stderr = ""

        with (
            patch.dict(os.environ, env_with_output, clear=False),
            patch("parse_pr_standards.subprocess.run", return_value=mock_result),
        ):
            assert parse_pr_standards.main() == 1

    def test_temp_file_uses_run_id(self, env_with_output: dict) -> None:
        """Verify temp file includes run ID for uniqueness."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = json.dumps(
            {
                "Success": True,
                "Validations": {
                    "IssueKeywords": {"Status": "PASS", "Message": "ok"},
                    "TemplateCompliance": {"Status": "PASS", "Message": "ok"},
                },
                "Warnings": [],
                "Errors": [],
            }
        )
        mock_result.stderr = ""

        created_files = []
        original_named_temp = tempfile.NamedTemporaryFile

        def track_tempfile(*args, **kwargs):
            f = original_named_temp(*args, **kwargs)
            created_files.append(f.name)
            return f

        with (
            patch.dict(os.environ, env_with_output, clear=False),
            patch("parse_pr_standards.subprocess.run", return_value=mock_result),
            patch("parse_pr_standards.tempfile.NamedTemporaryFile", side_effect=track_tempfile),
        ):
            parse_pr_standards.main()

        assert len(created_files) == 1
        assert "12345" in created_files[0]
