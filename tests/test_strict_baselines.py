"""Ratchet-down guards for the strict mypy and C901 baselines in pyproject.toml.

``strict = true`` and ruff's C90 rule landed with a baseline, so code that
failed them on main still passes. The baseline must only shrink:

1. ``[tool.ruff.lint.extend-per-file-ignores]`` holds only the C901 baseline.
   Every entry must name one tracked file that still has a C901 violation. A
   fixed or deleted file leaves a stale entry, and that entry would silently
   waive the rule for new code in the file.
2. The "Strict-mode baseline" mypy overrides relax one strict check each. Every
   module they list must still exist, so a renamed or deleted module cannot
   leave a dead entry behind. An override block the classifier cannot place
   raises instead of being skipped, so a block relaxing a setting the baseline
   vocabulary does not name cannot escape both checks.
3. Both baseline sizes are pinned as constants below, so adding an entry means
   raising one in the same diff, which a reviewer sees.

Proving that a listed module still fails its strict check needs a full mypy
run over the tree (minutes), so that half is left to the next baseline
re-measurement rather than to this test.
"""

from __future__ import annotations

import json
import subprocess
import sys
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

import pytest
import tomllib
from mypy.find_sources import create_source_list
from mypy.fscache import FileSystemCache
from mypy.options import Options

from scripts.validation import git_hook_policy as policy

REPO_ROOT = Path(__file__).resolve().parents[1]
PYPROJECT = REPO_ROOT / "pyproject.toml"

# Shrink-only pins. Lower each number when you fix debt; never raise it to make
# an entry fit. Adding an entry without editing these constants fails the
# length tests below, so the growth shows up in the diff a reviewer reads.
EXPECTED_C901_BASELINE_ENTRIES = 79
EXPECTED_STRICT_BASELINE_MODULE_NAMES = 144

C901_BASELINE_CODES = ["C901"]
# The only settings a strict-baseline override may carry, each at the value
# that turns one strict check off for the listed modules.
STRICT_RELAX_SETTINGS: Mapping[str, object] = {
    "implicit_reexport": True,
    "disallow_subclassing_any": False,
    "disable_error_code": ["redundant-cast"],
    "warn_unused_ignores": False,
    "disallow_untyped_defs": False,
    "disallow_incomplete_defs": False,
    "disallow_untyped_calls": False,
    "disallow_untyped_decorators": False,
    "strict_equality": False,
    "check_untyped_defs": False,
}
# The strict checks the tests.* override turns off, all at False: the ruff ANN
# waiver means test functions carry no annotations (the reason
# MYPY_TEST_PATH_FLAGS exists).
TESTS_OVERRIDE_OFF_SETTINGS = (
    "disallow_any_generics warn_return_any disallow_untyped_defs "
    "disallow_incomplete_defs disallow_untyped_calls check_untyped_defs"
).split()
# Override shapes that predate the strict baseline. Each relaxes a setting the
# baseline vocabulary does not name, so none can hide a baseline entry. A block
# matching neither a baseline shape nor one of these fails closed:
# strict_baseline_module_lists() raises instead of skipping it.
KNOWN_NON_BASELINE_OVERRIDES: tuple[Mapping[str, object], ...] = (
    {"disallow_any_generics": False},
    {"ignore_missing_imports": True},
    {"disable_error_code": ["arg-type", "return-value"]},
    {"disable_error_code": ["type-arg", "valid-type", "no-any-return"]},
    dict.fromkeys(TESTS_OVERRIDE_OFF_SETTINGS, False),
)
# The generated mirrors may waive the whole C90 family: each repeats a tree
# whose canonical sources carry the C901 baseline entries (ADR-115 comments in
# pyproject.toml). C901, the one rule the baseline waives per file, never is.
GENERATED_MIRROR_C90_GLOBS = frozenset(
    {
        "src/codex/skills/**/*.py",
        "src/copilot-cli/hooks/**/*.py",
        "src/copilot-cli/skills/**/*.py",
        "src/cursor/skills/**/*.py",
        "src/hermes/**/*.py",
    }
)
_GLOB_CHARS = frozenset("*?[")


def _load_pyproject() -> dict[str, Any]:
    return tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))


def _tracked_python_files() -> list[str]:
    result = subprocess.run(
        ["git", "ls-files", "-z", "--", "*.py"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=True,
    )
    return [name for name in result.stdout.split("\0") if name]


def c901_baseline(pyproject: Mapping[str, Any]) -> dict[str, list[str]]:
    lint = pyproject.get("tool", {}).get("ruff", {}).get("lint", {})
    return dict(lint.get("extend-per-file-ignores", {}))


def malformed_c901_entries(baseline: Mapping[str, Sequence[str]]) -> list[str]:
    """Return entries that waive anything but C901 or match more than one file."""
    return sorted(
        path
        for path, codes in baseline.items()
        if list(codes) != C901_BASELINE_CODES or _GLOB_CHARS & set(path)
    )


def stale_c901_entries(
    baseline: Iterable[str],
    tracked: Iterable[str],
    violating: Iterable[str],
) -> dict[str, str]:
    """Map each stale baseline path to the reason it is stale."""
    tracked_set = set(tracked)
    violating_set = set(violating)
    stale: dict[str, str] = {}
    for path in baseline:
        if path not in tracked_set:
            stale[path] = "not a tracked file"
        elif path not in violating_set:
            stale[path] = "no C901 violation left"
    return stale


def _c901_violating_files(paths: Sequence[str], max_complexity: int) -> set[str]:
    # --isolated drops pyproject's per-file ignores, so the scan sees the
    # violations the baseline waives.
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "ruff",
            "check",
            "--isolated",
            "--select",
            "C901",
            "--config",
            f"lint.mccabe.max-complexity = {max_complexity}",
            "--output-format",
            "json",
            "--",
            *paths,
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    # A missing or crashing ruff would otherwise surface as a JSONDecodeError
    # from an empty stdout, which names no cause.
    assert result.returncode in (0, 1), (
        f"ruff did not run: exit {result.returncode}, stderr={result.stderr!r}"
    )
    assert result.stdout.strip(), (
        f"ruff exited {result.returncode} with no JSON on stdout; stderr={result.stderr!r}"
    )
    return {
        Path(record["filename"]).resolve().relative_to(REPO_ROOT).as_posix()
        for record in json.loads(result.stdout)
    }


def is_strict_relax(settings: Mapping[str, object]) -> bool:
    """Whether every setting is a strict-baseline relaxation at its relax value."""
    return all(
        key in STRICT_RELAX_SETTINGS and STRICT_RELAX_SETTINGS[key] == value
        for key, value in settings.items()
    )


def _mypy_overrides(pyproject: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    overrides = pyproject.get("tool", {}).get("mypy", {}).get("overrides", [])
    return [override for override in overrides if isinstance(override, Mapping)]


def _settings(override: Mapping[str, Any]) -> dict[str, object]:
    """An override block's settings, without its ``module`` selector."""
    return {key: value for key, value in override.items() if key != "module"}


def unclassified_override_blocks(pyproject: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Return override blocks that are neither a baseline block nor a known shape.

    Fails closed. The earlier selector matched settings against
    STRICT_RELAX_SETTINGS and dropped every block that did not match, so a block
    relaxing an unlisted setting escaped the existence and sortedness checks.
    """
    unclassified: list[dict[str, Any]] = []
    for override in _mypy_overrides(pyproject):
        settings = _settings(override)
        # A block carrying no settings relaxes nothing, so it hides no entry.
        if not settings:
            continue
        if isinstance(override.get("module"), list) and is_strict_relax(settings):
            continue
        if any(settings == known for known in KNOWN_NON_BASELINE_OVERRIDES):
            continue
        unclassified.append(dict(override))
    return unclassified


def strict_baseline_module_lists(pyproject: Mapping[str, Any]) -> list[list[str]]:
    """Return the module list of each strict-baseline override, in file order.

    Raises ValueError on a block the classifier cannot place, so an
    unrecognised block reaches a reader instead of disappearing.
    """
    unclassified = unclassified_override_blocks(pyproject)
    if unclassified:
        raise ValueError(
            f"{len(unclassified)} [[tool.mypy.overrides]] block(s) are neither a "
            f"strict-baseline block nor a known shape: {unclassified}. A baseline block "
            "lists `module` as an array plus one STRICT_RELAX_SETTINGS setting at its "
            "relax value. Register any other shape in KNOWN_NON_BASELINE_OVERRIDES."
        )
    lists: list[list[str]] = []
    for override in _mypy_overrides(pyproject):
        names = override.get("module")
        settings = _settings(override)
        if not isinstance(names, list) or not settings:
            continue
        if is_strict_relax(settings):
            lists.append([str(name) for name in names])
    return lists


def strict_baseline_modules(pyproject: Mapping[str, Any]) -> list[str]:
    return [name for names in strict_baseline_module_lists(pyproject) for name in names]


def unknown_modules(modules: Iterable[str], known: Iterable[str]) -> list[str]:
    known_set = set(known)
    return sorted({module for module in modules if module not in known_set})


def _gate_module_names(paths: Sequence[str]) -> set[str]:
    """Return the module names the pre-push mypy gate can give ``paths``."""
    sources = create_source_list(list(paths), Options(), FileSystemCache())
    names = {source.module for source in sources}
    # The gate type-checks scripts/validation/ with that directory on MYPYPATH,
    # so its modules also load under their bare names.
    names.update(
        Path(path).stem for path in paths if Path(path).parent == Path("scripts/validation")
    )
    return names


# --- Real pyproject invariants -------------------------------------------------


def test_c901_baseline_entries_are_single_file_c901_waivers() -> None:
    baseline = c901_baseline(_load_pyproject())

    assert baseline, "the C901 baseline table is missing or empty"
    assert malformed_c901_entries(baseline) == []


def test_c901_baseline_is_sorted_so_removals_diff_cleanly() -> None:
    paths = list(c901_baseline(_load_pyproject()))

    assert paths == sorted(paths)


def test_c901_baseline_has_no_stale_entries() -> None:
    pyproject = _load_pyproject()
    baseline = c901_baseline(pyproject)
    max_complexity = pyproject["tool"]["ruff"]["lint"]["mccabe"]["max-complexity"]
    tracked = _tracked_python_files()
    present = [path for path in baseline if path in set(tracked)]

    violating = _c901_violating_files(present, max_complexity)
    stale = stale_c901_entries(baseline, tracked, violating)

    assert stale == {}, (
        f"{len(stale)} of {len(baseline)} C901 baseline entries are stale; delete "
        f"them from [tool.ruff.lint.extend-per-file-ignores]: {stale}"
    )


def test_c901_baseline_length_matches_the_pinned_constant() -> None:
    baseline = c901_baseline(_load_pyproject())

    assert len(baseline) == EXPECTED_C901_BASELINE_ENTRIES, (
        f"[tool.ruff.lint.extend-per-file-ignores] holds {len(baseline)} entries, pinned "
        f"at {EXPECTED_C901_BASELINE_ENTRIES}. Lower the constant when you delete an "
        "entry; never raise it. New code must be under max-complexity, not added here."
    )


def test_no_per_file_ignores_entry_waives_c901() -> None:
    lint = _load_pyproject()["tool"]["ruff"]["lint"]
    ignores = {path: list(codes) for path, codes in lint.get("per-file-ignores", {}).items()}

    assert ignores, "the per-file-ignores table is missing or empty"
    waiving_c901 = sorted(path for path, codes in ignores.items() if "C901" in codes)
    assert waiving_c901 == [], (
        "these [tool.ruff.lint.per-file-ignores] entries waive C901, which hides a "
        f"complexity violation from the shrink-only baseline: {waiving_c901}. Fix the "
        "function, or add one file to [tool.ruff.lint.extend-per-file-ignores] where "
        "the length and stale-entry tests see it."
    )
    # Only the generated mirrors waive the whole C90 family, and only as globs:
    # each repeats a tree whose canonical sources carry the baseline entries.
    family = {path for path, codes in ignores.items() if "C90" in codes}
    assert sorted(family - GENERATED_MIRROR_C90_GLOBS) == [], (
        "these per-file-ignores entries waive the C90 family outside the generated "
        f"mirror globs, which the baseline does not cover: {sorted(family)}"
    )
    assert all(_GLOB_CHARS & set(path) for path in family), (
        f"a C90 family waiver must target a mirror glob, not one file: {sorted(family)}"
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


# --- Helper unit coverage (positive, negative, edge) ---------------------------


def test_stale_c901_entries_empty_when_every_entry_still_violates() -> None:
    assert stale_c901_entries(["a.py", "b.py"], ["a.py", "b.py"], ["a.py", "b.py"]) == {}


def test_stale_c901_entries_flags_fixed_file() -> None:
    assert stale_c901_entries(["a.py", "b.py"], ["a.py", "b.py"], ["a.py"]) == {
        "b.py": "no C901 violation left"
    }


def test_stale_c901_entries_flags_deleted_file_before_violation_check() -> None:
    assert stale_c901_entries(["gone.py"], ["a.py"], []) == {"gone.py": "not a tracked file"}


def test_stale_c901_entries_empty_baseline_is_clean() -> None:
    assert stale_c901_entries([], ["a.py"], ["a.py"]) == {}


def test_malformed_c901_entries_flags_other_codes_and_globs() -> None:
    baseline = {
        "ok.py": ["C901"],
        "extra.py": ["C901", "E501"],
        "family.py": ["C90"],
        "scripts/**/*.py": ["C901"],
    }

    assert malformed_c901_entries(baseline) == ["extra.py", "family.py", "scripts/**/*.py"]


def test_c901_baseline_reads_missing_table_as_empty() -> None:
    assert c901_baseline({}) == {}
    assert c901_baseline({"tool": {"ruff": {"lint": {}}}}) == {}


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
        {"module": ["pkg.f"], "implicit_reexport": False},
    )

    assert [block.get("module") for block in unclassified_override_blocks(pyproject)] == [
        ["pkg.d"],
        ["pkg.f"],
    ]
    with pytest.raises(ValueError, match="neither a strict-baseline block"):
        strict_baseline_module_lists(pyproject)


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
