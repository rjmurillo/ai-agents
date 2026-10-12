"""Tests for write_skill_error's ADR-035 exit_code range guard (issue #5303).

ADR-035 allows 0-4 as standard codes, reserves 5-99, and sets 100+ for
script-specific codes. A process exit status is one byte, so 255 is the cap.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

# isort: skip_file
from scripts.github_core.output import write_skill_error  # noqa: E402
from scripts.validate_skill_output import validate_envelope  # noqa: E402

RANGE_MESSAGE = "exit_code must be 0-4"


class TestExitCodeRange:
    @pytest.mark.parametrize("exit_code", [0, 1, 2, 3, 4, 100, 101, 200, 255])
    def test_accepts_standard_and_script_specific_codes(
        self, exit_code: int, capsys: pytest.CaptureFixture[str]
    ) -> None:
        result = write_skill_error("test", exit_code, output_format="json", script_name="t.py")
        assert result is not None
        envelope = json.loads(result)
        assert envelope["Error"]["Code"] == exit_code
        assert validate_envelope(envelope) == []

    @pytest.mark.parametrize("exit_code", [5, 6, 7, 50, 98, 99])
    def test_rejects_reserved_band(
        self, exit_code: int, capsys: pytest.CaptureFixture[str]
    ) -> None:
        with pytest.raises(ValueError, match=RANGE_MESSAGE):
            write_skill_error("test", exit_code, output_format="json")
        assert capsys.readouterr().out == ""

    @pytest.mark.parametrize("exit_code", [-1, -100, 256, 1000])
    def test_rejects_values_outside_one_byte(
        self, exit_code: int, capsys: pytest.CaptureFixture[str]
    ) -> None:
        with pytest.raises(ValueError, match=RANGE_MESSAGE):
            write_skill_error("test", exit_code, output_format="json")
        assert capsys.readouterr().out == ""

    def test_error_message_names_the_offending_value(self) -> None:
        with pytest.raises(ValueError, match="got: 6"):
            write_skill_error("test", 6, output_format="json")

    def test_type_guard_still_runs_before_range_guard(self) -> None:
        with pytest.raises(ValueError, match="exit_code must be an integer"):
            write_skill_error("test", True, output_format="json")

    def test_human_format_also_rejects_reserved_code(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        with pytest.raises(ValueError, match=RANGE_MESSAGE):
            write_skill_error("test", 6, output_format="human")
        assert capsys.readouterr().out == ""
