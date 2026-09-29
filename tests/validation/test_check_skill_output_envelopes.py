"""Tests for the skill-output envelope gate (issue #5299).

The gate builds envelopes with the real producers and asks the ADR-056/ADR-103
validator to accept them, then proves the validator still rejects a malformed
one. Each test below breaks one half and asserts the gate goes red for it.
"""

from __future__ import annotations

import io
import json
import sys
from contextlib import redirect_stdout
from pathlib import Path
from types import ModuleType

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
_VALIDATION_DIR = REPO_ROOT / "scripts" / "validation"
if str(_VALIDATION_DIR) not in sys.path:
    sys.path.insert(0, str(_VALIDATION_DIR))
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import check_skill_output_envelopes as gate
import pre_pr_sequence
from checks_common import MissingScriptSkip

from scripts import validate_skill_output as real_validator
from scripts.github_core import output as real_producer


def _producer_with(**overrides: object) -> ModuleType:
    module = ModuleType("fake_producer")
    for name in ("VALID_ERROR_TYPES", "write_skill_output", "write_skill_error"):
        setattr(module, name, getattr(real_producer, name))
    for name, value in overrides.items():
        setattr(module, name, value)
    return module


def test_real_producers_and_validator_agree() -> None:
    assert gate.find_problems(REPO_ROOT, real_producer, real_validator) == []


def test_every_validator_error_type_is_exercised_with_and_without_extra() -> None:
    labels = [
        label for label, _ in gate.build_envelopes(real_producer, real_validator.VALID_ERROR_TYPES)
    ]
    assert "success" in labels
    for error_type in real_validator.VALID_ERROR_TYPES:
        assert f"error:{error_type}" in labels
        assert f"error:{error_type}:extra" in labels


def test_a_producer_that_drops_error_type_is_reported() -> None:
    def broken(message: str, exit_code: int, **kwargs: object) -> None:
        envelope = {
            "Success": False,
            "Data": None,
            "Error": {"Message": message, "Code": exit_code},
            "Metadata": {"Script": "x", "Version": "1", "Timestamp": "2026-01-01T00:00:00Z"},
        }
        print(json.dumps(envelope))

    problems = gate.find_problems(
        REPO_ROOT, _producer_with(write_skill_error=broken), real_validator
    )
    assert any(problem.startswith("error:General") for problem in problems)


def test_a_producer_that_drops_the_data_key_is_reported() -> None:
    def broken(data: object, **kwargs: object) -> None:
        print(json.dumps({"Success": True, "Error": None, "Metadata": {}}))

    problems = gate.find_problems(
        REPO_ROOT, _producer_with(write_skill_output=broken), real_validator
    )
    assert any(problem.startswith("success:") for problem in problems)


def test_a_producer_error_type_the_validator_rejects_is_reported() -> None:
    producer = _producer_with(
        VALID_ERROR_TYPES=frozenset({*real_producer.VALID_ERROR_TYPES, "Novel"})
    )
    problems = gate.find_problems(REPO_ROOT, producer, real_validator)
    assert any("Novel" in problem for problem in problems)


def test_a_validator_that_accepts_everything_is_caught_by_the_negative_control(
    tmp_path: Path,
) -> None:
    """A gate that cannot go red reports PASS forever; the CLI half guards that."""
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "validate_skill_output.py").write_text(
        "import sys\nsys.exit(0)\n", encoding="utf-8"
    )
    problems = gate.find_problems(tmp_path, real_producer, real_validator)
    assert "validator CLI did not reject an error envelope with no Error.Type" in problems


def test_a_validator_that_crashes_does_not_pass_the_negative_control(tmp_path: Path) -> None:
    """A non-zero exit that is not the validation-failure exit is not a rejection."""
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "validate_skill_output.py").write_text(
        "import sys\nsys.exit(2)\n", encoding="utf-8"
    )
    problems = gate.find_problems(tmp_path, real_producer, real_validator)
    assert "validator CLI did not reject an error envelope with no Error.Type" in problems


def test_a_validator_that_rejects_for_another_reason_does_not_pass(tmp_path: Path) -> None:
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "validate_skill_output.py").write_text(
        "import sys\nprint('[FAIL] Invalid JSON')\nsys.exit(1)\n", encoding="utf-8"
    )
    problems = gate.find_problems(tmp_path, real_producer, real_validator)
    assert "validator CLI did not reject an error envelope with no Error.Type" in problems


def test_a_producer_that_prints_nothing_is_reported() -> None:
    """Consumers read stdout, so a producer that only returns JSON is broken."""

    def silent(*_args: object, **_kwargs: object) -> str:
        return "{}"

    problems = gate.find_problems(
        REPO_ROOT,
        _producer_with(write_skill_output=silent, write_skill_error=silent),
        real_validator,
    )
    assert any("producer stdout is not one JSON envelope" in problem for problem in problems)


def test_load_ignores_modules_cached_from_another_checkout(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    foreign = ModuleType("scripts.github_core.output")
    foreign.__file__ = str(tmp_path / "elsewhere" / "output.py")
    monkeypatch.setitem(sys.modules, "scripts.github_core.output", foreign)
    producer, _validator = gate._load(REPO_ROOT)
    assert producer is not foreign
    assert Path(str(producer.__file__)).resolve().is_relative_to(REPO_ROOT)


def test_the_wrapper_skips_when_the_validator_is_absent(tmp_path: Path) -> None:
    with pytest.raises(MissingScriptSkip):
        gate.validate_skill_output_envelopes(tmp_path)


def test_the_wrapper_passes_on_this_repository() -> None:
    with redirect_stdout(io.StringIO()):
        assert gate.validate_skill_output_envelopes(REPO_ROOT) is True


def test_the_wrapper_prints_a_finding_and_returns_false(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        gate, "find_problems", lambda *_args: ["success: Missing required field: Data"]
    )
    with redirect_stdout(io.StringIO()) as captured:
        assert gate.validate_skill_output_envelopes(REPO_ROOT) is False
    assert (
        "[FAIL] skill output envelope: success: Missing required field: Data" in captured.getvalue()
    )


def test_the_gate_is_in_the_pre_pr_sequence_and_runs_in_quick_mode() -> None:
    gates = {row.name: row for row in pre_pr_sequence._SEQUENCE}
    assert "Skill Output Envelope" in gates
    assert not gates["Skill Output Envelope"].skip_when_quick


def test_main_returns_zero_on_this_repository(capsys: pytest.CaptureFixture[str]) -> None:
    assert gate.main(["--repo-root", str(REPO_ROOT)]) == 0
    assert "[PASS]" in capsys.readouterr().out


def test_main_returns_one_and_names_the_problem(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(gate, "find_problems", lambda *_args: ["error:General: nope"])
    assert gate.main(["--repo-root", str(REPO_ROOT)]) == 1
    assert "[FAIL] error:General: nope" in capsys.readouterr().out


def test_main_returns_two_for_a_missing_repo_root(tmp_path: Path) -> None:
    assert gate.main(["--repo-root", str(tmp_path / "absent")]) == 2


def test_main_returns_two_when_a_required_module_cannot_be_imported(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    def refuse(_root: Path) -> tuple[ModuleType, ModuleType]:
        raise ImportError("no module")

    monkeypatch.setattr(gate, "_load", refuse)
    assert gate.main(["--repo-root", str(tmp_path)]) == 2


def test_the_script_runs_standalone_and_exits_zero() -> None:
    import subprocess

    result = subprocess.run(
        [sys.executable, str(_VALIDATION_DIR / "check_skill_output_envelopes.py")],
        capture_output=True,
        encoding="utf-8",
        cwd=REPO_ROOT,
        timeout=60,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "[PASS]" in result.stdout
