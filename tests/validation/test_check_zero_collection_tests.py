"""Tests for scripts/validation/check_zero_collection_tests.py (issue #4494).

Guards the gate that catches a file pytest walks into and collects nothing
from. Such a file is inside ``testpaths``, matches ``python_files``, and is
counted in no failure, so it reads as a passing suite forever.

Every case builds a miniature repository under ``tmp_path`` and drives
``main(argv)`` so the assertion lands on the process exit code, not on a
helper's return value (`.claude/rules/testing.md` MUST 8).

- pos: a file with a real test -> exit 0
- neg/negative-control: adding a zero-collecting file flips the same repo from
  0 to 1, and removing it flips it back (issue #4494 acceptance criterion 3)
- neg: the failure names the offending path on stderr
- neg/only-file: the sole file collecting nothing (pytest exit 5) -> exit 1
- neg/stale: a declared file that starts collecting -> exit 1
- edge/declared: a declared zero-collecting file -> exit 0
- edge/module-skip: a module-level skip or importorskip -> exit 0 undeclared,
  and exit 1 when it carries a declaration it no longer needs
- edge/bare-marker: a declaration with no reason is not a declaration -> exit 1
- edge/skipped-dirs: files under a dot directory or __pycache__ are not walked
- edge/config: pyproject without testpaths -> exit 2; missing pyproject -> exit 2
- edge/uncollectable: a file pytest cannot import -> exit 3, not a false pass
- unit: declares_exemption, candidate_files, read_pytest_config
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
_VALIDATION_DIR = REPO_ROOT / "scripts" / "validation"
if str(_VALIDATION_DIR) not in sys.path:
    sys.path.insert(0, str(_VALIDATION_DIR))

from check_zero_collection_tests import (
    EXEMPTION_MARKER,
    candidate_files,
    declares_exemption,
    main,
    read_pytest_config,
)

_PYPROJECT = """\
[tool.pytest.ini_options]
testpaths = ["tests"]
python_files = ["test_*.py"]
"""

_REAL_TEST = "def test_passes():\n    assert True\n"
_NO_TESTS = "def helper():\n    return 1\n"

# Both raise Skipped while the Module collector runs, so no item ever exists on
# the host that skips and every item exists on the host that does not.
_MODULE_LEVEL_SKIP = (
    "import pytest\n\n"
    'pytest.skip("windows only", allow_module_level=True)\n\n\n'
    "def test_windows_path():\n    assert True\n"
)
_IMPORT_OR_SKIP = (
    "import pytest\n\n"
    'pytest.importorskip("a_module_that_does_not_exist")\n\n\n'
    "def test_needs_the_dependency():\n    assert True\n"
)


def _make_repo(root: Path, pyproject: str = _PYPROJECT) -> Path:
    """Write a miniature repository whose tests/ directory holds one real test."""
    (root / "pyproject.toml").write_text(pyproject, encoding="utf-8")
    tests = root / "tests"
    tests.mkdir()
    (tests / "test_real.py").write_text(_REAL_TEST, encoding="utf-8")
    return tests


def _run(root: Path) -> int:
    return main(["--repo-root", str(root)])


def test_a_tree_whose_files_all_collect_passes(tmp_path: Path) -> None:
    """A file with a real test is what the guard is meant to let through."""
    _make_repo(tmp_path)

    assert _run(tmp_path) == 0


def test_adding_a_zero_collecting_file_fails_and_removing_it_passes(
    tmp_path: Path,
) -> None:
    """The negative control: the same repo flips on this one file alone.

    Without this pairing the guard is an unverified claim, because a gate that
    never fails and a gate that cannot fail print the same thing.
    """
    tests = _make_repo(tmp_path)
    assert _run(tmp_path) == 0

    offender = tests / "test_collects_nothing.py"
    offender.write_text(_NO_TESTS, encoding="utf-8")
    assert _run(tmp_path) == 1

    offender.unlink()
    assert _run(tmp_path) == 0


def test_the_failure_names_the_offending_path(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A path the reader cannot locate is not a report."""
    tests = _make_repo(tmp_path)
    (tests / "test_collects_nothing.py").write_text(_NO_TESTS, encoding="utf-8")

    exit_code = _run(tmp_path)

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "tests/test_collects_nothing.py" in captured.err
    assert "examined 2 files" in captured.out


def test_a_lone_zero_collecting_file_still_fails(tmp_path: Path) -> None:
    """pytest exits 5 when nothing at all is collected; that is still a finding."""
    (tmp_path / "pyproject.toml").write_text(_PYPROJECT, encoding="utf-8")
    tests = tmp_path / "tests"
    tests.mkdir()
    (tests / "test_collects_nothing.py").write_text(_NO_TESTS, encoding="utf-8")

    assert _run(tmp_path) == 1


def test_a_declared_file_is_allowed(tmp_path: Path) -> None:
    """A helper module or a checker script declares itself and passes."""
    tests = _make_repo(tmp_path)
    (tests / "test_helpers.py").write_text(
        f'"""Shared helpers.\n\n{EXEMPTION_MARKER} imported by its siblings.\n"""\n{_NO_TESTS}',
        encoding="utf-8",
    )

    assert _run(tmp_path) == 0


def test_a_declaration_without_a_reason_is_not_a_declaration(tmp_path: Path) -> None:
    """A bare marker is an undocumented suppression, so it does not exempt."""
    tests = _make_repo(tmp_path)
    (tests / "test_bare.py").write_text(
        f'"""Helpers.\n\n{EXEMPTION_MARKER}\n"""\n{_NO_TESTS}', encoding="utf-8"
    )

    assert _run(tmp_path) == 1


def test_a_declaration_on_a_file_that_collects_fails(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The inverse case: a marker must not outlive the reason it was written for."""
    tests = _make_repo(tmp_path)
    (tests / "test_stale.py").write_text(
        f'"""Was a helper.\n\n{EXEMPTION_MARKER} no longer true.\n"""\n{_REAL_TEST}',
        encoding="utf-8",
    )

    exit_code = _run(tmp_path)

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "tests/test_stale.py" in captured.err
    assert "stale declarations" in captured.out


def test_a_module_level_skip_needs_no_declaration(tmp_path: Path) -> None:
    """A file that skips on this host collects on another, so neither spelling fits.

    Undeclared it would fail wherever it skips; declared it would fail as stale
    wherever it collects. pyproject.toml sanctions the pattern with the
    windows_path marker and the lefthook job has no OS gate, so the guard has to
    read a module-level skip as the file answering for itself.
    """
    tests = _make_repo(tmp_path)
    (tests / "test_windows_only.py").write_text(_MODULE_LEVEL_SKIP, encoding="utf-8")

    assert _run(tmp_path) == 0


def test_an_import_scope_importorskip_needs_no_declaration(tmp_path: Path) -> None:
    """importorskip raises Skipped from the same collection phase as skip()."""
    tests = _make_repo(tmp_path)
    (tests / "test_optional_dependency.py").write_text(_IMPORT_OR_SKIP, encoding="utf-8")

    assert _run(tmp_path) == 0


def test_a_declaration_on_a_module_level_skip_is_stale(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The mirror of the case above: satisfying the guard makes a marker stale.

    One set decides both directions, so a skipped module must not keep a
    declaration it no longer needs, exactly as a collecting file must not.
    """
    tests = _make_repo(tmp_path)
    (tests / "test_windows_only.py").write_text(
        f"# {EXEMPTION_MARKER} was thought to collect nothing.\n{_MODULE_LEVEL_SKIP}",
        encoding="utf-8",
    )

    exit_code = _run(tmp_path)

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "tests/test_windows_only.py" in captured.err
    assert "stale declarations" in captured.out


def test_a_module_level_skip_does_not_excuse_a_neighbour(tmp_path: Path) -> None:
    """Negative control: the carve-out must not turn the guard off wholesale."""
    tests = _make_repo(tmp_path)
    (tests / "test_windows_only.py").write_text(_MODULE_LEVEL_SKIP, encoding="utf-8")
    (tests / "test_collects_nothing.py").write_text(_NO_TESTS, encoding="utf-8")

    assert _run(tmp_path) == 1


def test_a_file_pytest_cannot_import_is_reported_as_external(tmp_path: Path) -> None:
    """A broken collection must not read as a clean tree."""
    tests = _make_repo(tmp_path)
    (tests / "test_broken.py").write_text("def test_x(:\n", encoding="utf-8")

    assert _run(tmp_path) == 3


def test_a_config_without_testpaths_is_a_configuration_error(tmp_path: Path) -> None:
    """Guessing the scope would silently narrow what is examined."""
    _make_repo(tmp_path, pyproject='[tool.pytest.ini_options]\npython_files = ["test_*.py"]\n')

    assert _run(tmp_path) == 2


def test_a_missing_pyproject_is_a_configuration_error(tmp_path: Path) -> None:
    """No contract to read means no verdict to give."""
    (tmp_path / "tests").mkdir()

    assert _run(tmp_path) == 2


def test_candidate_files_skips_directories_pytest_never_walks(tmp_path: Path) -> None:
    """Dot directories, __pycache__, and build output are not collection sites."""
    tests = _make_repo(tmp_path)
    for hidden in (".hidden", "__pycache__", "node_modules"):
        directory = tests / hidden
        directory.mkdir()
        (directory / "test_ignored.py").write_text(_NO_TESTS, encoding="utf-8")

    found = candidate_files(tmp_path, ["tests"], ["test_*.py"])

    assert found == ["tests/test_real.py"]


def test_candidate_files_honours_the_configured_pattern(tmp_path: Path) -> None:
    """The pattern comes from pyproject, so a widened pattern widens the guard."""
    tests = _make_repo(tmp_path)
    (tests / "check_thing.py").write_text(_REAL_TEST, encoding="utf-8")

    assert candidate_files(tmp_path, ["tests"], ["test_*.py"]) == ["tests/test_real.py"]
    assert candidate_files(tmp_path, ["tests"], ["check_*.py"]) == ["tests/check_thing.py"]


def test_read_pytest_config_returns_the_declared_contract(tmp_path: Path) -> None:
    """The guard reads testpaths and python_files rather than hardcoding them."""
    _make_repo(tmp_path)

    assert read_pytest_config(tmp_path) == (["tests"], ["test_*.py"])


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        (f"# {EXEMPTION_MARKER} imported by siblings", True),
        (f'"""Doc.\n\n{EXEMPTION_MARKER} a reason spanning the line.\n"""', True),
        (f"# {EXEMPTION_MARKER}", False),
        (f"# {EXEMPTION_MARKER}   ", False),
        ("# no marker here", False),
        ("", False),
    ],
)
def test_declares_exemption_requires_a_reason(text: str, expected: bool) -> None:
    """A marker with nothing after it documents nothing."""
    assert declares_exemption(text) is expected


def test_the_repository_itself_passes_the_guard() -> None:
    """The gate must be green against the corpus it ships with.

    A gate that merges red blocks every later push by every contributor
    (`.claude/rules/ci-scripts.md` MUST 13).
    """
    assert main(["--repo-root", str(REPO_ROOT)]) == 0
