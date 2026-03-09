"""Tests for skill_output module and validate_skill_output script.

Covers:
- get_output_format resolution
- write_skill_output JSON envelope structure
- write_skill_error JSON envelope structure
- validate_skill_output integration (valid, invalid, path traversal)
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from unittest import mock

import pytest

# Add scripts directory to path for imports
REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = REPO_ROOT / "scripts"
sys.path.insert(0, str(REPO_ROOT))

from scripts.skill_output import get_output_format, write_skill_error, write_skill_output
from scripts.validate_skill_output import validate_envelope


class TestGetOutputFormat:
    """Tests for get_output_format function."""

    def test_returns_json_when_requested(self) -> None:
        assert get_output_format("json") == "json"
        assert get_output_format("JSON") == "json"

    def test_returns_human_when_requested(self) -> None:
        assert get_output_format("human") == "human"
        assert get_output_format("Human") == "human"

    @mock.patch.dict(os.environ, {"CI": "true"}, clear=False)
    def test_returns_json_when_ci_env_set(self) -> None:
        assert get_output_format("auto") == "json"

    @mock.patch.dict(os.environ, {"GITHUB_ACTIONS": "true"}, clear=False)
    def test_returns_json_when_github_actions_set(self) -> None:
        assert get_output_format("auto") == "json"

    @mock.patch.dict(os.environ, {"TF_BUILD": "true"}, clear=False)
    def test_returns_json_when_tf_build_set(self) -> None:
        assert get_output_format("auto") == "json"


class TestWriteSkillOutput:
    """Tests for write_skill_output function."""

    def test_produces_valid_json_envelope(self, capsys: pytest.CaptureFixture[str]) -> None:
        data = {"Number": 42, "Title": "Test PR"}
        result = write_skill_output(
            data, output_format="json", human_summary="Test", script_name="test.py"
        )
        envelope = json.loads(result)
        assert envelope["Success"] is True
        assert envelope["Data"]["Number"] == 42
        assert envelope["Error"] is None
        assert envelope["Metadata"]["Script"] == "test.py"
        assert envelope["Metadata"]["Timestamp"]

    def test_handles_null_data(self, capsys: pytest.CaptureFixture[str]) -> None:
        result = write_skill_output(None, output_format="json", script_name="test.py")
        envelope = json.loads(result)
        assert envelope["Success"] is True
        assert envelope["Data"] is None

    def test_handles_empty_dict_data(self, capsys: pytest.CaptureFixture[str]) -> None:
        result = write_skill_output({}, output_format="json", script_name="test.py")
        envelope = json.loads(result)
        assert envelope["Success"] is True
        assert envelope["Data"] == {}


class TestWriteSkillError:
    """Tests for write_skill_error function."""

    def test_produces_valid_error_envelope(self, capsys: pytest.CaptureFixture[str]) -> None:
        result = write_skill_error(
            "Not found",
            2,
            error_type="NotFound",
            output_format="json",
            script_name="test.py",
        )
        envelope = json.loads(result)
        assert envelope["Success"] is False
        assert envelope["Error"]["Message"] == "Not found"
        assert envelope["Error"]["Code"] == 2
        assert envelope["Error"]["Type"] == "NotFound"
        assert envelope["Metadata"]["Script"] == "test.py"

    def test_includes_extra_data(self, capsys: pytest.CaptureFixture[str]) -> None:
        result = write_skill_error(
            "API error",
            3,
            error_type="ApiError",
            output_format="json",
            script_name="test.py",
            extra={"Number": 99},
        )
        envelope = json.loads(result)
        assert envelope["Success"] is False
        assert envelope["Data"]["Number"] == 99

    @pytest.mark.parametrize(
        "error_type",
        ["NotFound", "ApiError", "AuthError", "InvalidParams", "Timeout", "General"],
    )
    def test_validates_error_types(
        self, error_type: str, capsys: pytest.CaptureFixture[str]
    ) -> None:
        result = write_skill_error(
            "test", 1, error_type=error_type, output_format="json", script_name="test.py"
        )
        envelope = json.loads(result)
        assert envelope["Error"]["Type"] == error_type

    def test_rejects_invalid_error_type(self) -> None:
        with pytest.raises(ValueError, match="error_type must be one of"):
            write_skill_error("test", 1, error_type="Invalid", output_format="json")


class TestValidateEnvelope:
    """Tests for validate_envelope function."""

    def test_valid_success_envelope(self) -> None:
        envelope = {
            "Success": True,
            "Data": {"Result": "ok"},
            "Error": None,
            "Metadata": {"Script": "test.py", "Timestamp": "2026-03-08T12:00:00Z"},
        }
        assert validate_envelope(envelope) == []

    def test_valid_error_envelope(self) -> None:
        envelope = {
            "Success": False,
            "Data": None,
            "Error": {"Message": "fail", "Code": 1, "Type": "General"},
            "Metadata": {"Script": "test.py", "Timestamp": "2026-03-08T12:00:00Z"},
        }
        assert validate_envelope(envelope) == []

    def test_missing_success_field(self) -> None:
        errors = validate_envelope({"Metadata": {"Script": "x", "Timestamp": "t"}})
        assert any("Missing required field: Success" in e for e in errors)

    def test_missing_metadata_field(self) -> None:
        errors = validate_envelope({"Success": True})
        assert any("Missing required field: Metadata" in e for e in errors)

    def test_invalid_error_type(self) -> None:
        envelope = {
            "Success": False,
            "Error": {"Message": "x", "Code": 1, "Type": "BadType"},
            "Metadata": {"Script": "x", "Timestamp": "t"},
        }
        errors = validate_envelope(envelope)
        assert any("not valid" in e for e in errors)

    def test_missing_error_when_success_false(self) -> None:
        envelope = {
            "Success": False,
            "Error": None,
            "Metadata": {"Script": "x", "Timestamp": "t"},
        }
        errors = validate_envelope(envelope)
        assert any("Error field is required" in e for e in errors)


class TestValidateSkillOutputScript:
    """Integration tests for validate_skill_output.py CLI."""

    def _run_validator(self, json_input: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(SCRIPTS_DIR / "validate_skill_output.py")],
            input=json_input,
            capture_output=True,
            text=True,
            timeout=30,
        )

    def test_validates_success_envelope(self) -> None:
        envelope = {
            "Success": True,
            "Data": {"Result": "ok"},
            "Error": None,
            "Metadata": {
                "Script": "test.py",
                "Version": "1.0.0",
                "Timestamp": "2026-03-08T12:00:00Z",
            },
        }
        result = self._run_validator(json.dumps(envelope))
        assert result.returncode == 0
        assert "PASS" in result.stdout

    def test_validates_error_envelope(self) -> None:
        envelope = {
            "Success": False,
            "Data": None,
            "Error": {"Message": "fail", "Code": 1, "Type": "General"},
            "Metadata": {
                "Script": "test.py",
                "Version": "1.0.0",
                "Timestamp": "2026-03-08T12:00:00Z",
            },
        }
        result = self._run_validator(json.dumps(envelope))
        assert result.returncode == 0

    def test_rejects_invalid_json(self) -> None:
        result = self._run_validator("not json")
        assert result.returncode == 1

    def test_rejects_path_traversal(self) -> None:
        traversal = str(REPO_ROOT / ".." / ".." / ".." / "etc" / "passwd")
        result = subprocess.run(
            [
                sys.executable,
                str(SCRIPTS_DIR / "validate_skill_output.py"),
                "--input-file",
                traversal,
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 1
        assert "Path traversal attempt detected" in result.stdout

    @pytest.mark.skipif(sys.platform == "win32", reason="Symlinks require privileges on Windows")
    def test_rejects_symlink_traversal(self, tmp_path: Path) -> None:
        # Create external file outside repo
        external_file = tmp_path / "external.json"
        external_file.write_text('{"Success": true}')

        # Create symlink inside repo pointing outside
        symlink_path = REPO_ROOT / f"test-symlink-{os.getpid()}.json"
        try:
            symlink_path.symlink_to(external_file)
            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPTS_DIR / "validate_skill_output.py"),
                    "--input-file",
                    str(symlink_path),
                ],
                capture_output=True,
                text=True,
                timeout=30,
            )
            assert result.returncode == 1
            assert "Path traversal attempt detected" in result.stdout
        finally:
            symlink_path.unlink(missing_ok=True)
