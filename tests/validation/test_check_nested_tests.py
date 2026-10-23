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

import ast
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "validation" / "check_nested_tests.py"
_VALIDATION_DIR = REPO_ROOT / "scripts" / "validation"
if str(_VALIDATION_DIR) not in sys.path:
    sys.path.insert(0, str(_VALIDATION_DIR))

import check_nested_tests
from check_nested_tests import (
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


# ---------------------------------------------------------------------------
# Equivalence: the pruned finder and the parallel scan keep the old verdicts
# (issue #6734)
# ---------------------------------------------------------------------------


class _ReferenceFinder(ast.NodeVisitor):
    """The pre-#6734 finder, verbatim: visits every node, expressions included."""

    def __init__(self) -> None:
        self.findings: list[tuple[int, str]] = []
        self._func_depth = 0

    def _visit_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        if node.name.startswith("test_") and self._func_depth > 0:
            self.findings.append((node.lineno, node.name))
        self._func_depth += 1
        self.generic_visit(node)
        self._func_depth -= 1

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._visit_function(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._visit_function(node)


def _findings(finder_type: type, source: str) -> list[tuple[int, str]]:
    finder = finder_type()
    finder.visit(ast.parse(source))
    return finder.findings


_SHAPES = {
    "direct": "def f():\n    def test_a(): pass\n",
    "async": "async def f():\n    async def test_a(): pass\n",
    "in-if": (
        "def f():\n    if x:\n        def test_a(): pass\n    else:\n        def test_b(): pass\n"
    ),
    "in-for-else": (
        "def f():\n    for i in x:\n        pass\n    else:\n        def test_a(): pass\n"
    ),
    "in-while": "def f():\n    while x:\n        def test_a(): pass\n",
    "in-with": "def f():\n    with x:\n        def test_a(): pass\n",
    "in-try": (
        "def f():\n    try:\n        def test_a(): pass\n    except E:\n"
        "        def test_b(): pass\n    else:\n        def test_c(): pass\n"
        "    finally:\n        def test_d(): pass\n"
    ),
    "in-try-star": (
        "def f():\n    try:\n        pass\n    except* E:\n        def test_a(): pass\n"
    ),
    "in-match": (
        "def f(v):\n    match v:\n        case 1:\n            def test_a(): pass\n"
        "        case _:\n            def test_b(): pass\n"
    ),
    "class-inside-function": ("def f():\n    class C:\n        def test_method(self): pass\n"),
    "function-in-method": ("class C:\n    def test_ok(self):\n        def test_inner(): pass\n"),
    "lambda-default-arg": ("def f(g=lambda: 1):\n    def test_a(): pass\n"),
    "lambda-in-decorator": (
        "@deco(lambda: 1)\ndef f():\n    @deco(key=lambda: [1])\n    def test_a(): pass\n"
    ),
    "comprehension-then-def": (
        "def f():\n    xs = [lambda: i for i in range(3)]\n    def test_a(): pass\n"
    ),
    "type-params": "def f[T: int]():\n    def test_a[U: str](): pass\n",
    "walrus-and-fstring": (
        "def f():\n    y = (z := 1)\n    s = f'{y!r:>{z}}'\n    def test_a(): pass\n"
    ),
    "clean-class": (
        "class T:\n    def test_a(self): pass\n    class I:\n        def test_b(self): pass\n"
    ),
    "clean-module": "def test_a(): pass\nasync def test_b(): pass\n",
    "helper-only": "def f():\n    def helper(): pass\n",
}


@pytest.mark.parametrize("shape", sorted(_SHAPES))
def test_pruned_finder_matches_reference(shape: str) -> None:
    """Skipping expression subtrees must not change any verdict."""
    source = _SHAPES[shape]
    assert _findings(_NestedTestFinder, source) == _findings(_ReferenceFinder, source)


@pytest.mark.parametrize(
    ("shape", "expected_count"),
    [
        ("direct", 1),
        ("in-if", 2),
        ("in-try", 4),
        ("in-match", 2),
        ("lambda-default-arg", 1),
        ("lambda-in-decorator", 1),
        ("comprehension-then-def", 1),
        ("clean-class", 0),
        ("clean-module", 0),
        ("helper-only", 0),
    ],
)
def test_pruned_finder_still_flags_nested_tests(shape: str, expected_count: int) -> None:
    """Pins absolute counts so a pruning bug cannot hide behind a matching reference."""
    assert len(_findings(_NestedTestFinder, _SHAPES[shape])) == expected_count


def test_pruned_finder_matches_reference_on_real_code() -> None:
    """Every function in real repo code, renamed test_*, gives the same findings.

    Renaming makes each nested function a finding, so this exercises the walk on
    thousands of real constructs instead of the handful in ``_SHAPES``.
    """
    paths = sorted((REPO_ROOT / "scripts" / "validation").glob("*.py"))[:60]
    assert paths
    compared = 0
    for path in paths:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                node.name = "test_" + node.name
        pruned = _NestedTestFinder()
        pruned.visit(tree)
        reference = _ReferenceFinder()
        reference.visit(tree)
        assert pruned.findings == reference.findings, path
        compared += len(reference.findings)
    assert compared > 0


_NESTED = "def helper():\n    def test_nested_{n}(): pass\n"
_CLEAN = "def test_ok_{n}(): pass\n"


def _build_tree(root: Path, count: int, nested_every: int) -> None:
    """Write ``count`` tracked test files; every ``nested_every``-th one is bad.

    Also writes one file that does not parse and one that is not UTF-8, both of
    which the gate has always skipped.
    """
    tests_dir = root / "tests" / "pkg"
    tests_dir.mkdir(parents=True)
    for n in range(count):
        template = _NESTED if n % nested_every == 0 else _CLEAN
        (tests_dir / f"test_f{n:04d}.py").write_text(template.format(n=n), encoding="utf-8")
    (tests_dir / "test_broken.py").write_text("def broken(:\n", encoding="utf-8")
    (tests_dir / "test_latin1.py").write_bytes(b"# \xe9\ndef f():\n    def test_x(): pass\n")
    _git_repo(root)


def test_parallel_scan_matches_serial_scan(tmp_path: Path) -> None:
    """Same findings, same order, for 1, 2, 3, and 7 workers.

    Interleaved chunking reorders work, so a missing reassembly step would
    return findings grouped by worker instead of by file.
    """
    _build_tree(tmp_path, count=150, nested_every=7)

    serial = find_nested_tests(tmp_path, workers=1)

    assert len(serial) == 22
    assert [path.name for path, _, _ in serial] == sorted(path.name for path, _, _ in serial)
    for workers in (2, 3, 7):
        assert find_nested_tests(tmp_path, workers=workers) == serial


def test_automatic_worker_count_matches_serial_scan(tmp_path: Path) -> None:
    """Above the file threshold the default path runs in workers and agrees."""
    _build_tree(tmp_path, count=check_nested_tests._PARALLEL_MIN_FILES + 5, nested_every=11)

    assert find_nested_tests(tmp_path) == find_nested_tests(tmp_path, workers=1)


def test_parallel_scan_reports_only_the_one_bad_file(tmp_path: Path) -> None:
    """One bad file among clean ones is the only finding: chunking invents none."""
    _build_tree(tmp_path, count=140, nested_every=10**9)

    findings = find_nested_tests(tmp_path, workers=4)

    assert [name for _, _, name in findings] == ["test_nested_0"]  # n=0 is always nested


def test_parallel_scan_keeps_line_numbers(tmp_path: Path) -> None:
    """Line numbers and names survive the JSON round trip through workers."""
    _build_tree(tmp_path, count=140, nested_every=1)

    findings = find_nested_tests(tmp_path, workers=4)

    assert len(findings) == 140  # test_broken.py and test_latin1.py are skipped
    first = findings[0]
    assert first[1:] == (2, "test_nested_0")


@pytest.mark.parametrize("failure", ["raises", "nonzero", "garbage", "short"])
def test_worker_failure_falls_back_to_serial_scan(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure: str
) -> None:
    """A dead, wrong, or truncated worker never drops files from the scan."""
    _build_tree(tmp_path, count=140, nested_every=5)
    expected = find_nested_tests(tmp_path, workers=1)
    real_run = subprocess.run

    def fake_run(cmd, *args, **kwargs):  # type: ignore[no-untyped-def]
        if "-I" not in cmd:
            return real_run(cmd, *args, **kwargs)
        if failure == "raises":
            raise OSError("cannot spawn")
        stdout = {"nonzero": "[]", "garbage": "not json", "short": "[]"}[failure]
        returncode = 1 if failure == "nonzero" else 0
        return subprocess.CompletedProcess(cmd, returncode, stdout=stdout, stderr="")

    monkeypatch.setattr(check_nested_tests.subprocess, "run", fake_run)

    assert find_nested_tests(tmp_path, workers=4) == expected


def test_cli_verdict_unchanged_for_large_tree(tmp_path: Path) -> None:
    """End to end: exit 1 and every offending file named when the tree is large."""
    _build_tree(tmp_path, count=140, nested_every=20)

    result = _run_cli(tmp_path)

    assert result.returncode == 1
    assert "test_f0000.py:2  test_nested_0()" in result.stderr
    assert "test_f0120.py:2  test_nested_120()" in result.stderr
    assert "test_f0001.py" not in result.stderr
