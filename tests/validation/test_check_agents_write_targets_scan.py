"""Equivalence tests for the issue #6734 speedup of the .agents write-target gate.

``scan_python`` skips its AST walks when no finding is possible, and
``check_repository`` fans the scan out to worker processes. Both must return
exactly what the single-process, unfiltered scan returned.
"""

from __future__ import annotations

import ast
import subprocess
import sys
from concurrent.futures.process import BrokenProcessPool
from pathlib import Path

import pytest

VALIDATION = Path(__file__).resolve().parents[2] / "scripts" / "validation"
if str(VALIDATION) not in sys.path:
    sys.path.insert(0, str(VALIDATION))

import check_agents_write_targets as checker
import ordered_process_pool as pool_module
from agents_spelling_prefilter import may_name_agents
from ordered_process_pool import scan_in_processes, split_batches


def _init_repo(tmp_path: Path, files: dict[str, str]) -> Path:
    """Create a tmp git repo with the given files staged (no commit needed)."""
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    for relative, content in files.items():
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        subprocess.run(["git", "add", relative], cwd=tmp_path, check=True)
    return tmp_path


def _reference_scan_python(path: str, text: str) -> list[checker.Finding]:
    """The scan_python body from before the prefilter: parse, walk, and scan every file."""
    tree = ast.parse(text, filename=path)
    variables = checker._single_assigned_paths(tree)
    visitor = checker._PythonAgentsScan(path, variables)
    visitor.visit(tree)
    lines = text.splitlines()
    unique = {(item.line, item.reason): item for item in visitor.findings}
    literal_findings = (
        [] if path.startswith(checker._TEST_PREFIX) else checker._stale_line_findings(path, lines)
    )
    for item in literal_findings:
        unique.setdefault((item.line, item.reason), item)
    return [item for item in unique.values() if not checker._line_opted_out(lines, item.line)]


_IMPORT = "from pathlib import Path\n"

# Each source names a stale or written .agents path without the substring ".agents".
_HIDDEN_AGENTS_SOURCES = [
    pytest.param(_IMPORT + 'Path("\\x2eagents/sessions/x")\n', id="hex-escape"),
    pytest.param(_IMPORT + 'Path("\\u002eagents/sessions/x")\n', id="u-escape"),
    pytest.param(_IMPORT + 'Path("\\U0000002eagents/sessions/x")\n', id="big-u-escape"),
    pytest.param(_IMPORT + 'Path("\\N{FULL STOP}agents/sessions/x")\n', id="named-escape"),
    pytest.param(_IMPORT + 'Path("\\056agents/sessions/x")\n', id="octal-escape"),
    pytest.param(_IMPORT + 'Path("\\x2eagent\\x73/sessions/x")\n', id="two-escapes"),
    pytest.param(_IMPORT + 'Path(".age" "nts/sessions/x")\n', id="implicit-concat"),
    pytest.param(
        _IMPORT + 'Path(\n    ".a"  # why\n    "gents"\n    "/sessions/x"\n)\n',
        id="concat-with-comment",
    ),
    pytest.param(_IMPORT + 'Path(r".age" u"nts/sessions/x")\n', id="concat-with-prefixes"),
    pytest.param(_IMPORT + 'Path(".age\\\nnts/sessions/x")\n', id="line-continuation"),
    pytest.param(_IMPORT + 'Path(""".""" "agents/sessions/x")\n', id="triple-quote-concat"),
    pytest.param(
        _IMPORT + 'Path("\\x2eagents/governance/x").write_text("a")\n', id="hidden-keep-write"
    ),
]


@pytest.mark.parametrize("source", _HIDDEN_AGENTS_SOURCES)
def test_hidden_agents_spelling_still_gets_the_full_scan(source: str) -> None:
    """A bare '.agents' substring skip would return [] here and miss the finding."""
    assert ".agents" not in source
    assert may_name_agents(source)
    findings = checker.scan_python("scripts/example.py", source)
    assert findings
    assert findings == _reference_scan_python("scripts/example.py", source)


@pytest.mark.parametrize(
    "source",
    [
        pytest.param("x = 1\n", id="plain"),
        pytest.param('GREEN = "\\x1b[32m"\nPATTERN = r"\\d+\\s*"\n', id="other-escapes"),
        pytest.param('"""Prose, e.g.\nagents write here."""\nx = 1\n', id="prose-across-lines"),
        pytest.param('self.assert_called()\nitems = [".a", "b"]\n', id="near-miss"),
        pytest.param('NAME = "agents"\nDIR = "."\n', id="pieces-in-separate-statements"),
    ],
)
def test_source_without_any_agents_spelling_skips_the_walks(source: str) -> None:
    assert not may_name_agents(source)
    assert checker.scan_python("scripts/example.py", source) == []
    assert _reference_scan_python("scripts/example.py", source) == []


def test_syntax_error_without_agents_text_still_fails_the_scan() -> None:
    """The skip must not drop the parse: a broken file failed before and still must."""
    source = "def broken(:\n    pass\n"
    assert not may_name_agents(source)
    with pytest.raises(SyntaxError):
        checker.scan_python("scripts/broken.py", source)
    with pytest.raises(SyntaxError):
        _reference_scan_python("scripts/broken.py", source)


def test_marker_text_without_agents_substring_is_still_scanned() -> None:
    source = "x = 1  # agents-write-target: historical\n"
    assert may_name_agents(source)
    findings = checker.scan_python("scripts/example.py", source)
    assert [f.reason for f in findings] == [checker._MARKER_MISSING_REASON]
    assert findings == _reference_scan_python("scripts/example.py", source)


def test_prefilter_matches_the_unfiltered_scan_on_real_sources() -> None:
    root = Path(__file__).resolve().parents[2]
    paths = sorted((root / "scripts" / "validation").glob("*.py")) + sorted(
        (root / "tests" / "validation").glob("*.py")
    )
    scanned = 0
    for path in paths:
        relative = path.relative_to(root).as_posix()
        if relative in (checker._SELF_TEST, checker._SELF_SOURCE):
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        assert checker.scan_python(relative, text) == _reference_scan_python(relative, text), (
            relative
        )
        scanned += 1
    assert scanned > 50


_MIXED_CORPUS = {
    "scripts/a_stale.py": _IMPORT + 'Path(".agents/sessions/x")\n',
    "scripts/b_clean.py": "x = 1\n",
    "scripts/c_hidden.py": _IMPORT + 'Path("\\x2eagents/sessions/x")\n',
    "scripts/d_write.py": _IMPORT + 'Path(".agents/governance/x").write_text("a")\n',
    "docs/e.md": "Save to `.agents/governance/x`.\n",
    "docs/f.md": "Nothing here.\n",
    "tests/g_test.py": "open('.agents/governance/x', 'w')\n",
    "scripts/h_clean.py": "y = 2\n",
}


def _items(corpus: dict[str, str]) -> list[tuple[str, str]]:
    return list(corpus.items())


def test_parallel_scan_returns_the_serial_findings() -> None:
    items = _items(_MIXED_CORPUS)
    serial = checker._scan_candidates(items)
    assert len(serial) == 5
    assert scan_in_processes(checker._scan_candidates, items, 2) == serial


def test_check_repository_uses_the_pool_for_large_input(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    repo = _init_repo(tmp_path, _MIXED_CORPUS)
    expected, examined = checker.check_repository(repo)
    monkeypatch.setattr(pool_module, "MIN_BYTES", 0)
    monkeypatch.setattr(pool_module.os, "process_cpu_count", lambda: 4)
    calls: list[int] = []
    real = checker.scan_in_processes

    def spy(scan: object, items: list[tuple[str, str]], workers: int) -> list[checker.Finding]:
        calls.append(workers)
        return real(scan, items, workers)

    monkeypatch.setattr(checker, "scan_in_processes", spy)

    assert checker.check_repository(repo) == (expected, examined)
    assert calls == [4]
    assert len(expected) == 5


def test_check_repository_stays_in_process_for_small_input_or_one_cpu(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    repo = _init_repo(tmp_path, _MIXED_CORPUS)

    def boom(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("pool must not start")

    monkeypatch.setattr(pool_module, "ProcessPoolExecutor", boom)
    assert len(checker.check_repository(repo)[0]) == 5  # below the byte threshold
    monkeypatch.setattr(pool_module, "MIN_BYTES", 0)
    monkeypatch.setattr(pool_module.os, "process_cpu_count", lambda: 1)
    assert len(checker.check_repository(repo)[0]) == 5  # one CPU


def test_parallel_scan_raises_the_first_syntax_error_in_input_order() -> None:
    items = [
        ("scripts/a_ok.py", "x = 1\n"),
        ("scripts/b_bad.py", "def first(:\n"),
        ("scripts/c_ok.py", "y = 2\n"),
        ("scripts/d_bad.py", "def second(:\n"),
    ]
    with pytest.raises(SyntaxError) as serial:
        checker._scan_candidates(items)
    with pytest.raises(SyntaxError) as parallel:
        scan_in_processes(checker._scan_candidates, items, 4)
    assert "b_bad.py" in str(parallel.value)
    assert str(parallel.value) == str(serial.value)


def test_syntax_error_in_pool_fails_the_validator_closed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    repo = _init_repo(tmp_path, {**_MIXED_CORPUS, "scripts/z_bad.py": "def broken(:\n"})
    monkeypatch.setattr(pool_module, "MIN_BYTES", 0)
    monkeypatch.setattr(pool_module.os, "process_cpu_count", lambda: 2)
    assert checker.validate_agents_write_targets(repo) is False
    assert checker.main(["--repo-root", str(repo)]) == 2


def test_broken_pool_falls_back_to_the_serial_findings(monkeypatch: pytest.MonkeyPatch) -> None:
    items = _items(_MIXED_CORPUS)

    class DeadPool:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            raise BrokenProcessPool("pool died")

    monkeypatch.setattr(pool_module, "ProcessPoolExecutor", DeadPool)
    assert scan_in_processes(checker._scan_candidates, items, 2) == checker._scan_candidates(items)


def test_missing_forkserver_falls_back_to_the_serial_findings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def no_context(_method: str) -> None:
        raise ValueError("cannot find context for 'forkserver'")

    monkeypatch.setattr(pool_module.multiprocessing, "get_context", no_context)
    items = _items(_MIXED_CORPUS)
    assert scan_in_processes(checker._scan_candidates, items, 2) == checker._scan_candidates(items)


@pytest.mark.parametrize("count", [1, 2, 3, 8, 32])
def test_batches_keep_input_order_and_cover_every_item(count: int) -> None:
    items = [(f"scripts/f{i}.py", "x" * (i * 7 % 50)) for i in range(20)]
    batches = split_batches(items, count)
    assert 1 <= len(batches) <= count
    assert [item for batch in batches for item in batch] == items
    assert all(batches)


def test_batches_of_empty_input_is_one_empty_batch() -> None:
    assert split_batches([], 4) == [[]]


def test_deep_chain_without_agents_text_no_longer_crashes_the_visitor() -> None:
    """The one input class whose outcome changes: the old visitor hit RecursionError.

    A 400-term ``"a" + "a" + ...`` chain parses fine but nests past the visitor's
    recursion budget, so the unfiltered scan crashed the gate on a file that cannot
    hold a finding. The skip returns the verdict the file deserves: no findings.
    """
    source = "x = " + " + ".join(['"a"'] * 400) + "\n"
    assert not may_name_agents(source)
    with pytest.raises(RecursionError):
        _reference_scan_python("scripts/deep.py", source)
    assert checker.scan_python("scripts/deep.py", source) == []
