"""Equivalence tests for the faster nested-test gate (issue #6734).

The gate in scripts/validation/check_nested_tests.py now skips expression
subtrees and scans large trees in child interpreters. These tests pin that the
verdict, the finding order, and the skip rules match the pre-#6734 gate.

- pos/neg: pruned finder equals the old finder on every construct that can hold a def
- equiv/real: same findings as the old finder on real repo code, every function renamed test_*
- parallel: findings and order equal a serial scan for 2, 3, 7 workers
- fallback: a crashed, timed-out, or malformed worker never drops a file and warns
- meta: the parallel path is really taken (no silent fallback hiding a dead worker)
"""

from __future__ import annotations

import ast
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "validation" / "check_nested_tests.py"
_VALIDATION_DIR = REPO_ROOT / "scripts" / "validation"
if str(_VALIDATION_DIR) not in sys.path:
    sys.path.insert(0, str(_VALIDATION_DIR))

import check_nested_tests
from check_nested_tests import _NestedTestFinder, find_nested_tests


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


def _track_all(root: Path) -> None:
    """Make ``root`` a git repo with every file staged, so git ls-files lists them."""
    subprocess.run(["git", "init", "-q", str(root)], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(root), "add", "-A"], check=True, capture_output=True)


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
    _track_all(root)


def test_parallel_scan_matches_serial_scan(tmp_path: Path) -> None:
    """Same findings, same order, for 2, 3, and 7 workers.

    Interleaved chunking reorders work, so a missing reassembly step would
    return findings grouped by worker instead of by file.
    """
    _build_tree(tmp_path, count=150, nested_every=7)

    serial = find_nested_tests(tmp_path, workers=1)

    assert len(serial) == 22
    assert [path.name for path, _, _ in serial] == sorted(path.name for path, _, _ in serial)
    for workers in (2, 3, 7):
        assert find_nested_tests(tmp_path, workers=workers) == serial


def test_parallel_scan_runs_in_workers_without_falling_back(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The speedup is real: no chunk is re-scanned in-process and no warning prints.

    A dead worker falls back to a serial scan with the right answer, so output
    equality alone cannot tell the two apart. Counting in-process scans can.
    """
    _build_tree(tmp_path, count=140, nested_every=9)
    expected = find_nested_tests(tmp_path, workers=1)
    in_process_scans: list[int] = []
    real_scan_serial = check_nested_tests._scan_serial

    def counting_scan_serial(paths: list[Path]) -> list[list[tuple[int, str]] | None]:
        in_process_scans.append(len(paths))
        return real_scan_serial(paths)

    monkeypatch.setattr(check_nested_tests, "_scan_serial", counting_scan_serial)

    assert find_nested_tests(tmp_path, workers=4) == expected
    assert in_process_scans == []
    assert "[WARN]" not in capsys.readouterr().err


def test_automatic_worker_count_uses_workers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Above the file threshold the default path picks workers, whatever the CPU count."""
    _build_tree(tmp_path, count=check_nested_tests._PARALLEL_MIN_FILES + 5, nested_every=11)
    expected = find_nested_tests(tmp_path, workers=1)
    monkeypatch.setattr(check_nested_tests, "_worker_count", lambda file_count: 3)
    used: list[int] = []
    real_parallel = check_nested_tests._scan_parallel

    def recording_parallel(paths: list[Path], workers: int) -> list[list[tuple[int, str]] | None]:
        used.append(workers)
        return real_parallel(paths, workers)

    monkeypatch.setattr(check_nested_tests, "_scan_parallel", recording_parallel)

    assert find_nested_tests(tmp_path) == expected
    assert used == [3]


def test_small_tree_stays_in_process(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Below the file threshold no worker starts."""
    _build_tree(tmp_path, count=5, nested_every=2)

    def refuse(paths: list[Path], workers: int) -> list[list[tuple[int, str]] | None]:
        raise AssertionError("small tree must not start workers")

    monkeypatch.setattr(check_nested_tests, "_scan_parallel", refuse)

    assert len(find_nested_tests(tmp_path)) == 3


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
    assert findings[0][1:] == (2, "test_nested_0")


def _failing_run(failure: str) -> Callable[..., subprocess.CompletedProcess[str]]:
    def fake_run(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        if failure == "raises":
            raise OSError("cannot spawn")
        if failure == "timeout":
            raise subprocess.TimeoutExpired(cmd, 1)
        stdout = {
            "nonzero": "[]",
            "garbage": "not json",
            "short": "[]",
            "bad-entry": "[[[1]], null]",
            "bad-shape": '{"a": 1}',
        }[failure]
        returncode = 1 if failure == "nonzero" else 0
        return subprocess.CompletedProcess(cmd, returncode, stdout=stdout, stderr="")

    return fake_run


@pytest.mark.parametrize(
    "failure", ["raises", "timeout", "nonzero", "garbage", "short", "bad-entry", "bad-shape"]
)
def test_worker_failure_falls_back_to_serial_scan(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    failure: str,
) -> None:
    """A dead, wrong, truncated, or slow worker never drops files and says so."""
    _build_tree(tmp_path, count=140, nested_every=5)
    paths = check_nested_tests._tracked_test_files(tmp_path)
    expected = check_nested_tests._scan_serial(paths)
    monkeypatch.setattr(check_nested_tests.subprocess, "run", _failing_run(failure))

    assert check_nested_tests._scan_parallel(paths, 4) == expected
    assert capsys.readouterr().err.count("[WARN] nested-test scan worker failed") == 4


def test_worker_parser_warnings_reach_stderr(tmp_path: Path) -> None:
    """A SyntaxWarning raised while parsing in a worker is shown, as it is in-process."""
    _build_tree(tmp_path, count=140, nested_every=10**9)
    (tmp_path / "tests" / "pkg" / "test_escape.py").write_text(
        'PATTERN = "\\d+"\n', encoding="utf-8"
    )
    _track_all(tmp_path)
    paths = check_nested_tests._tracked_test_files(tmp_path)

    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; sys.path.insert(0, sys.argv[1]); import check_nested_tests as m; "
            "from pathlib import Path; "
            "m.find_nested_tests(Path(sys.argv[2]), workers=2)",
            str(_VALIDATION_DIR),
            str(tmp_path),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )

    assert paths
    assert result.returncode == 0
    assert "test_escape.py" in result.stderr
    assert "invalid escape sequence" in result.stderr


def test_cli_verdict_unchanged_for_large_tree(tmp_path: Path) -> None:
    """End to end: exit 1 and every offending file named when the tree is large."""
    _build_tree(tmp_path, count=140, nested_every=20)

    result = subprocess.run(
        [sys.executable, str(SCRIPT), str(tmp_path)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )

    assert result.returncode == 1
    assert "test_f0000.py:2  test_nested_0()" in result.stderr
    assert "test_f0120.py:2  test_nested_120()" in result.stderr
    assert "test_f0001.py" not in result.stderr
