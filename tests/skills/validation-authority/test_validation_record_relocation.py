"""Tests for the relocation-no-semantic-change diagnosis (issue #6214).

A test-only move under ``tests/validation/`` activates the Phase 2b gate
through the ``validation-fixture`` cue but has no defect to diagnose. The
record accepts ``relocation-no-semantic-change`` only when the collected test
names and count match before and after, and only when the trigger declared no
semantic effect.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from validation_record_fixtures import (
    make_generated_target,
    make_record,
    make_relocation_target,
    make_target,
    mod,
    record_errors,
)

PROJECT_ROOT = Path(__file__).resolve().parents[3]
SKILLS_ROOT = PROJECT_ROOT / ".claude" / "skills"
_RECORD_SCRIPT = SKILLS_ROOT / "validation-authority" / "scripts" / "validation_record.py"
_TRIGGER_SCRIPT = SKILLS_ROOT / "build" / "scripts" / "validation_trigger.py"
_TIMEOUT_S = 60


def _evidence(target: dict[str, Any]) -> dict[str, Any]:
    evidence: dict[str, Any] = target["relocation_evidence"]
    return evidence


def _errors(target: dict[str, Any], trigger: Any = None) -> list[str]:
    return record_errors(make_record(target, trigger=trigger))


def test_relocation_is_a_known_diagnosis() -> None:
    assert "relocation-no-semantic-change" in mod.DIAGNOSES


def test_pure_move_with_equal_names_and_count_passes() -> None:
    assert _errors(make_relocation_target()) == []


def test_pure_move_ignores_the_module_path_but_not_the_class_or_param() -> None:
    target = make_relocation_target()
    _evidence(target)["tests_after"] = [
        "other/dir/test_z.py::TestB::test_b[x]",
        "other/dir/test_y.py::test_a",
    ]
    assert _errors(target) == []


def test_ids_without_a_separator_compare_whole() -> None:
    target = make_relocation_target()
    _evidence(target)["tests_before"] = ["test_a", "test_b"]
    _evidence(target)["tests_after"] = ["test_b", "test_a"]
    assert _errors(target) == []


def test_activated_trigger_with_no_effects_passes_for_a_pure_move() -> None:
    trigger = {
        "decision": "activate",
        "effects": [],
        "targets": [{"path": "tests/validation/test_slow_part2.py"}],
    }
    assert _errors(make_relocation_target(), trigger=trigger) == []


def test_dropped_test_fails_and_names_it() -> None:
    target = make_relocation_target()
    _evidence(target)["tests_after"] = _evidence(target)["tests_after"][:1]
    errors = _errors(target)
    assert any("changed the collected tests" in e and "lost 1: test_a" in e for e in errors)


def test_added_test_fails_and_names_it() -> None:
    target = make_relocation_target()
    _evidence(target)["tests_after"].append("tests/validation/test_new.py::test_extra")
    errors = _errors(target)
    assert any("gained 1: test_extra" in e and "3 after" in e for e in errors)


def test_renamed_test_fails_with_both_sides_named() -> None:
    target = make_relocation_target()
    _evidence(target)["tests_after"][1] = "tests/validation/test_slow_part1.py::test_renamed"
    errors = _errors(target)
    assert any("lost 1: test_a" in e and "gained 1: test_renamed" in e for e in errors)


def test_duplicate_name_dropped_changes_the_count() -> None:
    target = make_relocation_target()
    _evidence(target)["tests_before"].append("tests/validation/test_other.py::test_a")
    errors = _errors(target)
    assert any("lost 1: test_a" in e for e in errors)


def test_diff_listing_is_capped() -> None:
    target = make_relocation_target()
    _evidence(target)["tests_before"] = [f"t.py::test_{n}" for n in range(12)]
    _evidence(target)["tests_after"] = ["t.py::test_0"]
    errors = _errors(target)
    assert any("lost 11:" in e and e.count("test_") == mod._RELOCATION_DIFF_LIMIT for e in errors)


def test_missing_evidence_fails() -> None:
    target = make_relocation_target()
    del target["relocation_evidence"]
    assert any("needs a `relocation_evidence` object" in e for e in _errors(target))


def test_evidence_must_be_an_object() -> None:
    target = make_relocation_target()
    target["relocation_evidence"] = ["a"]
    assert any("needs a `relocation_evidence` object" in e for e in _errors(target))


@pytest.mark.parametrize("command", ["", "   ", None, 3])
def test_collect_command_must_be_non_empty_text(command: Any) -> None:
    target = make_relocation_target()
    _evidence(target)["collect_command"] = command
    assert any("collect_command must be a non-empty string" in e for e in _errors(target))


@pytest.mark.parametrize("key", ["tests_before", "tests_after"])
@pytest.mark.parametrize("value", [None, "test_a", [], {}])
def test_test_lists_must_be_non_empty_lists(key: str, value: Any) -> None:
    target = make_relocation_target()
    _evidence(target)[key] = value
    assert any(f"{key} must be a non-empty list" in e for e in _errors(target))


@pytest.mark.parametrize("key", ["tests_before", "tests_after"])
@pytest.mark.parametrize("bad", ["", "  ", 7, None])
def test_test_lists_reject_blank_or_non_string_ids(key: str, bad: Any) -> None:
    target = make_relocation_target()
    _evidence(target)[key] = [*_evidence(target)[key], bad]
    assert any(f"{key} must contain only non-empty strings" in e for e in _errors(target))


def test_declared_semantic_effect_forces_a_defect_diagnosis() -> None:
    trigger = {
        "decision": "activate",
        "effects": ["fixture-redefines-case"],
        "targets": [{"path": "tests/validation/test_slow_part2.py"}],
    }
    errors = _errors(make_relocation_target(), trigger=trigger)
    assert any("contradicts trigger effects (fixture-redefines-case)" in e for e in errors)


def test_declared_effect_is_fine_when_the_diagnosis_is_a_defect() -> None:
    trigger = {
        "decision": "activate",
        "effects": ["fixture-redefines-case"],
        "targets": [{"path": "tests/validation/test_slow_part2.py"}],
    }
    target = make_target(target="tests/validation/test_slow_part2.py")
    assert _errors(target, trigger=trigger) == []


def test_effect_check_ignores_a_non_object_trigger() -> None:
    assert mod._relocation_effect_defects("nope", [make_relocation_target()]) == []


def test_effect_check_skips_malformed_targets() -> None:
    trigger = {"effects": ["severity-change"]}
    malformed = ["x", {"authority": "y"}, make_target()]
    assert mod._relocation_effect_defects(trigger, malformed) == []


@pytest.mark.parametrize("category", ["GENERATED", "VENDOR", "UPSTREAM"])
def test_relocation_requires_local_provenance(category: str) -> None:
    target = make_relocation_target(provenance={"category": category, "canonical_source": "c"})
    errors = _errors(target)
    assert any("applies only to LOCAL provenance" in e for e in errors)


@pytest.mark.parametrize(
    "path",
    [
        "scripts/validation/check_x.py",
        "src/tests/validation/x.py",
        "ruff.toml",
        "tests/../scripts/validation/check_x.py",
        "tests/validation/../../ruff.toml",
    ],
)
def test_relocation_requires_a_target_under_tests(path: str) -> None:
    target = make_relocation_target(target=path, authority={"permitted_change_location": path})
    assert any("applies only to a target under tests/" in e for e in _errors(target))


def test_relocation_target_path_spelling_is_normalized() -> None:
    target = make_relocation_target(target=".\\tests\\validation\\test_slow_part2.py")
    assert _errors(target) == []


def test_other_targets_in_the_record_keep_their_own_rules() -> None:
    record = make_record(make_relocation_target(), make_generated_target())
    assert record_errors(record) == []


def _run(script: Path, cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(script), *args],
        cwd=cwd,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        timeout=_TIMEOUT_S,
        check=False,
    )


def _trigger_output(cwd: Path, path: str, *effects: str) -> dict[str, Any]:
    args = ["--repo-root", str(PROJECT_ROOT), "--changed-path", path]
    for effect in effects:
        args += ["--effect", effect]
    result = _run(_TRIGGER_SCRIPT, cwd, *args)
    assert result.returncode == 0, result.stderr
    output: dict[str, Any] = json.loads(result.stdout)
    return output


def test_real_trigger_then_record_cli_passes_for_a_pure_move(tmp_path: Path) -> None:
    """End to end: the trigger activates on the move, and the record clears it."""
    path = "tests/validation/test_slow_part2.py"
    trigger = _trigger_output(tmp_path, path)
    assert trigger["decision"] == "activate"
    assert trigger["effects"] == []
    record = tmp_path / "record.json"
    record.write_text(json.dumps(make_record(make_relocation_target(), trigger=trigger)))
    result = _run(
        _RECORD_SCRIPT,
        tmp_path,
        "--record",
        str(record),
        "--changed-path",
        path,
        "--repo-root",
        str(PROJECT_ROOT),
    )
    assert result.returncode == 0, result.stdout
    assert json.loads(result.stdout)["ok"] is True


def test_real_trigger_then_record_cli_fails_when_an_assertion_changed(tmp_path: Path) -> None:
    """A move that also redefines a case declares the effect, so relocation is refused."""
    path = "tests/validation/test_slow_part2.py"
    trigger = _trigger_output(tmp_path, path, "fixture-redefines-case")
    record = tmp_path / "record.json"
    record.write_text(json.dumps(make_record(make_relocation_target(), trigger=trigger)))
    result = _run(
        _RECORD_SCRIPT,
        tmp_path,
        "--record",
        str(record),
        "--changed-path",
        path,
        "--repo-root",
        str(PROJECT_ROOT),
    )
    assert result.returncode == 1
    assert "contradicts trigger effects" in result.stdout
