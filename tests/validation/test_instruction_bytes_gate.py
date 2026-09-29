"""The pre-PR gate wrapper for instruction_bytes (issue #5400)."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

_VALIDATION = Path(__file__).resolve().parents[2] / "scripts" / "validation"
if str(_VALIDATION) not in sys.path:
    sys.path.insert(0, str(_VALIDATION))

import checks_common
import checks_tooling


def _repo(root: Path, *, module: bool = True, templates: bool = True) -> Path:
    if module:
        (root / "scripts" / "validation").mkdir(parents=True)
        (root / "scripts" / "validation" / "instruction_bytes.py").write_text(
            "# stub\n", encoding="utf-8"
        )
    if templates:
        (root / "templates").mkdir()
    return root


class TestValidateInstructionBytes:
    def test_passes_when_the_command_exits_zero(self, tmp_path: Path) -> None:
        with patch("checks_tooling._run_subprocess", return_value=(0, "ok\n", "")) as run:
            assert checks_tooling.validate_instruction_bytes(_repo(tmp_path)) is True
        argv = run.call_args.args[0]
        assert argv[1:3] == ["-m", "scripts.validation.instruction_bytes"]
        assert "--ci" in argv
        assert argv[argv.index("--path") + 1] == str(tmp_path)

    def test_fails_and_echoes_output_when_a_ceiling_is_exceeded(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        with patch("checks_tooling._run_subprocess", return_value=(1, "F1 over\n", "")):
            assert checks_tooling.validate_instruction_bytes(_repo(tmp_path)) is False
        assert "F1 over" in capsys.readouterr().out

    def test_fails_on_a_configuration_error_and_echoes_stderr(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        with patch("checks_tooling._run_subprocess", return_value=(2, "", "Error: bad tree\n")):
            assert checks_tooling.validate_instruction_bytes(_repo(tmp_path)) is False
        assert "Error: bad tree" in capsys.readouterr().err

    def test_skips_when_the_module_is_absent(self, tmp_path: Path) -> None:
        with pytest.raises(checks_common.MissingScriptSkip):
            checks_tooling.validate_instruction_bytes(_repo(tmp_path, module=False))

    def test_skips_when_the_templates_tree_is_absent(self, tmp_path: Path) -> None:
        with pytest.raises(checks_common.MissingScriptSkip):
            checks_tooling.validate_instruction_bytes(_repo(tmp_path, templates=False))
