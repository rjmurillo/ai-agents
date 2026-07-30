"""Tests for scripts/validation/check_nested_tests.py (issue #3879).

Guards the gate that catches test functions defined inside other functions.
Such functions are never collected by pytest; the file parses, the suite runs
green, and the regression guard is silently absent.

- pos: clean tree (no nested tests) -> exit 0, empty findings
- neg/direct: test function directly inside a helper function -> exit 1, exact file+line
- neg/async: async def test_* inside a function -> caught
- neg/deep: test function nested two levels deep -> caught
- neg/negative-control: the gate must catch the exact shape found in PR #3688
- edge/class-method: test method inside a class is NOT flagged (pytest collects it)
- edge/nested-class: test method inside a nested class (class in class) is NOT flagged
- edge/invalid-root: non-existent root -> exit 2
- edge/empty-tree: no test files -> exit 0 (not vacuous: scans the given root)
- meta: running the gate against its own fixture with negative-control finds >= 1 finding
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "validation" / "check_nested_tests.py"
_VALIDATION_DIR = REPO_ROOT / "scripts" / "validation"
if str(_VALIDATION_DIR) not in sys.path:
    sys.path.insert(0, str(_VALIDATION_DIR))

from check_nested_tests import (  # noqa: E402
    _NestedTestFinder,
    _walk_test_files,
    find_nested_tests,
)


def _git_repo(root: Path) -> None:
    """Initialise a bare git repo and stage all files so git ls-files sees them."""
    subprocess.run(["git", "init", "-q", str(root)], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(root), "config", "user.email", "t@test.invalid"],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "-C", str(root), "config", "user.name", "Test"], check=True, capture_output=True
    )
    subprocess.run(["git", "-C", str(root), "add", "-A"], check=True, capture_output=True)


def _write_test_file(root: Path, name: str, content: str) -> Path:
    path = root / name
    path.write_text(content, encoding="utf-8")
    return path


def _run_cli(repo_root: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), str(repo_root)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )


# ---------------------------------------------------------------------------
# Positive: clean tree
# ---------------------------------------------------------------------------


def test_clean_tree_passes(tmp_path: Path) -> None:
    """A test file with only module-level and class-level tests returns exit 0."""
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    _write_test_file(
        tests_dir,
        "test_clean.py",
        "def test_at_module_level():\n    assert True\n\n"
        "class TestGroup:\n    def test_as_method(self):\n        assert True\n",
    )
    _git_repo(tmp_path)

    result = _run_cli(tmp_path)

    assert result.returncode == 0, result.stderr
    assert find_nested_tests(tmp_path) == []


def test_no_test_files_passes(tmp_path: Path) -> None:
    """A repo with no test files returns exit 0 (not vacuous: root scanned)."""
    (tmp_path / "scripts").mkdir()
    _write_test_file(tmp_path / "scripts", "helper.py", "def helper(): pass\n")
    _git_repo(tmp_path)

    result = _run_cli(tmp_path)

    assert result.returncode == 0, result.stderr


# ---------------------------------------------------------------------------
# Negative: nested test function detected
# ---------------------------------------------------------------------------

_NESTED_IN_FUNCTION = """\
def _helper(tmp_path):
    def test_something_nested(self):
        assert True
    return _helper
"""

_NESTED_ASYNC = """\
def _setup():
    async def test_async_nested():
        pass
"""

_NESTED_TWO_LEVELS = """\
def outer():
    def inner():
        def test_deep():
            pass
"""


def test_nested_in_function_fails(tmp_path: Path) -> None:
    """A test function inside a helper function -> exit 1, reports the line."""
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    _write_test_file(tests_dir, "test_nested.py", _NESTED_IN_FUNCTION)
    _git_repo(tmp_path)

    result = _run_cli(tmp_path)

    assert result.returncode == 1
    assert "test_nested.py" in result.stderr
    assert "test_something_nested" in result.stderr

    findings = find_nested_tests(tmp_path)
    assert len(findings) == 1
    path, lineno, name = findings[0]
    assert path.name == "test_nested.py"
    assert name == "test_something_nested"
    assert lineno == 2


def test_nested_async_function_caught(tmp_path: Path) -> None:
    """An async test function nested inside a function is also caught."""
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    _write_test_file(tests_dir, "test_async.py", _NESTED_ASYNC)
    _git_repo(tmp_path)

    findings = find_nested_tests(tmp_path)

    assert len(findings) == 1
    _, _, name = findings[0]
    assert name == "test_async_nested"


def test_nested_two_levels_caught(tmp_path: Path) -> None:
    """A test function nested two function levels deep is also caught."""
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    _write_test_file(tests_dir, "test_deep.py", _NESTED_TWO_LEVELS)
    _git_repo(tmp_path)

    findings = find_nested_tests(tmp_path)

    assert len(findings) == 1
    _, _, name = findings[0]
    assert name == "test_deep"


# ---------------------------------------------------------------------------
# Negative control: the gate catches the exact PR #3688 shape
# ---------------------------------------------------------------------------

_PR3688_SHAPE = """\
def _repo_where_a_rename_repadded_the_number(tmp_path, renamed_to):
    repo = tmp_path / "repo"
    repo.mkdir()
    return repo, "after", "before"


    def test_blob_readers_do_not_normalise_line_endings(self, tmp_path):
        pass

    def test_head_copy_lookup_crosses_a_rename(self, tmp_path):
        pass
"""


def test_negative_control_pr3688_shape(tmp_path: Path) -> None:
    """The gate finds the exact indentation shape from PR #3688 (issue #3879).

    This is the meta-requirement: the gate must not pass vacuously. It must
    report at least one finding on the pattern that caused the regression.
    """
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    _write_test_file(tests_dir, "test_regression.py", _PR3688_SHAPE)
    _git_repo(tmp_path)

    findings = find_nested_tests(tmp_path)

    assert len(findings) >= 1, (
        "Gate passed vacuously: expected at least one finding on the PR #3688 shape"
    )
    names = [name for _, _, name in findings]
    assert "test_blob_readers_do_not_normalise_line_endings" in names


# ---------------------------------------------------------------------------
# Edge: class-level methods are NOT flagged
# ---------------------------------------------------------------------------

_CLASS_METHODS = """\
class TestSomething:
    def test_method(self):
        assert True

    class TestNested:
        def test_nested_class_method(self):
            assert True
"""


def test_class_methods_not_flagged(tmp_path: Path) -> None:
    """Test methods inside classes (and nested classes) are NOT flagged.

    pytest collects both shapes. The discriminator is function-nesting only.
    """
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    _write_test_file(tests_dir, "test_class.py", _CLASS_METHODS)
    _git_repo(tmp_path)

    findings = find_nested_tests(tmp_path)

    assert findings == [], f"Unexpected findings: {findings}"


# ---------------------------------------------------------------------------
# Edge: invalid repo root
# ---------------------------------------------------------------------------


def test_invalid_root_exits_2(tmp_path: Path) -> None:
    """A non-existent root directory returns exit code 2 (config error)."""
    result = _run_cli(tmp_path / "does_not_exist")
    assert result.returncode == 2


# ---------------------------------------------------------------------------
# Unit-level: _NestedTestFinder
# ---------------------------------------------------------------------------


def test_finder_empty_module() -> None:
    """An empty module produces no findings."""
    import ast

    tree = ast.parse("")
    finder = _NestedTestFinder()
    finder.visit(tree)
    assert finder.findings == []


def test_finder_module_level_test() -> None:
    """A module-level test function is not flagged."""
    import ast

    tree = ast.parse("def test_ok(): pass\n")
    finder = _NestedTestFinder()
    finder.visit(tree)
    assert finder.findings == []


def test_finder_directly_nested() -> None:
    """A test directly inside a function body is flagged with the right line."""
    import ast

    src = "def helper():\n    def test_nested(): pass\n"
    tree = ast.parse(src)
    finder = _NestedTestFinder()
    finder.visit(tree)
    assert len(finder.findings) == 1
    lineno, name = finder.findings[0]
    assert name == "test_nested"
    assert lineno == 2


def test_finder_non_test_nested_not_flagged() -> None:
    """A helper (non-test_) function nested inside a function is not flagged."""
    import ast

    src = "def outer():\n    def inner_helper(): pass\n"
    tree = ast.parse(src)
    finder = _NestedTestFinder()
    finder.visit(tree)
    assert finder.findings == []


def test_walk_test_files_skips_venv(tmp_path: Path) -> None:
    """The filesystem walk skips virtualenv directories."""
    venv_dir = tmp_path / ".venv" / "lib"
    venv_dir.mkdir(parents=True)
    (venv_dir / "test_vendored.py").write_text("def test_skip(): pass\n", encoding="utf-8")
    real_dir = tmp_path / "tests"
    real_dir.mkdir()
    (real_dir / "test_real.py").write_text("def test_keep(): pass\n", encoding="utf-8")

    found = _walk_test_files(tmp_path)

    paths = [p.name for p in found]
    assert "test_real.py" in paths
    assert "test_vendored.py" not in paths
