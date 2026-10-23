"""Equivalence tests for the per-run import memo in the interpreter-portability guard.

Issue #6734 sped the gate up by parsing each script once per scan instead of once
per documented mention. These tests pin that the memo changes cost, never verdicts.
"""

from __future__ import annotations

import ast
import random
from pathlib import Path
from typing import Any

import pytest

import scripts.validation.check_doc_interpreter_portability as checker
from scripts.validation.check_doc_interpreter_portability import (
    INVOCATION_LITERAL,
    INVOCATION_PATTERN,
    ImportCache,
    ScanError,
    find_offenses,
    scan,
    third_party_imports,
)
from tests.test_check_doc_interpreter_portability import make_repo

THIRD_PARTY = ("yaml", "jsonschema")


def _tracked(files: dict[str, str]) -> set[str]:
    return {name for name in files if name.endswith(".py")}


def test_cycle_does_not_poison_the_cache_for_the_back_edge_root(tmp_path: Path) -> None:
    """a imports b and yaml, b imports a. Walking a first must not hide yaml from b.

    While the walk from a is inside the cycle, b sees a as already visited and
    returns nothing. A memo that stored that partial result for b would report b
    as clean forever.
    """
    files = {
        "a.py": "import b\nimport yaml\n",
        "b.py": "import a\n",
        "README.md": "Run `python3 a.py` then `python3 b.py`.\n",
    }
    repo = make_repo(tmp_path, files)
    tracked = _tracked(files)
    cache = ImportCache()

    assert third_party_imports("a.py", repo, tracked, cache=cache) == {"yaml"}
    assert third_party_imports("b.py", repo, tracked, cache=cache) == {"yaml"}
    assert third_party_imports("b.py", repo, tracked) == {"yaml"}
    assert scan(repo) == {"README.md": ["a.py", "b.py"]}


def test_repeated_mentions_parse_each_script_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    files = {
        "dep.py": "import yaml\n",
        "entry.py": "import dep\n",
    }
    repo = make_repo(tmp_path, files)
    tracked = _tracked(files)
    parsed: list[str] = []
    real_parse = ast.parse

    def counting_parse(source: str, *args: Any, **kwargs: Any) -> ast.Module:
        parsed.append(source)
        return real_parse(source, *args, **kwargs)

    monkeypatch.setattr(checker.ast, "parse", counting_parse)
    line = "Run `python3 entry.py`."

    cache = ImportCache()
    cached = [find_offenses(line, repo, tracked, cache) for _ in range(5)]
    cached_parses = len(parsed)
    parsed.clear()
    uncached = [find_offenses(line, repo, tracked) for _ in range(5)]

    assert cached == uncached == [[("entry.py", ["yaml"])]] * 5
    assert cached_parses == 2
    assert len(parsed) == 10


def test_each_scan_starts_with_an_empty_cache(tmp_path: Path) -> None:
    """Editing a dependency between two scans changes the second verdict."""
    files = {
        "dep.py": "import os\n",
        "entry.py": "import dep\n",
        "README.md": "Run `python3 entry.py`.\n",
    }
    repo = make_repo(tmp_path, files)

    assert scan(repo) == {}

    (repo / "dep.py").write_text("import yaml\n", encoding="utf-8")

    assert scan(repo) == {"README.md": ["entry.py"]}


def test_broken_script_still_raises_scan_error_with_a_cache(tmp_path: Path) -> None:
    files = {"entry.py": "def broken(:\n", "README.md": "Run `python3 entry.py`.\n"}
    repo = make_repo(tmp_path, files)
    tracked = _tracked(files)
    cache = ImportCache()

    for _ in range(2):
        with pytest.raises(ScanError, match="could not analyze entry.py"):
            third_party_imports("entry.py", repo, tracked, cache=cache)
    with pytest.raises(ScanError, match="could not analyze entry.py"):
        scan(repo)


def test_declared_line_naming_a_broken_script_still_does_not_raise(tmp_path: Path) -> None:
    """A declared line is skipped before its script is parsed, as before the memo."""
    files = {
        "entry.py": "def broken(:\n",
        "README.md": (
            "<!-- doc-interpreter-portability: quoting CI verbatim -->\nRun `python3 entry.py`.\n"
        ),
    }
    repo = make_repo(tmp_path, files)

    assert scan(repo) == {}


def test_line_without_python_never_reaches_the_script_lookup(tmp_path: Path) -> None:
    files = {"entry.py": "def broken(:\n", "README.md": "See entry.py for details.\n"}
    repo = make_repo(tmp_path, files)

    assert find_offenses("See entry.py for details.", repo, _tracked(files)) == []
    assert scan(repo) == {}


def test_uv_run_prefix_and_untracked_script_are_still_skipped_with_a_cache(
    tmp_path: Path,
) -> None:
    files = {"entry.py": "import yaml\n"}
    repo = make_repo(tmp_path, files)
    tracked = _tracked(files)
    cache = ImportCache()

    assert find_offenses("uv run python entry.py", repo, tracked, cache) == []
    assert find_offenses("python3 missing.py", repo, tracked, cache) == []
    assert find_offenses("python3 entry.py", repo, tracked, cache) == [("entry.py", ["yaml"])]


def _random_module(rng: random.Random, count: int) -> str:
    lines: list[str] = []
    for _ in range(rng.randint(0, 3)):
        lines.append(f"import m{rng.randrange(count)}")
    if rng.random() < 0.35:
        lines.append(f"import {rng.choice(THIRD_PARTY)}")
    if rng.random() < 0.2:
        lines.append("import os")
    if rng.random() < 0.2:
        lines.append(f"def late():\n    import {rng.choice(THIRD_PARTY)}")
    return "\n".join(lines) + "\n"


@pytest.mark.parametrize("seed", range(12))
def test_cached_closure_matches_uncached_on_random_import_graphs(tmp_path: Path, seed: int) -> None:
    """Dense graphs with cycles: every root agrees, in any visiting order."""
    rng = random.Random(seed)
    count = 10
    files = {f"m{i}.py": _random_module(rng, count) for i in range(count)}
    repo = make_repo(tmp_path, files)
    tracked = _tracked(files)
    roots = sorted(tracked)
    rng.shuffle(roots)
    cache = ImportCache()

    expected = {root: third_party_imports(root, repo, tracked) for root in roots}
    for root in roots + roots[::-1]:
        assert third_party_imports(root, repo, tracked, cache=cache) == expected[root]


def test_subprocess_launched_dependency_is_found_through_the_cache(tmp_path: Path) -> None:
    files = {
        "validate.py": "import jsonschema\n",
        "entry.py": (
            "import os\nimport subprocess\nimport sys\n"
            "def run(root):\n"
            "    target = os.path.join(root, 'validate.py')\n"
            "    subprocess.run([sys.executable, target], check=False)\n"
            "run('.')\n"
        ),
    }
    repo = make_repo(tmp_path, files)
    tracked = _tracked(files)
    cache = ImportCache()

    for _ in range(2):
        assert third_party_imports("entry.py", repo, tracked, cache=cache) == {"jsonschema"}
    assert third_party_imports("entry.py", repo, tracked) == {"jsonschema"}


@pytest.mark.parametrize(
    "text",
    [
        "python entry.py",
        "python3 entry.py",
        "python3 -u -S entry.py",
        "x python3 ./a/b.py",
    ],
)
def test_prefilter_literal_is_in_every_pattern_match(text: str) -> None:
    """The literal prefilter is sound only while every match contains it."""
    match = INVOCATION_PATTERN.search(text)

    assert match is not None
    assert INVOCATION_LITERAL in match.group(0)
    assert INVOCATION_PATTERN.flags & 2 == 0  # re.IGNORECASE would widen the match set


def test_prefilter_literal_is_the_required_head_of_the_pattern() -> None:
    """Pin the pattern head so a new alternative such as ``py`` fails here, not silently."""
    head = r"(?<![\w./-])" + INVOCATION_LITERAL + "3?"

    assert INVOCATION_PATTERN.pattern.startswith(head)
    assert "|" not in INVOCATION_PATTERN.pattern.split(r"(?:[ \t]+-", 1)[0]
