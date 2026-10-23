"""Equivalence tests for the per-node ``ast.dump`` cache in the encoding gate.

Profiling the "Subprocess Encoding Convention" pre-PR gate (issue #6734) showed
``_merge_states`` and ``_state_key`` calling ``ast.dump`` 1,052,097 times over
the tracked scripts. ``_node_dump`` computes each node's dump once. These tests
pin that the cache returns what ``ast.dump`` returns, never answers for a freed
node's replacement, and leaves every merge, key, and scan verdict unchanged.
"""

from __future__ import annotations

import ast
import gc
import sys
import weakref
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
_VALIDATION_DIR = REPO_ROOT / "scripts" / "validation"
if str(_VALIDATION_DIR) not in sys.path:
    sys.path.insert(0, str(_VALIDATION_DIR))

import check_subprocess_encoding as gate

_State = tuple[set[str], dict[str, frozenset[str]], set[str], dict[str, tuple[ast.expr, ...]]]


def _const(value: str | int | bool | None) -> ast.Constant:
    return ast.Constant(value=value)


def _reference_merge(*states: _State) -> _State:
    """The merge as it was before the cache: ``ast.dump`` on every comparison."""
    modules: set[str] = set()
    callables: dict[str, frozenset[str]] = {}
    pipes: set[str] = set()
    common = set.intersection(*(set(state[3]) for state in states)) if states else set()
    known: dict[str, list[ast.expr]] = {name: [] for name in common}
    for state_modules, state_callables, state_pipes, state_known in states:
        modules.update(state_modules)
        pipes.update(state_pipes)
        for name, calls in state_callables.items():
            callables[name] = callables.get(name, frozenset()) | calls
        for name in common:
            destination = known[name]
            existing = {ast.dump(option) for option in destination}
            destination.extend(o for o in state_known[name] if ast.dump(o) not in existing)
    return modules, callables, pipes, {n: tuple(o) for n, o in known.items()}


def _reference_key(state: _State) -> tuple[object, ...]:
    modules, callables, pipes, known = state
    return (
        frozenset(modules),
        frozenset(callables.items()),
        frozenset(pipes),
        frozenset((n, frozenset(ast.dump(o) for o in opts)) for n, opts in known.items()),
    )


def _state(known: dict[str, tuple[ast.expr, ...]], modules: set[str] | None = None) -> _State:
    return (modules or set(), {"run": frozenset({"run"})}, set(), known)


def _fingerprint(merged: _State) -> tuple[object, ...]:
    """Compare merged states structurally: node identity differs between runs."""
    modules, callables, pipes, known = merged
    return (
        modules,
        callables,
        pipes,
        {name: tuple(ast.dump(option) for option in options) for name, options in known.items()},
    )


def test_node_dump_equals_ast_dump() -> None:
    node = ast.parse("f(a, b=[1, 'x'])").body[0]
    assert gate._node_dump(node) == ast.dump(node)


def test_node_dump_computes_each_node_once(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[ast.AST] = []
    real = ast.dump

    def counting(node: ast.AST, *args: object, **kwargs: object) -> str:
        calls.append(node)
        return real(node)

    monkeypatch.setattr(gate.ast, "dump", counting)
    node = _const("once")
    results = {gate._node_dump(node) for _ in range(5)}
    assert len(results) == 1
    assert len(calls) == 1


def test_node_dump_distinguishes_equal_looking_nodes_by_structure() -> None:
    assert gate._node_dump(_const(True)) != gate._node_dump(_const(False))
    assert gate._node_dump(_const(1)) != gate._node_dump(_const("1"))
    assert gate._node_dump(_const("a")) == gate._node_dump(_const("a"))


def test_node_dump_never_answers_for_a_freed_nodes_replacement() -> None:
    """Mutation control: a cache keyed by ``id()`` alone fails this.

    CPython reuses the address of a freed object. Allocating and dropping many
    nodes with different payloads provokes reuse; every answer must still match
    the node it was asked about.
    """
    for round_number in range(2000):
        value = round_number % 7
        node = _const(value)
        assert gate._node_dump(node) == ast.dump(node)
        del node
        if round_number % 50 == 0:
            gc.collect()


def test_cache_releases_entries_when_the_tree_is_dropped() -> None:
    """Context nodes (``Load``, ``Store``) are interpreter singletons, so skip them."""
    tree = ast.parse("x = [1, 2, 3]\ny = 'a'")
    refs = []
    for node in ast.walk(tree):
        gate._node_dump(node)
        if not isinstance(node, ast.expr_context):
            refs.append(weakref.ref(node))
    assert all(ref() in gate._NODE_DUMPS for ref in refs)
    del tree, node
    gc.collect()
    assert all(ref() is None for ref in refs)
    assert not any(isinstance(key, ast.Assign) for key in list(gate._NODE_DUMPS))


def test_merge_deduplicates_structurally_equal_distinct_nodes() -> None:
    first = _state({"flag": (_const(True),)})
    second = _state({"flag": (_const(True),)})
    merged = gate._SubprocessCallVisitor._merge_states(first, second)
    assert len(merged[3]["flag"]) == 1


def test_merge_keeps_structurally_different_options() -> None:
    first = _state({"flag": (_const(True),)})
    second = _state({"flag": (_const(False),)})
    merged = gate._SubprocessCallVisitor._merge_states(first, second)
    assert [ast.dump(o) for o in merged[3]["flag"]] == [
        ast.dump(_const(True)),
        ast.dump(_const(False)),
    ]


def test_merge_keeps_duplicates_inside_one_states_options() -> None:
    """The dedup set is built before each extend, as before the cache."""
    first = _state({"flag": (_const(1),)})
    second = _state({"flag": (_const(2), _const(2))})
    merged = gate._SubprocessCallVisitor._merge_states(first, second)
    assert len(merged[3]["flag"]) == 3


def test_merge_drops_names_known_in_only_some_states() -> None:
    first = _state({"flag": (_const(True),), "only_first": (_const(1),)})
    second = _state({"flag": (_const(True),)})
    merged = gate._SubprocessCallVisitor._merge_states(first, second)
    assert set(merged[3]) == {"flag"}


@pytest.mark.parametrize(
    "layouts",
    [
        [{"a": (1,)}, {"a": (1,)}],
        [{"a": (1,)}, {"a": (2,)}, {"a": (1,)}],
        [{"a": (1, 2)}, {"a": (2, 3)}, {"a": (3, 1)}],
        [{"a": (1,), "b": ("x",)}, {"a": (1,), "b": ("y",)}, {"a": (2,), "b": ("x",)}],
        [{"a": (1,), "b": (2,)}, {"a": (1,)}],
        [{}, {"a": (1,)}],
        [{"a": (None,)}, {"a": (None, None)}],
    ],
)
def test_merge_and_key_match_the_uncached_reference(
    layouts: list[dict[str, tuple[str | int | bool | None, ...]]],
) -> None:
    def build() -> list[_State]:
        return [
            _state(
                {name: tuple(_const(v) for v in values) for name, values in layout.items()},
                modules={f"m{index}"},
            )
            for index, layout in enumerate(layouts)
        ]

    cached = gate._SubprocessCallVisitor._merge_states(*build())
    reference = _reference_merge(*build())
    assert _fingerprint(cached) == _fingerprint(reference)
    for state in build():
        assert gate._SubprocessCallVisitor._state_key(state) == _reference_key(state)
    assert gate._SubprocessCallVisitor._state_key(cached) == _reference_key(reference)


def test_state_key_separates_states_that_differ_in_one_option() -> None:
    same_a = _state({"flag": (_const(True),)})
    same_b = _state({"flag": (_const(True),)})
    other = _state({"flag": (_const(False),)})
    key = gate._SubprocessCallVisitor._state_key
    assert key(same_a) == key(same_b)
    assert key(same_a) != key(other)


_BRANCHY_SOURCES = [
    # Positive: a rebound alias still reaches the unguarded call.
    "import subprocess as sp\nrun = sp.run\n"
    "if cond:\n    flag = True\nelse:\n    flag = False\n"
    "run(['x'], text=True, encoding='utf-8')\n",
    # Negative: errors='replace' satisfies the convention on every path.
    "import subprocess as sp\n"
    "if cond:\n    flag = True\nelse:\n    flag = True\n"
    "sp.run(['x'], text=flag, encoding='utf-8', errors='replace')\n",
    # Loop fixpoint (the _state_key consumer): alias rebound inside the loop.
    "import subprocess as sp\nrun = print\n"
    "for item in range(3):\n    run(['x'], text=True, encoding='utf-8')\n    run = sp.run\n",
    # Static iteration over a merged name.
    "import subprocess as sp\nrun = sp.run\n"
    "if cond:\n    items = [1, 2]\nelse:\n    items = [1, 2]\n"
    "for item in items:\n    run(['x'], text=True, encoding='utf-8')\n    run = print\n",
    # Try/except boundary merge.
    "import subprocess as sp\nrun = print\n"
    "try:\n    run = sp.run\n    risky()\nexcept Exception:\n    pass\n"
    "run(['x'], text=True, encoding='utf-8')\n",
    # While loop with a conditional rebind.
    "import subprocess as sp\nrun = print\nwhile cond():\n    if other():\n        run = sp.run\n"
    "    run(['x'], text=True, encoding='utf-8')\n",
]


def _corpus_sources() -> list[str]:
    paths = sorted(_VALIDATION_DIR.glob("*.py"))
    texts = [p.read_text(encoding="utf-8") for p in paths]
    return [text for text in texts if gate._SUBPROCESS_TOKEN in text][:40]


def test_cached_scan_matches_uncached_scan(monkeypatch: pytest.MonkeyPatch) -> None:
    sources = [*_BRANCHY_SOURCES, *_corpus_sources()]
    cached = [gate.find_violations(source) for source in sources]
    monkeypatch.setattr(gate, "_node_dump", ast.dump)
    uncached = [gate.find_violations(source) for source in sources]
    assert cached == uncached
    # Not vacuous: the branchy fixtures include flagged and unflagged cases.
    assert any(cached[: len(_BRANCHY_SOURCES)])
    assert not all(cached[: len(_BRANCHY_SOURCES)])


def test_repeated_scans_do_not_leak_results_between_sources() -> None:
    flagged = "import subprocess\nsubprocess.run(['x'], text=True, encoding='utf-8')\n"
    clean = (
        "import subprocess\nsubprocess.run(['x'], text=True, encoding='utf-8', errors='replace')\n"
    )
    for _ in range(200):
        assert gate.find_violations(flagged) == [2]
        assert gate.find_violations(clean) == []
