"""Ratchet-down guards for the strict mypy and C901 baselines in pyproject.toml.

``strict = true`` and ruff's C90 rule landed with a baseline, so code that
failed them on main still passes. The baseline must only shrink:

1. ``[tool.ruff.lint.extend-per-file-ignores]`` holds only the C901 baseline.
   Every entry must name one tracked file that still has a C901 violation. A
   fixed or deleted file leaves a stale entry, and that entry would silently
   waive the rule for new code in the file.
2. The "Strict-mode baseline" mypy overrides relax one strict check each. Every
   module they list must still exist, so a renamed or deleted module cannot
   leave a dead entry behind.

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

import tomllib
from mypy.find_sources import create_source_list
from mypy.fscache import FileSystemCache
from mypy.options import Options

REPO_ROOT = Path(__file__).resolve().parents[1]
PYPROJECT = REPO_ROOT / "pyproject.toml"

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
    assert result.returncode in (0, 1), result.stderr
    return {
        Path(record["filename"]).resolve().relative_to(REPO_ROOT).as_posix()
        for record in json.loads(result.stdout)
    }


def strict_baseline_module_lists(pyproject: Mapping[str, Any]) -> list[list[str]]:
    """Return the module list of each strict-baseline override, in file order."""
    lists: list[list[str]] = []
    for override in pyproject.get("tool", {}).get("mypy", {}).get("overrides", []):
        names = override.get("module")
        settings = {key: value for key, value in override.items() if key != "module"}
        if not isinstance(names, list) or not settings:
            continue
        if all(STRICT_RELAX_SETTINGS.get(key) == value for key, value in settings.items()):
            lists.append(names)
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
    pyproject = {
        "tool": {
            "mypy": {
                "overrides": [
                    {"module": ["pkg.a", "pkg.b"], "implicit_reexport": True},
                    {"module": ["pkg.c"], "disable_error_code": ["redundant-cast"]},
                    {"module": ["pkg.d"], "disable_error_code": ["arg-type"]},
                    {"module": ["pkg.e"], "disallow_any_generics": False},
                    {"module": "tests.*", "disallow_untyped_defs": False},
                    {"module": ["pkg.f"], "implicit_reexport": False},
                    {"module": ["pkg.g"]},
                ]
            }
        }
    }

    assert strict_baseline_modules(pyproject) == ["pkg.a", "pkg.b", "pkg.c"]


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
