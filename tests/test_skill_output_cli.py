"""Integration tests for the validate_skill_output.py CLI subprocess.

Split from test_skill_output.py (issue: file exceeded the 500-line taste-lint
gate) once the Copilot review on PR #5283, commit 6639555b8, added several
CLI-level regression cases alongside the existing path-traversal coverage.
Covers the same schema/ADR-056/ADR-103 contract as
test_validate_envelope.py's TestValidateEnvelope (that class itself moved
out of test_skill_output.py in ADR-103 Round 5, after this file's initial
split; corrected here per a later Copilot review), but end to end through
the real `python3 validate_skill_output.py` subprocess rather than calling
`validate_envelope` in-process, so a defect in argument parsing,
stdin/file reading, or exit-code plumbing is caught even when the
underlying function is correct.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = REPO_ROOT / "scripts"


class TestValidateSkillOutputScript:
    """Integration tests for validate_skill_output.py CLI."""

    def _run_validator(self, json_input: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(SCRIPTS_DIR / "validate_skill_output.py")],
            input=json_input,
            capture_output=True,
            text=True, encoding="utf-8",
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

    @pytest.mark.parametrize("valid_json_non_object", ["null", "1", '"a string"', "[1, 2]"])
    def test_rejects_non_object_valid_json_without_crashing(
        self, valid_json_non_object: str
    ) -> None:
        """Valid JSON that is not an object (null, a number, a string, an
        array) must exit 1 with a validation finding, not crash the CLI
        with an unhandled traceback. Exercises the same gap as
        test_validate_envelope.py's
        TestValidateEnvelope.test_non_dict_top_level_is_rejected_without_crashing
        end to end through the actual subprocess (Copilot review on
        PR #5283, commit 6639555b8).
        """
        result = self._run_validator(valid_json_non_object)
        assert result.returncode == 1
        assert "Envelope must be a JSON object" in result.stdout

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
            text=True, encoding="utf-8",
            timeout=30,
        )
        assert result.returncode == 1
        assert "Path traversal attempt detected" in result.stdout

    @pytest.mark.skipif(sys.platform == "win32", reason="Symlinks require privileges on Windows")
    def test_rejects_symlink_traversal(self, external_tmp_path: Path) -> None:
        # Create external file outside repo
        external_file = external_tmp_path / "external.json"
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
                text=True, encoding="utf-8",
                timeout=30,
            )
            assert result.returncode == 1
            assert "Path traversal attempt detected" in result.stdout
        finally:
            symlink_path.unlink(missing_ok=True)
