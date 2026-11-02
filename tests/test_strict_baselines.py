"""Ratchet-down guards for the C901 half of the baseline in pyproject.toml.

ruff's C90 rule landed with a baseline, so code that failed it on main still
passes. The baseline must only shrink:
``[tool.ruff.lint.extend-per-file-ignores]`` holds only the C901 baseline, every
entry must name one tracked file that still has a C901 violation, and the
table's length is pinned, so adding an entry fails until a reviewer sees the
constant move. The mypy half lives in ``tests/test_mypy_strict_baseline.py``.
"""

from __future__ import annotations

from tests.strict_baseline_helpers import (
    _GLOB_CHARS,
    EXPECTED_C901_BASELINE_ENTRIES,
    GENERATED_MIRROR_C90_GLOBS,
    _c901_violating_files,
    _load_pyproject,
    _tracked_python_files,
    c901_baseline,
    malformed_c901_entries,
    stale_c901_entries,
)


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
