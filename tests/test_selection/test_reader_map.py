"""Tests for narrowing a test-input change to its readers (issue #5377)."""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.test_selection import import_graph, reader_map, select_tests


def _write(root: Path, rel: str, text: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _policy(root: Path) -> Path:
    path = root / "path_policy.yml"
    path.write_text("python:\n  - '**/*.md'\n  - '**/*.json'\n  - 'uv.lock'\n", encoding="utf-8")
    return path


def _make_repo(root: Path) -> None:
    _write(root, "pyproject.toml", "[project]\nname = 'demo'\n")
    _write(root, "pkg/__init__.py", "")
    _write(root, "pkg/helper.py", "NAME = 'AGENTS.md'\n")
    _write(root, "pkg/other.py", "VALUE = 1\n")
    _write(
        root, "tests/test_literal.py", "from pathlib import Path\nPath('AGENTS.md').read_text()\n"
    )
    _write(root, "tests/test_via_helper.py", "from pkg import helper\n")
    _write(root, "tests/test_unrelated.py", "from pkg import other\n")


def _select(root: Path, changed: list[str]) -> select_tests.Selection:
    cache = root / ".cache" / "graph.json"
    return select_tests.select(changed, root, cache, _policy(root))


def test_literal_reader_is_selected_and_unrelated_test_excluded(tmp_path: Path) -> None:
    _make_repo(tmp_path)
    result = _select(tmp_path, ["AGENTS.md"])
    assert not result.full
    assert result.reason == "test-input readers subset"
    assert "tests/test_literal.py" in result.tests
    assert "tests/test_via_helper.py" in result.tests
    assert "tests/test_unrelated.py" not in result.tests


def test_tree_walker_is_selected_for_every_path(tmp_path: Path) -> None:
    _make_repo(tmp_path)
    _write(
        tmp_path,
        "tests/test_walker.py",
        "from pathlib import Path\nlist(Path('.').rglob('*.md'))\n",
    )
    result = _select(tmp_path, ["docs/unrelated-guide.md"])
    assert not result.full
    assert "tests/test_walker.py" in result.tests
    assert "tests/test_literal.py" not in result.tests


def test_transitive_walker_importer_is_selected(tmp_path: Path) -> None:
    _make_repo(tmp_path)
    _write(tmp_path, "pkg/scan.py", "import os\nos.walk('.')\n")
    _write(tmp_path, "tests/test_uses_scan.py", "from pkg import scan\n")
    result = _select(tmp_path, ["docs/x.md"])
    assert "tests/test_uses_scan.py" in result.tests


def test_directory_component_literal_selects_reader(tmp_path: Path) -> None:
    _make_repo(tmp_path)
    _write(tmp_path, "tests/test_docs_dir.py", "ROOT = 'docs/sub'\n")
    result = _select(tmp_path, ["docs/sub/guide.md"])
    assert "tests/test_docs_dir.py" in result.tests


def test_leading_dot_directory_literal_is_not_mangled(tmp_path: Path) -> None:
    _make_repo(tmp_path)
    _write(tmp_path, "tests/test_dot_dir.py", "ROOT = './.claude/'\n")
    result = _select(tmp_path, [".claude/notes.md"])
    assert "tests/test_dot_dir.py" in result.tests


def test_python_change_and_input_change_union(tmp_path: Path) -> None:
    _make_repo(tmp_path)
    result = _select(tmp_path, ["AGENTS.md", "pkg/other.py"])
    assert not result.full
    assert "tests/test_unrelated.py" in result.tests
    assert "tests/test_literal.py" in result.tests


def test_non_content_test_input_stays_full(tmp_path: Path) -> None:
    _make_repo(tmp_path)
    result = _select(tmp_path, ["uv.lock", "AGENTS.md"])
    assert result.full
    assert "uv.lock" in result.reason


def test_unlisted_non_python_stays_full(tmp_path: Path) -> None:
    _make_repo(tmp_path)
    result = _select(tmp_path, ["AGENTS.md", "logo.png"])
    assert result.full
    assert "non-Python" in result.reason


def test_input_with_no_reader_and_no_walker_is_full(tmp_path: Path) -> None:
    _write(tmp_path, "pyproject.toml", "[project]\nname = 'demo'\n")
    _write(tmp_path, "tests/test_only.py", "x = 1\n")
    result = _select(tmp_path, ["AGENTS.md"])
    assert result.full
    assert "no test transitively" in result.reason


def test_unbuildable_graph_stays_full(tmp_path: Path) -> None:
    _make_repo(tmp_path)
    _write(tmp_path, "pkg/broken.py", "def (:\n")
    result = _select(tmp_path, ["AGENTS.md"])
    assert result.full
    assert "import graph unavailable" in result.reason


@pytest.mark.parametrize(
    ("rel", "expected"),
    [
        ("AGENTS.md", True),
        ("a/b.json", True),
        ("notes.txt", True),
        ("uv.lock", False),
        ("pyproject.toml", False),
        ("lefthook.yml", False),
        ("requirements-dev.txt", False),
        ("constraints.txt", False),
        ("web/package.json", False),
        ("package-lock.json", False),
    ],
)
def test_is_narrowable(rel: str, expected: bool) -> None:
    assert reader_map.is_narrowable(rel) is expected


def test_candidate_literals_cover_suffixes_and_directory_runs() -> None:
    assert reader_map.candidate_literals("aa/bb/c.md") == {
        "aa/bb/c.md",
        "bb/c.md",
        "c.md",
        "aa",
        "aa/bb",
        "bb",
    }


def test_reader_tests_uses_supplied_graph_data() -> None:
    data = import_graph.ImportGraphData(
        graph={"tests/test_a.py": frozenset(), "tests/test_b.py": frozenset()},
        wildcard_dependents=frozenset(),
        string_literals={"tests/test_a.py": frozenset({"docs/x.md"})},
        tree_walkers=frozenset(),
    )
    assert reader_map.reader_tests(["docs/x.md"], data) == {"tests/test_a.py"}
