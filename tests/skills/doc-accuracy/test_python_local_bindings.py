"""Phase 3 resolves names a Python example binds itself, by scope and order.

A name drops only when every code occurrence is a binding or a read that
resolves to an earlier binding visible in that scope. Imports, reads before
binding, reads out of scope, and unknown class members stay findings.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from example_scope_helpers import run_cli, unresolved

_ENUM = "from enum import Enum\n\nclass Status(Enum):\n    SUCCESS = 0\n    TIMEOUT = 30\n\n"

# --- Positive: example-local bindings resolve ----------------------------------


@pytest.mark.parametrize(
    "code",
    [
        "THRESHOLDS = {'limit': 3}\nprint(THRESHOLDS)\n",
        "LIMIT: int = 3\nprint(LIMIT)\n",
        _ENUM,
        _ENUM + "def main():\n    return Status.SUCCESS\n",
        _ENUM
        + "def main():\n    if x:\n        return Status.TIMEOUT\n    return Status.SUCCESS\n",
        "LIMIT = 3\n\ndef check(n):\n    return n > LIMIT\n",
        "LIMIT = 3\nVALUES = [LIMIT * n for n in range(3)]\n",
        "from typing import Literal\nProvenanceLiteral = Literal['a', 'b']\n",
        "def f():\n    TOTAL = 1\n    TOTAL += 1\n    return TOTAL\n",
        "def outer():\n    LIMIT = 2\n    def inner():\n        return LIMIT\n    return inner\n",
        "check = lambda LIMIT: LIMIT > 0\n",
        "def f(LIMIT):\n    return LIMIT\n",
        "pairs = [(KEY, 1) for KEY in 'ab']\n",
        "HOOK = 1\nmessage = f'{HOOK}'\n",
    ],
)
def test_example_local_bindings_are_not_flagged(code: str) -> None:
    assert unresolved(code, "python") == set()


# --- Negative: out of scope, out of order, imported, or unknown members ---------


@pytest.mark.parametrize(
    ("code", "expected"),
    [
        ("print(LIMIT)\nLIMIT = 3\n", {"LIMIT"}),
        ("LIMIT = LIMIT + 1\n", {"LIMIT"}),
        ("LIMIT += 1\n", {"LIMIT"}),
        ("def f():\n    LIMIT = 3\n\nprint(LIMIT)\n", {"LIMIT"}),
        ("def f():\n    LIMIT = 3\n\ndef g():\n    return LIMIT\n", {"LIMIT"}),
        ("def f():\n    print(LIMIT)\n    LIMIT = 3\n", {"LIMIT"}),
        (
            "class Config:\n    LIMIT = 3\n    def read(self):\n        return LIMIT\n",
            {"LIMIT"},
        ),
        (_ENUM + "value = Status.MISSING\n", {"MISSING"}),
        ("SUCCESS = 0\nvalue = result.SUCCESS\n", {"SUCCESS"}),
        ("from mypkg import GhostWidget\nGhostWidget()\n", {"GhostWidget"}),
        ("LIMIT = 3\nprint(LIMIT)\nprint(OTHER.LIMIT)\n", {"LIMIT", "OTHER"}),
        ("VALUES = [LIMIT for n in range(3)]\nLIMIT = 1\n", {"LIMIT"}),
        ("def f():\n    global LIMIT\n    LIMIT = 3\n", {"LIMIT"}),
        ("LIMIT: int\nprint(LIMIT)\n", {"LIMIT"}),
        ("class Config:\n    LIMIT: int\n\nvalue = Config.LIMIT\n", {"LIMIT"}),
    ],
)
def test_unresolved_python_names_stay_flagged(code: str, expected: set[str]) -> None:
    assert unresolved(code, "python") == expected


# --- Control flow: only definite bindings resolve later reads -------------------


@pytest.mark.parametrize(
    "code",
    [
        "if False:\n    LIMIT = 3\nprint(LIMIT)\n",
        "if flag:\n    LIMIT = 3\nelif other:\n    LIMIT = 4\nprint(LIMIT)\n",
        "for item in []:\n    LIMIT = 3\nprint(LIMIT)\n",
        "while flag:\n    LIMIT = 3\nprint(LIMIT)\n",
        "for item in items:\n    print(LIMIT)\n    LIMIT = 3\n",
        "try:\n    LIMIT = 3\nexcept OSError:\n    pass\nprint(LIMIT)\n",
        "try:\n    pass\nexcept OSError:\n    LIMIT = 3\nprint(LIMIT)\n",
        "with lock:\n    LIMIT = 3\nprint(LIMIT)\n",
        "match value:\n    case 1:\n        LIMIT = 3\nprint(LIMIT)\n",
        "ok = flag and (LIMIT := 3)\nprint(LIMIT)\n",
        "x = 1 if flag else (LIMIT := 3)\nprint(LIMIT)\n",
        "if flag:\n    LIMIT = 3\ndef f():\n    return LIMIT\n",
        "LIMIT = 3\ndel LIMIT\nprint(LIMIT)\n",
    ],
)
def test_non_definite_bindings_leave_reads_flagged(code: str) -> None:
    assert "LIMIT" in unresolved(code, "python")


@pytest.mark.parametrize(
    "code",
    [
        "if flag:\n    LIMIT = 1\nelse:\n    LIMIT = 2\nprint(LIMIT)\n",
        "if flag:\n    LIMIT = 1\nelse:\n    raise ValueError(flag)\nprint(LIMIT)\n",
        "if flag:\n    LIMIT = 1\n    print(LIMIT)\n",
        "try:\n    LIMIT = 1\nexcept OSError:\n    LIMIT = 2\nprint(LIMIT)\n",
        "try:\n    pass\nfinally:\n    LIMIT = 1\nprint(LIMIT)\n",
        "try:\n    LIMIT = 1\nexcept OSError:\n    raise\nprint(LIMIT)\n",
        "for item in items:\n    LIMIT = item\n    print(LIMIT)\n",
        "with lock:\n    LIMIT = 3\n    print(LIMIT)\n",
        "if (LIMIT := compute()):\n    pass\nprint(LIMIT)\n",
        "def f(flag):\n    if flag:\n        return 0\n    LIMIT = 1\n    return LIMIT\n",
    ],
)
def test_definite_bindings_resolve_later_reads(code: str) -> None:
    assert "LIMIT" not in unresolved(code, "python")


def test_conditional_class_member_is_not_a_proven_attribute() -> None:
    code = "class Config:\n    if flag:\n        LIMIT = 3\n\nvalue = Config.LIMIT\n"
    assert unresolved(code, "python") == {"LIMIT"}


def test_fstring_expression_stays_checkable_beside_a_resolved_name() -> None:
    # Before 3.12 the tokenizer blanks a whole f-string, a documented
    # extraction limit (_extract_identifiers) that only ever misses a name.
    expected = {"GhostWidget"} if sys.version_info >= (3, 12) else set()
    assert unresolved("LIMIT = 3\nmessage = f'{GhostWidget()} {LIMIT}'\n", "python") == expected


def test_unparseable_example_keeps_every_name() -> None:
    assert unresolved("LIMIT = 3\nprint(LIMIT\n", "python") == {"LIMIT"}


def test_non_ascii_text_before_a_binding_keeps_columns_aligned() -> None:
    code = "label = 'café'; LIMIT = 3\nprint(LIMIT)\n"
    assert unresolved(code, "python") == set()


# --- Real CLI -------------------------------------------------------------------


@pytest.mark.parametrize(
    ("code", "exit_code", "expected"),
    [
        ("THRESHOLDS = {'limit': 3}\nprint(THRESHOLDS)", 0, set()),
        (_ENUM + "def main():\n    return Status.SUCCESS", 0, set()),
        (_ENUM + "value = Status.MISSING", 10, {("unresolved_symbol", "MISSING")}),
        ("print(LIMIT)\nLIMIT = 3", 10, {("unresolved_symbol", "LIMIT")}),
        (
            "import third_party\nthird_party.GhostWidget()",
            10,
            {("unresolved_symbol", "GhostWidget")},
        ),
    ],
)
def test_cli_resolves_local_bindings_without_hiding_errors(
    tmp_path: Path, code: str, exit_code: int, expected: set[tuple[str, str]]
) -> None:
    assert run_cli(tmp_path, "python", code) == (exit_code, expected)
