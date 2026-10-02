"""Unit tests for the import-graph builder and its cache."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from scripts.test_selection import import_graph


def _write(root: Path, rel: str, text: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _make_repo(root: Path) -> None:
    _write(root, "pyproject.toml", "[project]\nname = 'demo'\n")
    _write(root, "pkg/__init__.py", "")
    _write(root, "pkg/core.py", "VALUE = 1\n")
    _write(root, "pkg/mid.py", "from pkg import core\n")
    _write(root, "tests/test_feature.py", "from pkg import mid\n")


def test_build_graph_maps_direct_import(tmp_path: Path) -> None:
    _make_repo(tmp_path)
    graph = import_graph.build_graph(tmp_path)
    assert "pkg/core.py" in graph["pkg/mid.py"]


def test_build_graph_maps_from_import_to_test(tmp_path: Path) -> None:
    _make_repo(tmp_path)
    graph = import_graph.build_graph(tmp_path)
    assert "pkg/mid.py" in graph["tests/test_feature.py"]


def test_build_graph_maps_literal_dynamic_import(tmp_path: Path) -> None:
    _make_repo(tmp_path)
    _write(
        tmp_path,
        "tests/test_dynamic.py",
        'import importlib\nMODULE = importlib.import_module("pkg.core")\n',
    )
    graph = import_graph.build_graph(tmp_path)
    assert "pkg/core.py" in graph["tests/test_dynamic.py"]


def test_build_graph_data_marks_wildcard_dynamic_imports(tmp_path: Path) -> None:
    _make_repo(tmp_path)
    _write(
        tmp_path,
        "tests/test_dynamic.py",
        "import importlib\nname = 'pkg.core'\nMODULE = importlib.import_module(name)\n",
    )
    graph_data = import_graph.build_graph_data(tmp_path)
    assert graph_data.wildcard_dependents == frozenset({"tests/test_dynamic.py"})


def test_reverse_graph_inverts_edges(tmp_path: Path) -> None:
    _make_repo(tmp_path)
    reverse = import_graph.reverse_graph(import_graph.build_graph(tmp_path))
    assert reverse["pkg/core.py"] == {"pkg/mid.py"}


def test_affected_closure_is_transitive(tmp_path: Path) -> None:
    _make_repo(tmp_path)
    reverse = import_graph.reverse_graph(import_graph.build_graph(tmp_path))
    affected = import_graph.affected_closure(["pkg/core.py"], reverse)
    assert affected == {"pkg/core.py", "pkg/mid.py", "tests/test_feature.py"}


def test_affected_closure_includes_changed_file(tmp_path: Path) -> None:
    reverse = import_graph.reverse_graph(import_graph.build_graph(tmp_path))
    assert import_graph.affected_closure(["orphan.py"], reverse) == {"orphan.py"}


def test_python_files_skips_cache_dirs(tmp_path: Path) -> None:
    _write(tmp_path, "pkg/real.py", "x = 1\n")
    _write(tmp_path, ".cache/stale.py", "x = 1\n")
    _write(tmp_path, "node_modules/dep/mod.py", "x = 1\n")
    _write(tmp_path, "pkg/__pycache__/real.cpython.py", "x = 1\n")
    rels = {p.relative_to(tmp_path).as_posix() for p in import_graph.python_files(tmp_path)}
    assert rels == {"pkg/real.py"}


def test_python_files_skips_nested_worktrees(tmp_path: Path) -> None:
    _write(tmp_path, "scripts/keep.py", "x = 1\n")
    _write(tmp_path, "scripts/worktrees/scratch.py", "x = 1\n")
    rels = {p.relative_to(tmp_path).as_posix() for p in import_graph.python_files(tmp_path)}
    assert rels == {"scripts/keep.py"}


def test_build_graph_raises_on_syntax_error(tmp_path: Path) -> None:
    _write(tmp_path, "broken.py", "def (:\n")
    with pytest.raises(RuntimeError, match="Cannot parse"):
        import_graph.build_graph(tmp_path)


def test_load_or_build_writes_cache(tmp_path: Path) -> None:
    _make_repo(tmp_path)
    cache = tmp_path / ".cache" / "graph.json"
    import_graph.load_or_build(tmp_path, cache)
    assert cache.is_file()


def test_load_or_build_reuses_fresh_cache(tmp_path: Path) -> None:
    _make_repo(tmp_path)
    cache = tmp_path / ".cache" / "graph.json"
    import_graph.load_or_build(tmp_path, cache)
    # Corrupt the on-disk graph, then confirm a fresh cache is trusted verbatim
    # instead of being rebuilt from the sources.
    cache.write_text(
        (
            f'{{"version": {import_graph.CACHE_VERSION}, '
            '"graph": {"sentinel.py": ["marker.py"]}, '
            '"wildcard_dependents": ["tests/test_dynamic.py"], '
            '"string_literals": {"tests/test_read.py": ["AGENTS.md"]}, '
            '"tree_walkers": ["tests/test_walk.py"]}'
        ),
        encoding="utf-8",
    )
    future = import_graph._newest_source_mtime(tmp_path) + 100
    os.utime(cache, (future, future))
    graph_data = import_graph.load_or_build_data(tmp_path, cache)
    assert graph_data.graph == {"sentinel.py": frozenset({"marker.py"})}
    assert graph_data.wildcard_dependents == frozenset({"tests/test_dynamic.py"})
    assert graph_data.string_literals == {"tests/test_read.py": frozenset({"AGENTS.md"})}
    assert graph_data.tree_walkers == frozenset({"tests/test_walk.py"})


def test_cache_without_read_signals_is_rebuilt(tmp_path: Path) -> None:
    _make_repo(tmp_path)
    cache = tmp_path / ".cache" / "graph.json"
    import_graph.load_or_build(tmp_path, cache)
    cache.write_text(
        f'{{"version": {import_graph.CACHE_VERSION}, "graph": {{"sentinel.py": []}}}}',
        encoding="utf-8",
    )
    future = import_graph._newest_source_mtime(tmp_path) + 100
    os.utime(cache, (future, future))
    graph_data = import_graph.load_or_build_data(tmp_path, cache)
    assert "sentinel.py" not in graph_data.graph


@pytest.mark.parametrize(
    ("source", "walks"),
    [
        ("import pathlib\nlist(pathlib.Path('.').rglob('*.md'))\n", True),
        ("import glob\nglob.glob('*.md')\n", True),
        ("from glob import glob\nglob('*.md')\n", True),
        ("import os\nlist(os.walk('.'))\n", True),
        ("import os\nos.listdir('.')\nos.scandir('.')\n", True),
        ("from pathlib import Path\nPath('.').iterdir()\n", True),
        ("import subprocess\nsubprocess.run(['git', 'ls-files'])\n", True),
        ("from pathlib import Path\nPath('AGENTS.md').read_text()\n", False),
    ],
)
def test_read_signals_detect_tree_walks(source: str, walks: bool) -> None:
    import ast

    _, found = import_graph._read_signals(ast.parse(source))
    assert found is walks


def test_read_signals_keep_path_like_literals_only() -> None:
    import ast

    keep = "k" * 299
    drop = "z" * 300
    tree = ast.parse(f"a = 'AGENTS.md'\nb = 'x'\nc = 'two\\nlines'\nd = '{drop}'\ne = '{keep}'\n")
    literals, _ = import_graph._read_signals(tree)
    assert literals == frozenset({"AGENTS.md", keep})


def test_build_records_literals_and_walkers(tmp_path: Path) -> None:
    _write(tmp_path, "tests/test_read.py", "open('AGENTS.md')\n")
    _write(tmp_path, "tests/test_walk.py", "import pathlib\npathlib.Path('.').rglob('*.md')\n")
    data = import_graph.build_graph_data(tmp_path)
    assert "AGENTS.md" in data.string_literals["tests/test_read.py"]
    assert data.tree_walkers == frozenset({"tests/test_walk.py"})


def test_cache_stale_when_source_is_newer(tmp_path: Path) -> None:
    _make_repo(tmp_path)
    cache = tmp_path / ".cache" / "graph.json"
    import_graph.load_or_build(tmp_path, cache)
    assert import_graph.is_cache_fresh(tmp_path, cache)
    future = cache.stat().st_mtime + 100
    os.utime(tmp_path / "pkg" / "core.py", (future, future))
    assert not import_graph.is_cache_fresh(tmp_path, cache)


def test_cache_stale_when_pyproject_is_newer(tmp_path: Path) -> None:
    _make_repo(tmp_path)
    cache = tmp_path / ".cache" / "graph.json"
    import_graph.load_or_build(tmp_path, cache)
    future = cache.stat().st_mtime + 100
    os.utime(tmp_path / "pyproject.toml", (future, future))
    assert not import_graph.is_cache_fresh(tmp_path, cache)


def test_stale_cache_rebuilds_with_new_edge(tmp_path: Path) -> None:
    _make_repo(tmp_path)
    cache = tmp_path / ".cache" / "graph.json"
    import_graph.load_or_build(tmp_path, cache)
    _write(tmp_path, "pkg/mid.py", "from pkg import core\nimport pkg.extra\n")
    _write(tmp_path, "pkg/extra.py", "y = 2\n")
    future = cache.stat().st_mtime + 100
    for rel in ("pkg/mid.py", "pkg/extra.py"):
        os.utime(tmp_path / rel, (future, future))
    graph = import_graph.load_or_build(tmp_path, cache)
    assert "pkg/extra.py" in graph["pkg/mid.py"]


def test_missing_cache_is_not_fresh(tmp_path: Path) -> None:
    assert not import_graph.is_cache_fresh(tmp_path, tmp_path / "absent.json")
