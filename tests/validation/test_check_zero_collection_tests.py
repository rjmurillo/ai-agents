# taste-lint: ignore file-size -- one gate, one test file; splitting these
# cases across files would let a case for one behavior pass while another
# silently loses its coverage, the same reasoning `.claude/lib/github_core`
# uses for the file this test suite exercises.
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
- edge/module-skip: any module pytest skips at collection time (unconditional
  or conditional, with or without a marker) needs the same explicit
  declaration as a file that collects nothing outright
- edge/bare-marker: a declaration with no reason is not a declaration -> exit 1
- edge/marker-mention: prose that mentions the marker is not a declaration
- edge/ignored: pytest defaults, configured norecursedirs globs, and
  collect_ignore entries do not create false violations
- edge/config: missing, malformed, or unusable testpaths -> exit 2
- edge/uncollectable: a file pytest cannot import -> exit 3, not a false pass
- unit: declares_exemption and read_pytest_config
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
    declares_exemption,
    main,
    read_pytest_config,
)

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

# Any module pytest skips at collection time, marked or not, conditional or
# not, needs the same explicit `pytest-zero-collection:` declaration as a file
# that collects nothing outright (Copilot review rounds 3-7, PR #5344: a
# marker-based auto-trust mechanism was tried and repeatedly found bypassable,
# since marker syntax alone never proves the guarded code runs anywhere).
_MODULE_LEVEL_SKIP = (
    "import pytest\n\n"
    'pytest.skip("windows only", allow_module_level=True)\n\n\n'
    "def test_windows_path():\n    assert True\n"
)
_MODULE_LEVEL_SKIP_MARKED = (
    "import pytest\n\n"
    'pytest.skip("windows only", allow_module_level=True)\n\n\n'
    "@pytest.mark.windows_path\n"
    "def test_windows_path():\n    assert True\n"
)
_IMPORT_OR_SKIP = (
    "import pytest\n\n"
    'pytest.importorskip("a_module_that_does_not_exist")\n\n\n'
    "def test_needs_the_dependency():\n    assert True\n"
)
_IMPORT_OR_SKIP_MARKED = (
    "import pytest\n\n"
    'pytest.importorskip("a_module_that_does_not_exist")\n\n\n'
    "@pytest.mark.windows_path\n"
    "def test_needs_the_dependency():\n    assert True\n"
)
_SKIP_ONLY = (
    "import pytest\n\n"
    'pytest.skip("nothing to collect", allow_module_level=True)\n'
)
_IMPORT_OR_SKIP_ONLY = (
    "import pytest\n\n"
    'pytest.importorskip("a_module_that_does_not_exist")\n'
)
_CONDITIONAL_PLATFORM_SKIP_MARKED = (
    "import sys\n"
    "import pytest\n\n"
    'if sys.platform == "a-platform-that-does-not-exist":\n'
    "    @pytest.mark.windows_path\n"
    "    def test_platform_behavior():\n"
    "        assert True\n"
    "else:\n"
    '    pytest.skip("other platform", allow_module_level=True)\n'
)
_CONDITIONAL_PLATFORM_SKIP_UNMARKED = (
    "import sys\n"
    "import pytest\n\n"
    'if sys.platform == "a-platform-that-does-not-exist":\n'
    "    def test_platform_behavior():\n"
    "        assert True\n"
    "else:\n"
    '    pytest.skip("other platform", allow_module_level=True)\n'
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


def test_marker_text_inside_an_ordinary_string_does_not_exempt(tmp_path: Path) -> None:
    """Only comments and the module docstring may declare an exemption."""
    tests = _make_repo(tmp_path)
    (tests / "test_marker_text.py").write_text(
        f'MARKER = "{EXEMPTION_MARKER} ordinary string"\n{_NO_TESTS}',
        encoding="utf-8",
    )

    assert _run(tmp_path) == 1


def test_an_incidental_marker_mention_does_not_exempt(tmp_path: Path) -> None:
    """A comment must declare the marker, not merely discuss it."""
    tests = _make_repo(tmp_path)
    (tests / "test_marker_mention.py").write_text(
        f"# Do not add {EXEMPTION_MARKER} markers here.\n{_NO_TESTS}",
        encoding="utf-8",
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


@pytest.mark.parametrize(
    "source",
    [
        _MODULE_LEVEL_SKIP,
        _MODULE_LEVEL_SKIP_MARKED,
        _IMPORT_OR_SKIP,
        _IMPORT_OR_SKIP_MARKED,
        _CONDITIONAL_PLATFORM_SKIP_MARKED,
        _CONDITIONAL_PLATFORM_SKIP_UNMARKED,
    ],
)
def test_a_skipped_module_needs_a_declaration_regardless_of_marker_syntax(
    tmp_path: Path, source: str
) -> None:
    """No module pytest skips at collection time is auto-trusted, marked or not.

    Copilot review rounds 3-7 (PR #5344): a marker-based auto-trust mechanism
    for skipped modules was tried and repeatedly found bypassable, because
    marker syntax alone never proves the guarded code runs on another host. A
    dead test behind a condition that is false on every real host
    (``_CONDITIONAL_PLATFORM_SKIP_MARKED``'s ``"a-platform-that-does-not-exist"``)
    can carry ``@pytest.mark.windows_path`` forever and still never collect
    anywhere. Every one of these six shapes, unconditional or conditional,
    ``skip`` or ``importorskip``, decorated or not, needs the same explicit
    ``pytest-zero-collection:`` declaration as a file that collects nothing
    outright.
    """
    tests = _make_repo(tmp_path)
    (tests / "test_skipped_module.py").write_text(source, encoding="utf-8")

    assert _run(tmp_path) == 1


def test_a_declared_skipped_module_is_allowed(tmp_path: Path) -> None:
    """A skipped module with an explicit, reasoned declaration passes."""
    tests = _make_repo(tmp_path)
    (tests / "test_windows_only.py").write_text(
        f"# {EXEMPTION_MARKER} this repository never collects it on any CI host.\n"
        f"{_MODULE_LEVEL_SKIP}",
        encoding="utf-8",
    )

    assert _run(tmp_path) == 0


def test_a_skipped_module_does_not_excuse_an_undeclared_neighbour(
    tmp_path: Path,
) -> None:
    """Negative control: one file's exemption must not turn the guard off wholesale."""
    tests = _make_repo(tmp_path)
    (tests / "test_windows_only.py").write_text(
        f"# {EXEMPTION_MARKER} this repository never collects it on any CI host.\n"
        f"{_MODULE_LEVEL_SKIP}",
        encoding="utf-8",
    )
    (tests / "test_collects_nothing.py").write_text(_NO_TESTS, encoding="utf-8")

    assert _run(tmp_path) == 1


@pytest.mark.parametrize("source", [_SKIP_ONLY, _IMPORT_OR_SKIP_ONLY])
def test_a_skip_only_module_is_not_a_test_suite(tmp_path: Path, source: str) -> None:
    """Skipping cannot create evidence that the file defines a test."""
    tests = _make_repo(tmp_path)
    (tests / "test_skip_only.py").write_text(source, encoding="utf-8")

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


def test_malformed_toml_syntax_is_a_configuration_error(tmp_path: Path) -> None:
    """A TOML parse error must map to the documented configuration exit.

    Distinct from the malformed-table-shape cases below: this is a syntax
    error tomllib itself refuses to parse (an unterminated string), not a
    shape ``tomllib`` accepts but this guard cannot use.
    """
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
    """A testpath that resolves outside the repo root must not be trusted.

    The nonexistent-path case above exercises only the ``not
    resolved.exists()`` half of the guard; this exercises the
    ``is_relative_to(repo_root)`` half, so removing either check regresses
    silently without both cases.
    """
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


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        (f"# {EXEMPTION_MARKER} imported by siblings", True),
        (f'"""Doc.\n\n{EXEMPTION_MARKER} a reason spanning the line.\n"""', True),
        (f'MARKER = "{EXEMPTION_MARKER} ordinary string"', False),
        (
            f'def helper():\n    """{EXEMPTION_MARKER} function docstring"""\n',
            False,
        ),
        (f"# {EXEMPTION_MARKER}", False),
        (f"# {EXEMPTION_MARKER}   ", False),
        ("# no marker here", False),
        ("", False),
    ],
)
def test_declares_exemption_requires_a_reason(text: str, expected: bool) -> None:
    """A marker with nothing after it documents nothing."""
    assert declares_exemption(text) is expected
