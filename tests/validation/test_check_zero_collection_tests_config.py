"""Configuration-focused tests for check_zero_collection_tests.py."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
_VALIDATION_DIR = REPO_ROOT / "scripts" / "validation"
if str(_VALIDATION_DIR) not in sys.path:
    sys.path.insert(0, str(_VALIDATION_DIR))

from check_zero_collection_tests import main, read_pytest_config

_PYPROJECT = """\
[tool.pytest.ini_options]
testpaths = ["tests"]
python_files = ["test_*.py"]
markers = [
    "windows_path: Tests that exercise Windows path handling and must run on a Windows runner.",
    "unit: Unit tests. Registered but not tied to any separately gated environment.",
]
"""
_REAL_TEST = "def test_passes():\n    assert True\n"
_NO_TESTS = "def helper():\n    return 1\n"


def _make_repo(root: Path, pyproject: str = _PYPROJECT) -> Path:
    (root / "pyproject.toml").write_text(pyproject, encoding="utf-8")
    tests = root / "tests"
    tests.mkdir()
    (tests / "test_real.py").write_text(_REAL_TEST, encoding="utf-8")
    return tests


def _run(root: Path) -> int:
    return main(["--repo-root", str(root)])


def test_a_file_pytest_cannot_import_is_reported_as_external(tmp_path: Path) -> None:
    """A broken collection must not read as a clean tree."""
    tests = _make_repo(tmp_path)
    (tests / "test_broken.py").write_text("def test_x(:\n", encoding="utf-8")

    assert _run(tmp_path) == 3


def test_a_config_without_testpaths_is_a_configuration_error(tmp_path: Path) -> None:
    """Guessing the scope would silently narrow what is examined."""
    _make_repo(tmp_path, pyproject='[tool.pytest.ini_options]\npython_files = ["test_*.py"]\n')

    assert _run(tmp_path) == 2


@pytest.mark.parametrize(
    "pyproject",
    [
        '[tool.pytest.ini_options]\ntestpaths = ["tests"]\n',
        '[tool.pytest.ini_options]\ntestpaths = []\npython_files = ["test_*.py"]\n',
        '[tool.pytest.ini_options]\ntestpaths = ["tests"]\npython_files = []\n',
    ],
)
def test_missing_or_empty_config_lists_are_configuration_errors(
    tmp_path: Path, pyproject: str
) -> None:
    """The guard needs both config lists, and each must contain at least one entry."""
    _make_repo(tmp_path, pyproject=pyproject)

    assert _run(tmp_path) == 2


def test_malformed_toml_syntax_is_a_configuration_error(tmp_path: Path) -> None:
    """A TOML parse error must map to the documented configuration exit."""
    _make_repo(tmp_path, pyproject='[tool.pytest.ini_options]\ntestpaths = ["tests\n')

    assert _run(tmp_path) == 2


def test_a_nonexistent_testpath_is_a_configuration_error(tmp_path: Path) -> None:
    """A configured path pytest cannot enter is invalid configuration."""
    pyproject = """\
[tool.pytest.ini_options]
testpaths = ["tests/missing"]
python_files = ["test_*.py"]
"""
    _make_repo(tmp_path, pyproject)

    assert _run(tmp_path) == 2


def test_a_testpath_outside_the_repository_is_a_configuration_error(
    tmp_path: Path,
) -> None:
    """A testpath that resolves outside the repo root must not be trusted."""
    outside = tmp_path.parent / f"outside-{tmp_path.name}"
    outside.mkdir()
    pyproject = f"""\
[tool.pytest.ini_options]
testpaths = ["{outside.as_posix()}"]
python_files = ["test_*.py"]
"""
    _make_repo(tmp_path, pyproject)

    assert _run(tmp_path) == 2


def test_an_option_shaped_testpath_is_passed_as_a_path(tmp_path: Path) -> None:
    """A repository path must not become a pytest command-line option."""
    pyproject = """\
[tool.pytest.ini_options]
testpaths = ["--ignore=tests"]
python_files = ["test_*.py"]
"""
    _make_repo(tmp_path, pyproject)
    option_path = tmp_path / "--ignore=tests"
    option_path.mkdir()
    (option_path / "test_collects_nothing.py").write_text(_NO_TESTS, encoding="utf-8")

    assert _run(tmp_path) == 1


def test_a_testpath_with_no_candidate_modules_is_a_configuration_error(
    tmp_path: Path,
) -> None:
    """A green gate must report at least one examined candidate."""
    pyproject = """\
[tool.pytest.ini_options]
testpaths = ["empty"]
python_files = ["test_*.py"]
"""
    _make_repo(tmp_path, pyproject)
    (tmp_path / "empty").mkdir()

    assert _run(tmp_path) == 2


def test_a_missing_pyproject_is_a_configuration_error(tmp_path: Path) -> None:
    """No contract to read means no verdict to give."""
    (tmp_path / "tests").mkdir()

    assert _run(tmp_path) == 2


@pytest.mark.parametrize(
    ("testpaths", "python_files"),
    [
        ([1], ["test_*.py"]),
        ([""], ["test_*.py"]),
        (["tests"], [1]),
        (["tests"], [""]),
    ],
)
def test_invalid_testpaths_and_python_files_entries_are_configuration_errors(
    tmp_path: Path,
    testpaths: list[object],
    python_files: list[object],
) -> None:
    """Non-string and empty-string config entries are configuration errors."""
    pyproject = (
        "[tool.pytest.ini_options]\n"
        f"testpaths = {testpaths!r}\n"
        f"python_files = {python_files!r}\n"
    )
    _make_repo(tmp_path, pyproject)

    assert _run(tmp_path) == 2


def test_pytest_default_norecursedirs_are_honoured(tmp_path: Path) -> None:
    """The guard must not inspect a directory pytest excludes by default."""
    tests = _make_repo(tmp_path)
    ignored = tests / "{arch}"
    ignored.mkdir()
    (ignored / "test_ignored.py").write_text(_NO_TESTS, encoding="utf-8")

    assert _run(tmp_path) == 0


def test_configured_norecursedirs_globs_are_honoured(tmp_path: Path) -> None:
    """Configured directory globs belong to pytest, not a copied name list."""
    pyproject = _PYPROJECT + 'norecursedirs = ["generated*"]\n'
    tests = _make_repo(tmp_path, pyproject)
    ignored = tests / "generated-output"
    ignored.mkdir()
    (ignored / "test_ignored.py").write_text(_NO_TESTS, encoding="utf-8")

    assert _run(tmp_path) == 0


def test_collect_ignore_is_honoured(tmp_path: Path) -> None:
    """A conftest exclusion must not become a zero-collection violation."""
    tests = _make_repo(tmp_path)
    (tests / "conftest.py").write_text(
        'collect_ignore = ["test_ignored.py"]\n', encoding="utf-8"
    )
    (tests / "test_ignored.py").write_text(_NO_TESTS, encoding="utf-8")

    assert _run(tmp_path) == 0


def test_read_pytest_config_returns_the_declared_contract(tmp_path: Path) -> None:
    """The guard reads testpaths and python_files rather than hardcoding them."""
    _make_repo(tmp_path)

    assert read_pytest_config(tmp_path) == (["tests"], ["test_*.py"])


@pytest.mark.parametrize(
    "pyproject",
    [
        'tool = "invalid"\n',
        '[tool]\npytest = "invalid"\n',
        '[tool.pytest]\nini_options = "invalid"\n',
    ],
)
def test_malformed_pytest_table_shapes_are_configuration_errors(
    tmp_path: Path, pyproject: str
) -> None:
    """Malformed table shapes must use the documented configuration exit."""
    _make_repo(tmp_path, pyproject)

    assert _run(tmp_path) == 2
