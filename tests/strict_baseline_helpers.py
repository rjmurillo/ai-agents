"""Readers and classifiers for the strict mypy and C901 baselines.

Shared by ``tests/test_strict_baselines.py`` (the C901 half) and
``tests/test_mypy_strict_baseline.py`` (the mypy half), so both read
``pyproject.toml`` through one implementation. Not a test module: no ``test_``
name, so pytest does not collect it.
"""

from __future__ import annotations

import json
import os
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

# Shrink-only pins. Lower each number when you fix debt; never raise it to make
# an entry fit. Adding an entry without editing these constants fails the
# length tests below, so the growth shows up in the diff a reviewer reads.
EXPECTED_C901_BASELINE_ENTRIES = 79
# 158 is the complete count for this PR, not growth: the first cut counted 144
# and missed the modules that fail only an error code (type-arg,
# no-any-return, call-overload). Those now count, which is 148, plus the 10
# modules whose debt strict mode surfaced and no override named at all. From
# here the number only goes down. It counts entries, not distinct modules
# (144): a module listed in three blocks lowers it by three once fixed.
EXPECTED_STRICT_BASELINE_MODULE_NAMES = 158

C901_BASELINE_CODES = ["C901"]
DISABLE_ERROR_CODE_KEY = "disable_error_code"
# The mypy error codes a baseline block may turn off. A block naming anything
# else is unclassified, so a typo or a whole-check bypass reaches a reader
# instead of quietly disabling more than the debt it records.
STRICT_ERROR_CODES = frozenset(
    {
        "arg-type",
        "assignment",
        "attr-defined",
        "call-overload",
        "index",
        "no-any-return",
        "operator",
        "redundant-cast",
        "return-value",
        "type-arg",
        "union-attr",
        "unused-ignore",
        "valid-type",
    }
)
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
    """Whether the block turns off strict checks for the modules it names.

    Two shapes count as a relaxation, and both are baseline entries: one relax
    value from STRICT_RELAX_SETTINGS, or a `disable_error_code` list naming the
    error codes the module still raises. The second shape exists because the
    debt strict mode surfaced is not always a whole setting: a bare `dict`
    annotation is `type-arg` while the rest of strict still applies.
    """
    if not settings:
        return False
    if set(settings) == {DISABLE_ERROR_CODE_KEY}:
        codes = settings[DISABLE_ERROR_CODE_KEY]
        return (
            isinstance(codes, list)
            and bool(codes)
            and all(isinstance(code, str) and code in STRICT_ERROR_CODES for code in codes)
        )
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
    # A tracked directory symlink at the repo root is a second import path for
    # the same files, and mypy reports the name the path spells, so the override
    # may name either form. memory_enhancement -> scripts/memory_enhancement.
    for link in REPO_ROOT.iterdir():
        if not (link.is_symlink() and link.is_dir()):
            continue
        target = os.path.relpath(link.resolve(), REPO_ROOT).replace(os.sep, "/")
        names.update(
            ".".join([link.name, *Path(path).relative_to(target).with_suffix("").parts])
            for path in paths
            if path == target or path.startswith(f"{target}/")
        )
    return names
