"""Verification tests for relocation evidence and trigger recomputation (issue #6506).

Covers review-gates-03 (real collection), -04 (trigger recomputation), and -05
(path rules on every moved_from and moved_to entry).
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import relocation_evidence as reloc
from validation_record_fixtures import (
    make_record,
    make_relocation_target,
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


def _write_moved_modules(root: Path, *, drop_param: bool = False) -> None:
    """Write the two destination modules that make_relocation_target() describes."""
    tests = root / "tests" / "validation"
    tests.mkdir(parents=True)
    (tests / "test_slow_part1.py").write_text("def test_a():\n    pass\n", encoding="utf-8")
    params = '"y"' if drop_param else '"x"'
    (tests / "test_slow_part2.py").write_text(
        "import pytest\n\n\nclass TestB:\n"
        f"    @pytest.mark.parametrize('v', [{params}])\n"
        "    def test_b(self, v):\n        pass\n",
        encoding="utf-8",
    )


def test_cli_fails_closed_when_real_collection_disagrees_with_the_claimed_ids(
    tmp_path: Path,
) -> None:
    """review-gates-03: the claimed ids are compared with what pytest really collects."""
    _write_moved_modules(tmp_path, drop_param=True)
    path = "tests/validation/test_slow_part2.py"
    trigger = _trigger_output(tmp_path, path)
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
        str(tmp_path),
    )
    assert result.returncode == 1
    assert "does not match real collection" in result.stdout


def test_cli_fails_closed_when_the_moved_files_do_not_exist(tmp_path: Path) -> None:
    """A collect failure is a defect, never a silent pass."""
    path = "tests/validation/test_slow_part2.py"
    trigger = _trigger_output(tmp_path, path)
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
        str(tmp_path),
    )
    assert result.returncode == 1
    assert "could not be verified by real collection" in result.stdout


def _errors_with(collector: Any) -> list[str]:
    errors: list[str] = mod.validate(make_record(make_relocation_target()), collector=collector)
    return errors


def test_collector_matching_the_claim_passes_and_receives_the_moved_to_paths() -> None:
    seen: list[list[str]] = []

    def collector(paths: Any) -> list[str]:
        seen.append(list(paths))
        return list(_evidence(make_relocation_target())["tests_after"])

    assert _errors_with(collector) == []
    assert seen == [["tests/validation/test_slow_part1.py", "tests/validation/test_slow_part2.py"]]


def test_collector_returning_extra_tests_fails() -> None:
    extra = [*_evidence(make_relocation_target())["tests_after"], "tests/x/test_n.py::test_new"]
    errors = _errors_with(lambda paths: extra)
    assert any("does not match real collection" in e and "gained 1" in e for e in errors)


def test_collector_returning_nothing_fails() -> None:
    errors = _errors_with(lambda paths: [])
    assert any("found no tests" in e for e in errors)


def test_collector_error_is_a_defect() -> None:
    def boom(paths: Any) -> list[str]:
        raise reloc.CollectionError("pytest collection exited 2: boom")

    errors = _errors_with(boom)
    assert any(
        "could not be verified by real collection: pytest collection exited 2" in e for e in errors
    )


def test_collect_tests_reports_a_nonzero_exit_as_collection_error(tmp_path: Path) -> None:
    with pytest.raises(reloc.CollectionError, match="exited"):
        reloc.collect_tests(["tests/missing/test_none.py"], tmp_path)


def test_moved_from_must_sit_under_tests_with_no_parent_segments() -> None:
    """review-gates-05: every moved_from path gets the target's path rules."""
    for bad in ("src/app/test_slow.py", "tests/../src/test_slow.py", "/etc/test_slow.py"):
        target = make_relocation_target()
        _evidence(target)["moved_from"] = [bad]
        _evidence(target)["tests_before"] = [f"{bad}::test_a", f"{bad}::TestB::test_b[x]"]
        errors = _errors(target)
        assert any("moved_from path under tests/" in e for e in errors), bad


def test_moved_from_must_name_a_test_module() -> None:
    target = make_relocation_target()
    _evidence(target)["moved_from"] = ["tests/validation/conftest.py"]
    _evidence(target)["tests_before"] = [
        "tests/validation/conftest.py::test_a",
        "tests/validation/conftest.py::TestB::test_b[x]",
    ]
    assert any("moved_from path" in e and "test module" in e for e in _errors(target))


def test_moved_to_gets_the_same_path_rules() -> None:
    target = make_relocation_target()
    _evidence(target)["moved_to"] = [*_evidence(target)["moved_to"], "tests/../evil/test_x.py"]
    assert any("moved_to path under tests/" in e for e in _errors(target))


def test_one_bad_moved_from_among_good_ones_still_fails() -> None:
    target = make_relocation_target()
    _evidence(target)["moved_from"] = ["tests/validation/test_slow.py", "scripts/test_other.py"]
    assert any("moved_from path under tests/" in e for e in _errors(target))


def test_activated_trigger_without_an_effects_key_fails_closed() -> None:
    """review-gates-04: omitting effects must not skip the relocation-vs-effect check."""
    errors = _errors(make_relocation_target(), trigger={"decision": "activate"})
    assert any("trigger.effects is missing" in e for e in errors)


def test_record_trigger_skip_is_overridden_by_recomputing_from_changed_paths() -> None:
    """A record that says skip cannot hide a validator path the real trigger flags."""
    trigger_mod = mod.load_trigger()
    record = make_record(make_relocation_target(), trigger={"decision": "skip"})
    errors = record_errors(
        record,
        changed_paths=("scripts/validation/check_x.py",),
        repo_root=PROJECT_ROOT,
        trigger_module=trigger_mod,
    )
    assert any("trigger.decision is `skip` but the trigger recomputed" in e for e in errors)


def test_recomputed_trigger_agreeing_with_the_record_adds_no_defect() -> None:
    trigger_mod = mod.load_trigger()
    path = "tests/validation/test_slow_part2.py"
    record = make_record(make_relocation_target())
    errors = record_errors(
        record, changed_paths=(path,), repo_root=PROJECT_ROOT, trigger_module=trigger_mod
    )
    assert not any("recomputed" in e for e in errors)


def test_recomputed_trigger_refusal_is_reported(tmp_path: Path) -> None:
    trigger_mod = mod.load_trigger()
    record = make_record(
        make_relocation_target(), trigger={"decision": "activate", "effects": ["bogus-effect"]}
    )
    errors = record_errors(
        record, changed_paths=("tests/a.py",), repo_root=tmp_path, trigger_module=trigger_mod
    )
    assert any("refused: unknown effect: bogus-effect" in e for e in errors)


def test_collect_tests_yields_ids_from_the_real_repo_root_despite_addopts() -> None:
    """review-gates-03: repo addopts (-v) must not turn the id list into a tree."""
    ids = reloc.collect_tests(
        ["tests/validation/test_check_memory_placement_growth.py"], PROJECT_ROOT
    )
    assert ids
    assert all("::" in item for item in ids)


def test_collect_tests_ignores_an_inherited_pytest_addopts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """PYTEST_ADDOPTS=-v must not cancel -q and drop the node ids."""
    monkeypatch.setenv("PYTEST_ADDOPTS", "-v")
    ids = reloc.collect_tests(
        ["tests/validation/test_check_memory_placement_growth.py"], PROJECT_ROOT
    )
    assert ids
    assert all("::" in item for item in ids)


def test_cli_passes_a_pure_move_from_the_real_repo_root(tmp_path: Path) -> None:
    """review-gates-03: end to end with --repo-root set to the real repository."""
    module = "tests/validation/test_check_memory_placement_growth.py"
    ids = reloc.collect_tests([module], PROJECT_ROOT)
    target = make_relocation_target(
        target=module,
        authority={
            "diagnosis": "relocation-no-semantic-change",
            "permitted_change_location": module,
        },
    )
    target["relocation_evidence"].update(
        {"moved_from": ["tests/validation/test_old_home.py"], "moved_to": [module]}
    )
    old = "tests/validation/test_old_home.py"
    target["relocation_evidence"]["tests_before"] = [item.replace(module, old, 1) for item in ids]
    target["relocation_evidence"]["tests_after"] = list(ids)
    trigger = _trigger_output(tmp_path, module)
    record = tmp_path / "record.json"
    record.write_text(json.dumps(make_record(target, trigger=trigger)))
    result = _run(
        _RECORD_SCRIPT,
        tmp_path,
        "--record",
        str(record),
        "--changed-path",
        module,
        "--repo-root",
        str(PROJECT_ROOT),
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_collector_is_not_called_when_a_moved_to_path_fails_the_scope_rule() -> None:
    """review-gates-05: an unvetted record path must never reach pytest."""
    calls: list[Any] = []

    def collector(paths: Any) -> list[str]:
        calls.append(list(paths))
        return []

    target = make_relocation_target()
    target["relocation_evidence"]["moved_to"] = ["tests/../../outside/test_evil.py"]
    errors = mod.validate(make_record(target), collector=collector)
    assert calls == []
    assert any(".." in error for error in errors)
