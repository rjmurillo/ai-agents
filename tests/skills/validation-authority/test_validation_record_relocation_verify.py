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

_HERE = Path(__file__).resolve().parent
_SCRIPTS = _HERE.parents[2] / ".claude" / "skills" / "validation-authority" / "scripts"
sys.path.insert(0, str(_HERE))
sys.path.insert(0, str(_SCRIPTS))
import relocation_collector as collector_mod
from relocation_cli_fixtures import (
    PROJECT_ROOT,
    RECORD_SCRIPT,
    run_script,
    trigger_output,
    write_moved_modules,
)
from validation_record_fixtures import (
    make_record,
    make_relocation_target,
    mod,
    record_errors,
)

# Real collection reads this module itself, so a rename elsewhere cannot break it.
SELF_MODULE = Path(__file__).resolve().relative_to(PROJECT_ROOT).as_posix()


def _evidence(target: dict[str, Any]) -> dict[str, Any]:
    evidence: dict[str, Any] = target["relocation_evidence"]
    return evidence


def _errors(target: dict[str, Any], trigger: Any = None) -> list[str]:
    return record_errors(make_record(target, trigger=trigger))


def test_cli_fails_closed_when_real_collection_disagrees_with_the_claimed_ids(
    tmp_path: Path,
) -> None:
    """review-gates-03: the claimed ids are compared with what pytest really collects."""
    write_moved_modules(tmp_path, drop_param=True)
    path = "tests/validation/test_slow_part2.py"
    trigger = trigger_output(tmp_path, path)
    record = tmp_path / "record.json"
    record.write_text(json.dumps(make_record(make_relocation_target(), trigger=trigger)))
    result = run_script(
        RECORD_SCRIPT,
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


# Runs the record CLI with pytest hidden, the way an interpreter without it behaves.
_NO_PYTEST_LAUNCHER = (
    "import runpy, sys; sys.modules['pytest'] = None; "
    "sys.argv = sys.argv[1:]; runpy.run_path(sys.argv[0], run_name='__main__')"
)


def test_cli_exits_2_when_pytest_is_missing(tmp_path: Path) -> None:
    """A missing pytest is a config error (exit 2), not a record defect (exit 1)."""
    write_moved_modules(tmp_path)
    path = "tests/validation/test_slow_part2.py"
    trigger = trigger_output(tmp_path, path)
    record = tmp_path / "record.json"
    record.write_text(json.dumps(make_record(make_relocation_target(), trigger=trigger)))
    argv = ["--record", str(record), "--changed-path", path, "--repo-root", str(tmp_path)]
    result = subprocess.run(
        [sys.executable, "-c", _NO_PYTEST_LAUNCHER, str(RECORD_SCRIPT), *argv],
        cwd=tmp_path,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
        check=False,
    )
    assert result.returncode == 2, result.stdout + result.stderr
    assert "pytest is not installed" in result.stderr
    assert result.stdout == ""


def test_collect_tests_raises_pytest_unavailable_not_collection_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The missing-tool error must not be caught as a record defect."""
    real_find_spec = collector_mod.importlib.util.find_spec

    def find_spec(name: str, *args: Any) -> Any:
        return None if name == "pytest" else real_find_spec(name, *args)

    monkeypatch.setattr(collector_mod.importlib.util, "find_spec", find_spec)
    with pytest.raises(collector_mod.PytestUnavailableError, match="pytest is not installed"):
        collector_mod.collect_tests(["tests/validation/test_x.py"], PROJECT_ROOT)
    assert not issubclass(collector_mod.PytestUnavailableError, collector_mod.CollectionError)


def test_cli_fails_closed_when_the_moved_files_do_not_exist(tmp_path: Path) -> None:
    """A collect failure is a defect, never a silent pass."""
    path = "tests/validation/test_slow_part2.py"
    trigger = trigger_output(tmp_path, path)
    record = tmp_path / "record.json"
    record.write_text(json.dumps(make_record(make_relocation_target(), trigger=trigger)))
    result = run_script(
        RECORD_SCRIPT,
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
        raise collector_mod.CollectionError("pytest collection exited 2: boom")

    errors = _errors_with(boom)
    assert any(
        "could not be verified by real collection: pytest collection exited 2" in e for e in errors
    )


def test_collect_tests_reports_a_nonzero_exit_as_collection_error(tmp_path: Path) -> None:
    with pytest.raises(collector_mod.CollectionError, match="exited"):
        collector_mod.collect_tests(["tests/missing/test_none.py"], tmp_path)


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
    ids = collector_mod.collect_tests([SELF_MODULE], PROJECT_ROOT)
    assert ids
    assert all("::" in item for item in ids)


def test_collect_tests_ignores_an_inherited_pytest_addopts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """PYTEST_ADDOPTS=-v must not cancel -q and drop the node ids."""
    monkeypatch.setenv("PYTEST_ADDOPTS", "-v")
    ids = collector_mod.collect_tests([SELF_MODULE], PROJECT_ROOT)
    assert ids
    assert all("::" in item for item in ids)


def test_cli_passes_a_pure_move_from_the_real_repo_root(tmp_path: Path) -> None:
    """review-gates-03: end to end with --repo-root set to the real repository."""
    module = SELF_MODULE
    ids = collector_mod.collect_tests([module], PROJECT_ROOT)
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
    trigger = trigger_output(tmp_path, module)
    record = tmp_path / "record.json"
    record.write_text(json.dumps(make_record(target, trigger=trigger)))
    result = run_script(
        RECORD_SCRIPT,
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
