"""Ratchet-down guards for the mypy half of the baseline in pyproject.toml.

``strict = true`` landed with a baseline, so modules that failed it on main
still pass. The baseline must only shrink: every module an override names must
still exist, an override block the classifier cannot place raises instead of
being skipped, and the name count is pinned, so adding one fails until a
reviewer sees the constant move. The C901 half lives in
``tests/test_strict_baselines.py``.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import pytest

from scripts.validation import git_hook_policy as policy
from tests.strict_baseline_helpers import (
    EXPECTED_STRICT_BASELINE_MODULE_NAMES,
    _gate_module_names,
    _load_pyproject,
    _mypy_overrides,
    _tracked_python_files,
    strict_baseline_module_lists,
    strict_baseline_modules,
    unclassified_override_blocks,
    unknown_modules,
)


def test_strict_baseline_module_name_count_matches_the_pinned_constant() -> None:
    modules = strict_baseline_modules(_load_pyproject())

    assert len(modules) == EXPECTED_STRICT_BASELINE_MODULE_NAMES, (
        f"the mypy overrides list {len(modules)} strict-baseline module names, pinned at "
        f"{EXPECTED_STRICT_BASELINE_MODULE_NAMES}. Lower the constant when you fix a "
        "module; never raise it. New code must satisfy strict, not join the baseline."
    )


def test_no_unclassified_mypy_override_block() -> None:
    unclassified = unclassified_override_blocks(_load_pyproject())

    assert unclassified == [], (
        "these override blocks are neither a strict-baseline block nor a known shape, "
        f"so no test can tell whether their modules belong in the baseline: {unclassified}. "
        "Register the shape in KNOWN_NON_BASELINE_OVERRIDES, or make it a baseline block."
    )


def test_mypy_test_path_flags_mirror_the_tests_override_settings() -> None:
    override = next(
        block for block in _mypy_overrides(_load_pyproject()) if block.get("module") == "tests.*"
    )
    # The path flags exist because a tests/ directory with no __init__.py gives its
    # files top-level names "tests.*" cannot match, so each flag mirrors one
    # annotation setting the override turns off.
    mirrored = {
        "--allow-untyped-defs": "disallow_untyped_defs",
        "--allow-incomplete-defs": "disallow_incomplete_defs",
        "--allow-untyped-calls": "disallow_untyped_calls",
        "--no-check-untyped-defs": "check_untyped_defs",
    }

    assert set(policy.MYPY_TEST_PATH_FLAGS) == set(mirrored), (
        "MYPY_TEST_PATH_FLAGS and this mapping disagree; update both together. Flags: "
        f"{sorted(policy.MYPY_TEST_PATH_FLAGS)}"
    )
    off = {setting: override.get(setting) for setting in mirrored.values()}
    assert off == dict.fromkeys(mirrored.values(), False), (
        f"the tests.* override must turn off all four annotation settings it mirrors; {off}"
    )


def test_strict_baseline_modules_still_exist() -> None:
    modules = strict_baseline_modules(_load_pyproject())
    known = _gate_module_names(_tracked_python_files())

    missing = unknown_modules(modules, known)

    assert modules, "no strict-baseline mypy overrides were found"
    assert missing == [], (
        f"{len(missing)} of {len(set(modules))} strict-baseline modules no longer "
        f"exist; delete them from the mypy overrides: {missing}"
    )


def test_strict_baseline_module_lists_are_sorted_and_unique() -> None:
    lists = strict_baseline_module_lists(_load_pyproject())

    assert lists
    assert [names for names in lists if names != sorted(set(names))] == []


def test_strict_baseline_modules_selects_only_strict_relax_overrides() -> None:
    pyproject = _with_overrides(
        {"module": ["pkg.a", "pkg.b"], "implicit_reexport": True},
        {"module": ["pkg.c"], "disable_error_code": ["redundant-cast"]},
        {"module": ["pkg.e"], "disallow_any_generics": False},
        {"module": ["pkg.g"]},
    )

    assert strict_baseline_modules(pyproject) == ["pkg.a", "pkg.b", "pkg.c"]


def _with_overrides(*overrides: Mapping[str, Any]) -> dict[str, Any]:
    """A pyproject shaped mapping holding exactly ``overrides``."""
    return {"tool": {"mypy": {"overrides": list(overrides)}}}


def test_unclassified_override_block_fails_closed() -> None:
    pyproject = _with_overrides(
        {"module": ["pkg.a"], "implicit_reexport": True},
        {"module": ["pkg.d"], "disable_error_code": ["arg-type"]},
        {"module": ["pkg.e"], "disable_error_code": ["not-a-real-code"]},
        {"module": ["pkg.f"], "implicit_reexport": False},
    )

    assert [block.get("module") for block in unclassified_override_blocks(pyproject)] == [
        ["pkg.e"],
        ["pkg.f"],
    ]
    with pytest.raises(ValueError, match="neither a strict-baseline block"):
        strict_baseline_module_lists(pyproject)


def test_disable_error_code_block_counts_as_a_baseline_entry() -> None:
    """A module relaxing only named error codes is a baseline entry like any other.

    Counting it keeps the shrink-only rule and the pinned length honest: add a
    module here and the length test fails.
    """
    pyproject = _with_overrides({"module": ["pkg.d"], "disable_error_code": ["arg-type"]})

    assert strict_baseline_modules(pyproject) == ["pkg.d"]


def test_disable_error_code_with_an_unknown_code_is_unclassified() -> None:
    pyproject = _with_overrides({"module": ["pkg.e"], "disable_error_code": ["not-a-real-code"]})

    assert [block.get("module") for block in unclassified_override_blocks(pyproject)] == [["pkg.e"]]


def test_disable_error_code_mixed_with_another_setting_is_unclassified() -> None:
    """Only a lone disable_error_code key is a baseline relaxation."""
    pyproject = _with_overrides(
        {"module": ["pkg.g"], "disable_error_code": ["arg-type"], "implicit_reexport": True}
    )

    assert [block.get("module") for block in unclassified_override_blocks(pyproject)] == [["pkg.g"]]


def test_known_non_baseline_and_empty_blocks_are_not_unclassified() -> None:
    pyproject = _with_overrides(
        {"module": "semantic_hooks.*", "disallow_any_generics": False},
        {"module": ["pkg.a"], "ignore_missing_imports": True},
        {"module": ["pkg.b"]},
    )

    assert unclassified_override_blocks(pyproject) == []
    assert strict_baseline_modules(pyproject) == []


def test_strict_baseline_modules_empty_without_mypy_config() -> None:
    assert strict_baseline_modules({}) == []


def test_unknown_modules_flags_only_missing_names() -> None:
    assert unknown_modules(["a", "b", "b", "c"], ["a", "c"]) == ["b"]
    assert unknown_modules([], ["a"]) == []


def test_gate_module_names_include_package_and_bare_validation_names() -> None:
    names = _gate_module_names(
        ["scripts/validation/git_hook_policy.py", "tests/test_strict_baselines.py"]
    )

    assert {
        "scripts.validation.git_hook_policy",
        "git_hook_policy",
        "tests.test_strict_baselines",
    } <= names
